import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from library.app import getCurrentVersion
from library.filesystem import MOUNT_METHOD
from functions.appFunctions import refresh_lock
from functions.refreshFunctions import performRefresh

TOKEN = os.getenv("CONTROL_TOKEN", "")

_state_lock = threading.Lock()
_state = {
    "last_finished": 0.0,
    "last_result": None,
    "last_error": None,
}


def _cooldown_remaining():
    try:
        interval = max(0.0, float(os.getenv("CONTROL_MIN_INTERVAL", "60")))
    except ValueError:
        interval = 60.0

    with _state_lock:
        last_finished = _state["last_finished"]

    return max(0.0, interval - (time.time() - last_finished))


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
        if self.path != "/health":
            return self._send_json(404, {"error": "not found"})
        if not self._authorized():
            return self._send_json(401, {"error": "unauthorized"})

        with _state_lock:
            state = dict(_state)

        self._send_json(
            200,
            {
                "status": "ok",
                "version": getCurrentVersion(),
                "mode": MOUNT_METHOD,
                "last_finished": state["last_finished"] or None,
                "last_result": state["last_result"],
                "last_error": state["last_error"],
            },
        )

    def do_POST(self):
        if self.path != "/refresh":
            return self._send_json(404, {"error": "not found"})
        if not self._authorized():
            return self._send_json(401, {"error": "unauthorized"})

        payload = self._read_json()
        if not isinstance(payload, dict):
            return self._send_json(400, {"error": "invalid json"})

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
