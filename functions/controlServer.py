import hmac
import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from library.app import getCurrentVersion
from library.filesystem import MOUNT_METHOD
from functions.appFunctions import refresh_lock
from functions.refreshFunctions import performRefresh

CONTROL_API_VERSION = 2
MAX_RETAINED_JOBS = 20

TOKEN = os.getenv("CONTROL_TOKEN", "")

_state_lock = threading.Lock()
_state = {
    "last_finished": 0.0,
    "last_result": None,
    "last_error": None,
}

_jobs_lock = threading.Lock()
_jobs = {}
_job_order = []
_idempotency = {}
_active_job_id = None


def _cooldown_remaining():
    try:
        interval = max(0.0, float(os.getenv("CONTROL_MIN_INTERVAL", "60")))
    except ValueError:
        interval = 60.0

    with _state_lock:
        last_finished = _state["last_finished"]

    return max(0.0, interval - (time.time() - last_finished))


def _job_payload(job):
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "result": job["result"],
        "error": job["error"],
    }


def _job_reply(job):
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "status_url": f"/refresh/jobs/{job['job_id']}",
    }


def _finish_job(job_id, status, result=None, error=None):
    global _active_job_id

    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] in ("completed", "failed"):
            return

        job["status"] = status
        job["finished_at"] = time.time()
        job["result"] = result
        job["error"] = error
        _job_order.append(job_id)
        if _active_job_id == job_id:
            _active_job_id = None

        while len(_job_order) > MAX_RETAINED_JOBS:
            old_id = _job_order.pop(0)
            old_job = _jobs.pop(old_id, None)
            if old_job is None:
                continue
            key = old_job.get("idempotency_key")
            if key and _idempotency.get(key) == old_id:
                _idempotency.pop(key, None)


def _run_job(job_id):
    global _active_job_id

    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_at"] = time.time()

    started = time.time()
    logging.info("Control refresh job started: job_id=%s", job_id)

    try:
        result = performRefresh()
        result["duration_ms"] = int((time.time() - started) * 1000)
        with _state_lock:
            _state["last_result"] = result
            _state["last_error"] = None
            _state["last_finished"] = time.time()
        _finish_job(job_id, "completed", result=result)
        logging.info(
            "Control refresh job completed: job_id=%s duration_ms=%s "
            "added=%s removed=%s updated=%s partial=%s",
            job_id,
            result["duration_ms"],
            result.get("added"),
            result.get("removed"),
            result.get("updated"),
            result.get("partial"),
        )
    except Exception as e:
        logging.exception(
            "Control refresh job failed: job_id=%s duration_ms=%s",
            job_id,
            int((time.time() - started) * 1000),
        )
        with _state_lock:
            _state["last_error"] = str(e)
            _state["last_finished"] = time.time()
        _finish_job(job_id, "failed", error=str(e))
    finally:
        with _jobs_lock:
            if _active_job_id == job_id:
                _active_job_id = None


class Handler(BaseHTTPRequestHandler):
    server_version = "TorBoxMediaCenterControl/1.0"

    def log_message(self, fmt, *args):
        logging.debug("control api: " + fmt, *args)

    def _authorized(self):
        expected = f"Bearer {TOKEN}".encode()
        actual = self.headers.get("Authorization", "").encode()
        return hmac.compare_digest(actual, expected)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _send_json(self, status, payload, headers=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path

        if path == "/health":
            if not self._authorized():
                return self._send_json(401, {"error": "unauthorized"})

            with _state_lock:
                state = dict(_state)

            return self._send_json(
                200,
                {
                    "status": "ok",
                    "api_version": CONTROL_API_VERSION,
                    "version": getCurrentVersion(),
                    "mode": MOUNT_METHOD,
                    "last_finished": state["last_finished"] or None,
                    "last_result": state["last_result"],
                    "last_error": state["last_error"],
                },
            )

        if path.startswith("/refresh/jobs/"):
            if not self._authorized():
                return self._send_json(401, {"error": "unauthorized"})

            job_id = path[len("/refresh/jobs/"):]
            if not job_id or "/" in job_id:
                return self._send_json(404, {"error": "not found"})

            with _jobs_lock:
                job = _jobs.get(job_id)
                payload = _job_payload(job) if job else None

            if payload is None:
                return self._send_json(404, {"error": "not found"})
            return self._send_json(200, payload)

        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/refresh", "/refresh/jobs"):
            return self._send_json(404, {"error": "not found"})
        if not self._authorized():
            return self._send_json(401, {"error": "unauthorized"})

        payload = self._read_json()
        if not isinstance(payload, dict):
            return self._send_json(400, {"error": "invalid json"})

        if path == "/refresh/jobs":
            return self._start_job(payload)

        remaining = _cooldown_remaining()
        if not payload.get("force") and remaining > 0:
            return self._send_json(
                429,
                {"error": "cooldown", "retry_after": round(remaining, 1)},
                {"Retry-After": str(int(remaining) + 1)},
            )

        if not refresh_lock.acquire(blocking=False):
            return self._send_json(409, {"error": "refresh already running"})

        started = time.time()
        try:
            result = performRefresh()
            result["duration_ms"] = int((time.time() - started) * 1000)
            with _state_lock:
                _state["last_result"] = result
                _state["last_error"] = None
            logging.info(
                "Control refresh: %s added, %s removed, %s updated",
                result["added"],
                result["removed"],
                result["updated"],
            )
            self._send_json(200, result)
        except Exception as e:
            logging.exception("Control refresh failed")
            with _state_lock:
                _state["last_error"] = str(e)
            self._send_json(500, {"error": str(e)})
        finally:
            with _state_lock:
                _state["last_finished"] = time.time()
            refresh_lock.release()

    def _send_conflict(self, active_id):
        return self._send_json(
            409,
            {
                "error": "refresh already running",
                "job_id": active_id,
                "active_job_id": active_id,
            },
        )

    def _find_idempotent_job(self, key):
        if not key:
            return None
        with _jobs_lock:
            job_id = _idempotency.get(key)
            job = _jobs.get(job_id) if job_id else None
            return dict(job) if job else None

    def _start_job(self, payload):
        global _active_job_id

        force = bool(payload.get("force"))
        idempotency_key = (self.headers.get("Idempotency-Key") or "").strip() or None

        replay = self._find_idempotent_job(idempotency_key)
        if replay is not None:
            return self._send_json(202, _job_reply(replay))

        with _jobs_lock:
            active_id = _active_job_id

        if active_id:
            return self._send_conflict(active_id)
        if not refresh_lock.acquire(blocking=False):
            with _jobs_lock:
                active_id = _active_job_id
            return self._send_conflict(active_id)
        refresh_lock.release()

        remaining = _cooldown_remaining()
        if not force and remaining > 0:
            return self._send_json(
                429,
                {"error": "cooldown", "retry_after": round(remaining, 1)},
                {"Retry-After": str(int(remaining) + 1)},
            )

        with _jobs_lock:
            active_id = _active_job_id
            replay = None
            if not active_id and idempotency_key:
                existing_id = _idempotency.get(idempotency_key)
                existing = _jobs.get(existing_id) if existing_id else None
                if existing is not None:
                    replay = dict(existing)

            job_id = None
            if not active_id and replay is None:
                job_id = uuid.uuid4().hex
                _jobs[job_id] = {
                    "job_id": job_id,
                    "status": "queued",
                    "started_at": None,
                    "finished_at": None,
                    "result": None,
                    "error": None,
                    "idempotency_key": idempotency_key,
                }
                if idempotency_key:
                    _idempotency[idempotency_key] = job_id
                _active_job_id = job_id

        if active_id:
            return self._send_conflict(active_id)
        if replay is not None:
            return self._send_json(202, _job_reply(replay))

        thread = threading.Thread(
            target=_run_job,
            args=(job_id,),
            daemon=True,
            name=f"torbox-refresh-{job_id}",
        )
        thread.start()

        return self._send_json(
            202,
            {
                "job_id": job_id,
                "status": "queued",
                "status_url": f"/refresh/jobs/{job_id}",
            },
        )


def startControlServer():
    if not TOKEN:
        raise RuntimeError("CONTROL_TOKEN must be set when CONTROL_ENABLED=true")

    host = os.getenv("CONTROL_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROL_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="torbox-control",
    )
    thread.start()
    logging.info("Control API listening on %s:%s", host, port)
    return server
