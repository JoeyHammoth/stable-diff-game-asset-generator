"""The ComfyUI adapter: the one class that knows ComfyUI exists.

`GET /history/{prompt_id}` is the source of truth for completion. The WebSocket is a
tracker that can notice a failure sooner, never one that can declare success.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from ...config import BackendConfig
from ...errors import BackendError
from ...model import GenerationRequest
from ..base import (
    ArtifactRef,
    BackendProfile,
    JobHandle,
    JobReport,
    PollState,
)
from .client import ComfyUIClient
from .probe import build_profile
from .progress import WebSocketTracker, open_websocket_frames


def prompt_id_for(request_hash: str) -> str:
    """Deterministic, so re-submitting after a crash reuses the same history entry."""
    return str(uuid5(NAMESPACE_URL, request_hash))


class ComfyUIBackend:
    kind = "comfyui"

    def __init__(
        self,
        config: BackendConfig,
        *,
        client: ComfyUIClient | None = None,
        tracker_factory: Callable[[str], WebSocketTracker | None] | None = None,
        client_id: str | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.config = config
        self._client = client or ComfyUIClient(config.url)
        self._client_id = client_id or f"sdga-{uuid4().hex[:12]}"
        self._jobs: dict[str, tuple[GenerationRequest, float]] = {}
        self._trackers: dict[str, WebSocketTracker] = {}
        self._tracker_factory = tracker_factory or self._default_tracker
        # References are uploaded by content address, so two assets sharing a style anchor
        # upload it once per process. `project_root` is only needed to read the bytes.
        self._project_root = project_root
        self._uploaded: dict[str, str] = {}

    # ------------------------------------------------------------------ seam

    def probe(self) -> BackendProfile:
        return build_profile(
            self._client.object_info(),
            self._client.system_stats(),
            url=self._client.base_url,
        )

    def submit(self, request: GenerationRequest) -> JobHandle:
        if not request.graph:
            raise BackendError(
                "rejected_graph",
                f"{request.asset_id}: the request has no bound graph",
                remedy="give the kind a recipe, then let `sdga plan` bind it",
            )

        prompt_id = prompt_id_for(request.request_hash)
        existing = self._jobs.get(prompt_id)
        if existing is not None:
            # Idempotent: the same request never queues twice in one process.
            return self._handle(request, prompt_id)

        self._upload_refs(request)
        self._client.submit(request.graph, prompt_id=prompt_id, client_id=self._client_id)
        self._jobs[prompt_id] = (request, time.monotonic())
        tracker = self._tracker_factory(prompt_id)
        if tracker is not None:
            self._trackers[prompt_id] = tracker
        return self._handle(request, prompt_id)

    def poll(self, handle: JobHandle) -> JobReport:
        entry = self._jobs.get(handle.prompt_id)
        if entry is None:
            raise BackendError(
                "bad_output",
                f"no such job: {handle.prompt_id}",
                remedy="submit the request before polling it",
            )
        request, started_at = entry

        tracker = self._trackers.get(handle.prompt_id)
        if tracker is not None:
            terminal = tracker.poll()
            if terminal is not None and terminal.kind == "error":
                return JobReport(
                    state=PollState.FAILED,
                    message=terminal.message or "execution_error",
                    error={"kind": "execution_error", **terminal.to_dict()},
                )

        record = self._client.history(handle.prompt_id).get(handle.prompt_id)
        if record is None:
            elapsed = time.monotonic() - started_at
            if elapsed > self.config.timeout_s:
                raise BackendError(
                    "timeout",
                    f"{handle.asset_id}: no terminal event within {self.config.timeout_s}s",
                    remedy="raise [backend] timeout_s, or check the ComfyUI console",
                )
            return JobReport(state=PollState.RUNNING)
        return self._report_from_history(request, record)

    def cancel(self, handle: JobHandle) -> None:
        self._client.interrupt()

    def fetch(self, artifact: ArtifactRef, dest: Path) -> Path:
        payload = self._client.view(artifact.filename, artifact.subfolder, artifact.type)
        if not payload:
            raise BackendError("bad_output", f"/view returned no bytes for {artifact.filename!r}")
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    # ------------------------------------------------------------------ internals

    def _upload_refs(self, request: GenerationRequest) -> None:
        """Upload every reference once, under its content-addressed handle.

        Skipping a handle already uploaded in this process is what makes "two assets share a
        style anchor, upload once" true; the handle is stable across processes too, because
        it is derived from the bytes rather than from a counter.
        """
        if self._project_root is None:
            return
        for ref in request.refs:
            if not ref.backend_handle or ref.backend_handle in self._uploaded:
                continue
            source = self._project_root / ref.path
            if not source.is_file():
                raise BackendError(
                    "bad_output",
                    f"{request.asset_id}: reference {ref.path} is missing from the project",
                    remedy="restore the file, then re-plan",
                )
            self._client.upload_image(source, name=ref.backend_handle)
            self._uploaded[ref.backend_handle] = ref.sha256

    def _handle(self, request: GenerationRequest, prompt_id: str) -> JobHandle:
        return JobHandle(
            prompt_id=prompt_id,
            request_hash=request.request_hash,
            asset_id=request.asset_id,
        )

    def _report_from_history(
        self, request: GenerationRequest, record: Mapping[str, Any]
    ) -> JobReport:
        status = record.get("status") or {}
        if isinstance(status, dict) and status.get("status_str") == "error":
            message = _error_message(status)
            return JobReport(
                state=PollState.FAILED,
                message=message,
                error={"kind": "execution_error", "message": message},
            )

        outputs = record.get("outputs") or {}
        node_output = outputs.get(str(request.output_node)) if outputs else None
        if not node_output or not node_output.get("images"):
            if isinstance(status, dict) and status.get("completed") is False:
                return JobReport(state=PollState.RUNNING)
            raise BackendError(
                "bad_output",
                f"{request.asset_id}: output node {request.output_node!r} produced no image",
                payload={"output_nodes": sorted(str(key) for key in outputs)},
                remedy="the recipe's output_node must name the node whose image is the asset",
            )

        image = node_output["images"][0]
        artifact = ArtifactRef(
            filename=str(image["filename"]),
            subfolder=str(image.get("subfolder", "")),
            type=str(image.get("type", "output")),
        )
        return JobReport(state=PollState.SUCCEEDED, progress=1.0, artifacts=(artifact,))

    def _default_tracker(self, prompt_id: str) -> WebSocketTracker | None:
        if not self.config.ws_url:
            return None
        try:
            frames = open_websocket_frames(self.config.ws_url, self._client_id)
        except Exception:  # noqa: BLE001 - a tracker is an optimisation, never a failure
            # A missing library or an unreachable socket must degrade to polling, not
            # abort a submission.
            return None
        if frames is None:
            return None
        return WebSocketTracker(prompt_id, lambda: frames)


def _error_message(status: Mapping[str, Any]) -> str:
    for message in status.get("messages") or ():
        if not isinstance(message, (list, tuple)) or len(message) < 2:
            continue
        name, payload = message[0], message[1]
        if name == "execution_error" and isinstance(payload, dict):
            node = payload.get("node_id")
            node_type = payload.get("node_type")
            text = payload.get("exception_message") or "execution error"
            return f"node {node} ({node_type}): {text}".strip()
    return "execution_error"


__all__ = ["ComfyUIBackend", "prompt_id_for"]
