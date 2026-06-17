from __future__ import annotations

import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from core.bilibili import BilibiliAudioStream


@dataclass(frozen=True)
class RegisteredBiliStream:
    stream: BilibiliAudioStream
    urls: list[str]


class BiliStreamProxy:
    def __init__(self) -> None:
        self._server: _BiliProxyServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = _BiliProxyServer(("127.0.0.1", 0), _BiliStreamProxyHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def register(self, stream: BilibiliAudioStream) -> str:
        self.start()
        if self._server is None:
            raise RuntimeError("Bili stream proxy failed to start")
        token = secrets.token_urlsafe(18)
        self._server.streams[token] = RegisteredBiliStream(stream=stream, urls=[stream.stream_url, *stream.backup_urls])
        host, port = self._server.server_address
        return f"http://{host}:{port}/stream/{token}"

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None


class _BiliProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(server_address, handler_class)
        self.streams: dict[str, RegisteredBiliStream] = {}


class _BiliStreamProxyHandler(BaseHTTPRequestHandler):
    server: _BiliProxyServer

    def do_GET(self) -> None:  # noqa: N802
        token = self._read_token()
        registered = self.server.streams.get(token)
        if registered is None:
            self.send_error(404)
            return

        last_error: Exception | None = None
        for url in registered.urls:
            try:
                self._proxy_url(url, registered.stream)
                return
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                continue

        self.send_error(502, str(last_error or "Bili stream unavailable"))

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_token(self) -> str:
        path = urllib.parse.urlparse(self.path).path
        prefix = "/stream/"
        if not path.startswith(prefix):
            return ""
        return path[len(prefix) :]

    def _proxy_url(self, url: str, stream: BilibiliAudioStream) -> None:
        headers = dict(stream.headers)
        incoming_range = self.headers.get("Range")
        if incoming_range:
            headers["Range"] = incoming_range

        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=12) as response:
            status = getattr(response, "status", 200)
            self.send_response(status)
            self._copy_header(response, "Content-Type")
            self._copy_header(response, "Content-Length")
            self._copy_header(response, "Content-Range")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            if self.command == "HEAD":
                return

            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _copy_header(self, response: Any, header: str) -> None:
        value = response.headers.get(header)
        if value:
            self.send_header(header, value)
