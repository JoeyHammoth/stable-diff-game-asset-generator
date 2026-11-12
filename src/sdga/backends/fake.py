"""A deterministic in-process backend: no GPU, no network, no ComfyUI.

This is what lets the whole pipeline run in CI and what catches seam and planning bugs
before a model is ever loaded. It is not a mock of `ComfyUIBackend`; it is an independent
implementation of the same protocol, which is the point.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from PIL import Image

from ..errors import BackendError
from ..model import GenerationRequest
from .base import (
    ArtifactRef,
    BackendProfile,
    CapabilityGap,
    JobHandle,
    JobReport,
    PollState,
)

DEFAULT_NODES = frozenset(
    {
        "CheckpointLoaderSimple",
        "LoraLoader",
        "CLIPTextEncode",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
        "ImageScale",
        "ControlNetApplyAdvanced",
        "IPAdapterAdvanced",
        "CannyEdgePreprocessor",
        "OpenposePreprocessor",
    }
)

DEFAULT_MODELS: dict[str, tuple[str, ...]] = {
    "checkpoints": ("sd_v1-5.safetensors",),
    "loras": ("example_style.safetensors",),
}

# Four tones from a muted moss ramp. Palette-exactness is not this backend's job; the
# postprocess chain (phase P1) is what guarantees the palette.
_TONES = ((31, 34, 41), (58, 99, 64), (120, 164, 96), (198, 214, 163))


@dataclass
class _Job:
    request: GenerationRequest
    submitted_at: float
    artifact: ArtifactRef


@dataclass
class FakeBackend:
    """Deterministic output derived from `request.seed`, never from wall-clock or RNG."""

    nodes: frozenset[str] = DEFAULT_NODES
    models: Mapping[str, Sequence[str]] = field(default_factory=lambda: DEFAULT_MODELS)
    gaps: tuple[CapabilityGap, ...] = ()
    delay_s: float = 0.0
    kind: str = "fake"

    def __post_init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._requests: dict[str, GenerationRequest] = {}

    def probe(self) -> BackendProfile:
        return BackendProfile(
            kind=self.kind,
            url="fake://local",
            comfyui_version="fake-0.0.0",
            pytorch_version="none",
            devices=(),
            nodes=frozenset(self.nodes),
            models={folder: tuple(names) for folder, names in self.models.items()},
            gaps=tuple(self.gaps),
        )

    def submit(self, request: GenerationRequest) -> JobHandle:
        if request.size is None:
            raise BackendError(
                "rejected_graph",
                f"{request.asset_id} has no render size",
                remedy="audio assets need the audio backend (phase P4), not the image backend",
            )
        prompt_id = str(uuid5(NAMESPACE_URL, request.request_hash))
        artifact = ArtifactRef(
            filename=f"{request.asset_id.replace('/', '__')}__{request.seed}.png",
            subfolder="",
            type="output",
        )
        self._jobs[prompt_id] = _Job(
            request=request, submitted_at=time.monotonic(), artifact=artifact
        )
        self._requests[artifact.filename] = request
        return JobHandle(
            prompt_id=prompt_id,
            request_hash=request.request_hash,
            asset_id=request.asset_id,
        )

    def poll(self, handle: JobHandle) -> JobReport:
        job = self._jobs.get(handle.prompt_id)
        if job is None:
            raise BackendError(
                "bad_output",
                f"no such job: {handle.prompt_id}",
                remedy="submit the request before polling it",
            )
        if self.delay_s > 0:
            elapsed = time.monotonic() - job.submitted_at
            if elapsed < self.delay_s:
                return JobReport(
                    state=PollState.RUNNING, progress=min(0.99, elapsed / self.delay_s)
                )
        return JobReport(state=PollState.SUCCEEDED, progress=1.0, artifacts=(job.artifact,))

    def cancel(self, handle: JobHandle) -> None:
        self._jobs.pop(handle.prompt_id, None)

    def fetch(self, artifact: ArtifactRef, dest: Path) -> Path:
        request = self._requests.get(artifact.filename)
        if request is None:
            raise BackendError(
                "bad_output", f"unknown artifact: {artifact.filename}"
            )
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        _render(request).save(target, format="PNG", optimize=False)
        return target


def _render(request: GenerationRequest) -> Image.Image:
    """A two-tone checkerboard, offset by the seed.

    Period 2 is not arbitrary: it is genuinely seam-continuous, so `seamless_tile`
    measures the same thing it would on a real tile instead of failing on the fake.
    """
    assert request.size is not None  # guarded in submit()
    width, height = request.size
    image = Image.new("RGB", (width, height))
    tones = _TONES
    pair = (tones[request.seed % len(tones)], tones[(request.seed + 1) % len(tones)])
    image.putdata(
        [pair[(x + y) % 2] for y in range(height) for x in range(width)]
    )
    return image


__all__ = ["DEFAULT_MODELS", "DEFAULT_NODES", "FakeBackend"]
