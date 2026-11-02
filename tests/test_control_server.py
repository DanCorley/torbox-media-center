import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

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

        self.patches = [
            patch.object(controlServer, "TOKEN", "secret"),
            patch.object(controlServer, "performRefresh", return_value=self.result),
            patch.dict("os.environ", {"CONTROL_MIN_INTERVAL": "0"}),
        ]
        for item in self.patches:
            item.start()

        controlServer._state.update(
            {"last_finished": 0.0, "last_result": None, "last_error": None}
        )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), controlServer.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/refresh"
        self.health_url = f"http://127.0.0.1:{self.server.server_port}/health"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()

    def post(self, token):
        request = urllib.request.Request(
            self.url,
            data=b"{}",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_rejects_bad_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("wrong")
        self.assertEqual(caught.exception.code, 401)

    def test_health_returns_status(self):
        request = urllib.request.Request(
            self.health_url,
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read())

        self.assertEqual(body["status"], "ok")

    def test_refresh_returns_counts(self):
        with self.post("secret") as response:
            self.assertEqual(response.status, 200)
            body = json.loads(response.read())

        self.assertEqual(body["changed"], 1)
        self.assertIn("duration_ms", body)


if __name__ == "__main__":
    unittest.main()
