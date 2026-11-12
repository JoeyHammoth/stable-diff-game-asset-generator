"""A local HTTP server that replays recorded ComfyUI responses.

Tests run the real `ComfyUIClient` against this, so URL building, JSON serialisation,
multipart bodies and error mapping are all exercised. Mocks of the client would drift from
the API; a replay server cannot.
"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "backend"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def checkerboard_png(size: tuple[int, int] = (512, 512)) -> bytes:
    """A 512px render stand-in: period-2, so it is genuinely seamless when downscaled."""
    width, height = size
    tones = ((31, 34, 41), (58, 99, 64))
    image = Image.new("RGB", size)
    image.putdata([tones[(x + y) % 2] for y in range(height) for x in range(width)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ReplayServer:
    def __init__(
        self,
        *,
        object_info: dict | None = None,
        system_stats: dict | None = None,
        history: dict | None = None,
        view_bytes: bytes | None = None,
        prompt_status: int = 200,
        prompt_body: dict | None = None,
    ) -> None:
        self.object_info = object_info if object_info is not None else load("object_info.json")
        self.system_stats = system_stats if system_stats is not None else load("system_stats.json")
        self.history = history if history is not None else load("history_success.json")
        self.view_bytes = view_bytes if view_bytes is not None else checkerboard_png()
        self.prompt_status = prompt_status
        self.prompt_body = prompt_body if prompt_body is not None else load(
            "prompt_400_node_errors.json"
        )
        self.prompt_requests: list[dict[str, Any]] = []
        self.post_requests: list[tuple[str, bytes]] = []
        self.view_queries: list[dict[str, list[str]]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "ReplayServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        replay = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:  # silence test output
                pass

            def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server API
                parsed = urlparse(self.path)
                if parsed.path == "/object_info":
                    self._send(200, json.dumps(replay.object_info).encode())
                    return
                if parsed.path == "/system_stats":
                    self._send(200, json.dumps(replay.system_stats).encode())
                    return
                if parsed.path.startswith("/history/"):
                    prompt_id = parsed.path.rsplit("/", 1)[-1]
                    payload = json.loads(
                        json.dumps(replay.history).replace("__PROMPT_ID__", prompt_id)
                    )
                    self._send(200, json.dumps(payload).encode())
                    return
                if parsed.path == "/view":
                    replay.view_queries.append(parse_qs(parsed.query))
                    self._send(200, replay.view_bytes, "image/png")
                    return
                self._send(404, b"{}")

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                replay.post_requests.append((self.path, raw))
                if self.path == "/prompt":
                    try:
                        payload = json.loads(raw.decode("utf-8") or "{}")
                    except ValueError:
                        payload = {}
                    replay.prompt_requests.append(payload)
                    if replay.prompt_status != 200:
                        self._send(
                            replay.prompt_status, json.dumps(replay.prompt_body).encode()
                        )
                        return
                    self._send(
                        200,
                        json.dumps(
                            {
                                "prompt_id": payload.get("prompt_id"),
                                "number": len(replay.prompt_requests),
                                "node_errors": {},
                            }
                        ).encode(),
                    )
                    return
                self._send(200, b"{}")

        return Handler


__all__ = ["FIXTURES", "ReplayServer", "checkerboard_png", "load"]
