"""Minimal fake TorBox API server for integration tests.

Only the stdlib is used so the fixture has no test-only dependencies. It serves
the single endpoint the refresh path needs: ``GET /v1/api/<type>/mylist``.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class FakeTorBoxApi:
    """Serve scripted TorBox ``mylist`` responses on a local port.

    ``responses`` maps a download type (``torrents``, ``usenet``, ``webdl``) to
    either a list of API items or an integer HTTP status code. Types that are
    not listed return an empty ``data`` list, matching a real empty library.
    """

    def __init__(self, responses=None):
        self._responses = dict(responses or {})
        self._requests = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="fake-torbox-api",
        )

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_port}/v1/api"

    @property
    def requests(self):
        """Return the (path, query) pairs received so far."""
        with self._lock:
            return list(self._requests)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def _response_for(self, path):
        parts = path.strip("/").split("/")
        if (
            len(parts) != 4
            or parts[0] != "v1"
            or parts[1] != "api"
            or parts[3] != "mylist"
        ):
            return 404, {"error": "not found"}

        value = self._responses.get(parts[2], [])
        if isinstance(value, int):
            return value, {"error": f"forced {value}"}
        return 200, {"data": value, "success": True}

    def _handler_type(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlsplit(self.path)
                with api._lock:
                    api._requests.append((parsed.path, parsed.query))

                status, payload = api._response_for(parsed.path)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, fmt, *args):
                pass

        return Handler
