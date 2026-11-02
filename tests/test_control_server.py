import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

from functions import controlServer


class ControlServerTest(unittest.TestCase):
    def setUp(self):
        self.result = {
            "added": 1,
            "removed": 0,
            "updated": 0,
            "changed": 1,
            "partial": False,
            "errors": {},
            "mode": "strm",
            "mount": {},
            "refreshed": True,
        }
        self.refresh_started = threading.Event()
        self.release_refresh = threading.Event()
        self.perform = MagicMock(side_effect=lambda: dict(self.result))

        self.patches = [
            patch.object(controlServer, "TOKEN", "secret"),
            patch.object(controlServer, "performRefresh", self.perform),
            patch.dict("os.environ", {"CONTROL_MIN_INTERVAL": "0"}),
        ]
        for item in self.patches:
            item.start()

        controlServer._state.update(
            {"last_finished": 0.0, "last_result": None, "last_error": None}
        )
        with controlServer._jobs_lock:
            controlServer._jobs.clear()
            controlServer._job_order.clear()
            controlServer._idempotency.clear()
            controlServer._active_job_id = None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), controlServer.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.release_refresh.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            with controlServer._jobs_lock:
                active = controlServer._active_job_id
            if active is None:
                break
            time.sleep(0.01)

        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()

    def slow_refresh(self):
        self.refresh_started.set()
        self.release_refresh.wait(5)
        return dict(self.result)

    def request(self, path, method="POST", body=b"{}", token="secret", headers=None):
        request_headers = {"Authorization": f"Bearer {token}"}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})

        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def wait_for_status(self, job_id, expected, timeout=5):
        deadline = time.time() + timeout
        body = None
        while time.time() < deadline:
            status, body = self.request(f"/refresh/jobs/{job_id}", method="GET", body=None)
            if status == 200 and body["status"] == expected:
                return body
            time.sleep(0.01)
        self.fail(f"job {job_id} did not reach {expected}: {body}")

    def test_rejects_bad_token(self):
        status, _ = self.request("/refresh/jobs", token="wrong")
        self.assertEqual(status, 401)

        status, _ = self.request("/health", method="GET", body=None, token="wrong")
        self.assertEqual(status, 401)

    def test_health_returns_status_and_api_version(self):
        status, body = self.request("/health", method="GET", body=None)

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["api_version"], 2)
        self.assertIn("version", body)
        self.assertIn("mode", body)
        self.assertIn("last_finished", body)
        self.assertIn("last_result", body)
        self.assertIn("last_error", body)

    def test_refresh_returns_counts(self):
        status, body = self.request("/refresh")

        self.assertEqual(status, 200)
        self.assertEqual(body["changed"], 1)
        self.assertIn("duration_ms", body)

    def test_async_job_lifecycle(self):
        self.perform.side_effect = self.slow_refresh

        status, body = self.request("/refresh/jobs")
        self.assertEqual(status, 202)
        self.assertEqual(body["status"], "queued")
        job_id = body["job_id"]
        self.assertEqual(body["status_url"], f"/refresh/jobs/{job_id}")

        self.assertTrue(self.refresh_started.wait(5))
        status, body = self.request(f"/refresh/jobs/{job_id}", method="GET", body=None)
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "running")
        self.assertIsNotNone(body["started_at"])
        self.assertIsNone(body["finished_at"])

        self.release_refresh.set()
        body = self.wait_for_status(job_id, "completed")
        self.assertEqual(body["result"]["changed"], 1)
        self.assertIsNotNone(body["finished_at"])
        self.assertIsNone(body["error"])

    def test_async_job_conflict_while_active(self):
        self.perform.side_effect = self.slow_refresh

        status, body = self.request("/refresh/jobs")
        self.assertEqual(status, 202)
        job_id = body["job_id"]
        self.assertTrue(self.refresh_started.wait(5))

        status, body = self.request("/refresh/jobs", body=b'{"force": true}')
        self.assertEqual(status, 409)
        self.assertEqual(body["job_id"], job_id)
        self.assertEqual(body["active_job_id"], job_id)

        self.release_refresh.set()
        self.wait_for_status(job_id, "completed")

    def test_async_job_cooldown(self):
        controlServer._state["last_finished"] = time.time()

        with patch.dict(os.environ, {"CONTROL_MIN_INTERVAL": "60"}):
            status, body = self.request("/refresh/jobs")

        self.assertEqual(status, 429)
        self.assertEqual(body["error"], "cooldown")
        self.assertGreater(body["retry_after"], 0)
        self.perform.assert_not_called()

    def test_idempotency_key_reuses_active_and_recent_job(self):
        self.perform.side_effect = self.slow_refresh
        headers = {"Idempotency-Key": "scan-1"}

        status, body = self.request("/refresh/jobs", headers=headers)
        self.assertEqual(status, 202)
        job_id = body["job_id"]
        self.assertTrue(self.refresh_started.wait(5))

        status, replay = self.request("/refresh/jobs", headers=headers)
        self.assertEqual(status, 202)
        self.assertEqual(replay["job_id"], job_id)
        self.assertEqual(replay["status"], "running")
        self.assertEqual(self.perform.call_count, 1)

        self.release_refresh.set()
        self.wait_for_status(job_id, "completed")

        status, replay = self.request("/refresh/jobs", headers=headers)
        self.assertEqual(status, 202)
        self.assertEqual(replay["job_id"], job_id)
        self.assertEqual(replay["status"], "completed")
        self.assertEqual(self.perform.call_count, 1)

    def test_unknown_job_returns_404(self):
        status, _ = self.request("/refresh/jobs/missing", method="GET", body=None)
        self.assertEqual(status, 404)

    def test_retains_last_20_completed_jobs(self):
        job_ids = []
        for _ in range(21):
            status, body = self.request("/refresh/jobs")
            self.assertEqual(status, 202)
            job_ids.append(body["job_id"])
            self.wait_for_status(body["job_id"], "completed")

        status, _ = self.request(f"/refresh/jobs/{job_ids[0]}", method="GET", body=None)
        self.assertEqual(status, 404)
        status, _ = self.request(f"/refresh/jobs/{job_ids[1]}", method="GET", body=None)
        self.assertEqual(status, 200)
        with controlServer._jobs_lock:
            self.assertEqual(len(controlServer._jobs), 20)


if __name__ == "__main__":
    unittest.main()
