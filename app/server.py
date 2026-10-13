"""HTTP layer. Standard library only, so the service runs on any clean Python 3.10+.

Routes are in the contract from section 3 of the brief, plus GET /health and
GET / for the page. Errors come back as JSON with a 4xx or 5xx status.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .catalogue import Catalogue, parse_whole_number

STATIC_DIR = Path(__file__).resolve().parent / "static"

_PART_RE = re.compile(r"/api/parts/([^/]+)")
_PATHS_RE = re.compile(r"/api/parts/([^/]+)/paths")
_SERIAL_RE = re.compile(r"/api/serial/([^/]+)")


def make_server(catalogue: Catalogue, host: str = "127.0.0.1", port: int = 8000):
    handler = _make_handler(catalogue)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def _make_handler(catalogue: Catalogue):
    index_html = (STATIC_DIR / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "PartsCatalogue/1.0"

        def do_GET(self):  # noqa: N802 (name fixed by http.server)
            path = urlsplit(self.path).path
            if len(path) > 1:
                path = path.rstrip("/")

            if path == "/":
                return self._send(200, index_html, "text/html; charset=utf-8")
            if path == "/health":
                return self._json(200, {"status": "ok"})
            if path == "/api/validation":
                return self._json(200, catalogue.validation())

            m = _PATHS_RE.fullmatch(path)
            if m:
                result = catalogue.paths(unquote(m.group(1)))
                if result is None:
                    return self._not_in_machine(unquote(m.group(1)))
                return self._json(200, result)

            m = _PART_RE.fullmatch(path)
            if m:
                result = catalogue.part(unquote(m.group(1)))
                if result is None:
                    return self._not_in_machine(unquote(m.group(1)))
                return self._json(200, result)

            m = _SERIAL_RE.fullmatch(path)
            if m:
                text = unquote(m.group(1))
                serial = parse_whole_number(text)
                if serial is None:
                    return self._json(
                        400, {"error": "serial must be a whole number", "received": text}
                    )
                return self._json(
                    200,
                    {"serial": serial, "applicable_parts": catalogue.applicable_parts(serial)},
                )

            return self._json(404, {"error": "not found", "path": path})

        def do_HEAD(self):  # noqa: N802
            self._json(405, {"error": "method not allowed"})

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD  # noqa: N815

        def _not_in_machine(self, part_number: str):
            return self._json(
                404, {"error": "part is not in this machine", "part_number": part_number}
            )

        def _json(self, status: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # keep test and console output quiet
            pass

    return Handler
