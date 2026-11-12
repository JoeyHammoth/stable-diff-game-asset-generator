"""Progress tracking, with the binary-frame trap handled explicitly.

ComfyUI sends preview images over the same WebSocket as JSON events. The source guide's
`json.loads(ws.recv())` therefore crashes on real traffic, which is why `parse_event` treats
every non-text frame as "not interesting" and why a tracker failure is never allowed to
decide that a job failed.

The socket is an optimisation. `GET /history` remains the source of truth, so polling-only
operation is correct, just slower to notice.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Terminal:
    kind: str  # completed | error
    node_id: str | None = None
    node_type: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"kind": self.kind}
        if self.node_id:
            body["node_id"] = self.node_id
        if self.node_type:
            body["node_type"] = self.node_type
        if self.message:
            body["message"] = self.message
        return body


def parse_event(raw: Any, prompt_id: str) -> Terminal | None:
    """Interpret one WebSocket message. Returns a terminal state or None."""
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return None  # a preview image frame; never text
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
    elif isinstance(raw, dict):
        payload = raw
    else:
        return None

    if not isinstance(payload, dict):
        return None

    kind = payload.get("type")
    data = payload.get("data") or {}

    if kind == "executing":
        event_id = data.get("prompt_id")
        if event_id and event_id != prompt_id:
            return None
        if data.get("node") is None:
            return Terminal("completed")
        return None

    if kind == "execution_error":
        event_id = data.get("prompt_id")
        if event_id and event_id != prompt_id:
            return None
        return Terminal(
            "error",
            node_id=data.get("node_id"),
            node_type=data.get("node_type"),
            message=data.get("exception_message"),
        )

    return None


class WebSocketTracker:
    """Drains a message source and remembers the first terminal state it sees.

    `frames` is injected, so the binary-frame and execution_error paths are tested without
    a socket. A raising source disables the tracker and falls back to polling.
    """

    def __init__(self, prompt_id: str, frames: Callable[[], Iterable[Any]] | None = None) -> None:
        self._prompt_id = prompt_id
        self._frames = frames
        self._terminal: Terminal | None = None
        self._broken = frames is None

    def poll(self) -> Terminal | None:
        if self._terminal is not None or self._broken or self._frames is None:
            return self._terminal
        try:
            for raw in self._frames():
                terminal = parse_event(raw, self._prompt_id)
                if terminal is not None:
                    self._terminal = terminal
                    break
        except OSError:
            # A dropped socket means "use polling", never "the job failed".
            self._broken = True
        return self._terminal


def open_websocket_frames(ws_url: str, client_id: str) -> Iterator[Any] | None:
    """Best-effort message iterator. Returns None when no websocket library is installed.

    `websocket-client` is an optional dependency: without it the pipeline polls.
    """
    try:
        import websocket  # type: ignore[import-not-found]
    except ImportError:
        return None

    url = f"{ws_url}?clientId={client_id}"
    connection = websocket.create_connection(url, timeout=5)
    return (message for message in iter(lambda: connection.recv(), None))


__all__ = ["Terminal", "WebSocketTracker", "open_websocket_frames", "parse_event"]
