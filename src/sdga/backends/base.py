"""The backend seam (docs/01-architecture.md §4).

`GenerationBackend` is the only interface tests cross. Adaptees: `ComfyUIBackend` (phase P1)
and `FakeBackend`, which is not a test double for convenience but a real backend whose whole
job is deterministic, offline output.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..canonical import hash_obj
from ..model import GenerationRequest


class PollState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    vram_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "vram_total": self.vram_total}


@dataclass(frozen=True)
class CapabilityGap:
    """Something the backend declared it cannot do, with where to fix it."""

    kind: str  # node | model | input | recipe
    item: str
    detail: str = ""
    remedy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "item": self.item,
            "detail": self.detail,
            "remedy": self.remedy,
        }


@dataclass(frozen=True)
class BackendProfile:
    """What a backend reported at probe time. Recorded in every run.

    `profile_hash` covers identity and capability only — deliberately not `url`. Moving a
    backend to another host must not invalidate cached art.
    """

    kind: str
    url: str = ""
    comfyui_version: str = ""
    pytorch_version: str = ""
    devices: tuple[DeviceInfo, ...] = ()
    nodes: frozenset[str] = frozenset()
    models: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    gaps: tuple[CapabilityGap, ...] = ()

    @property
    def profile_hash(self) -> str:
        return hash_obj(
            {
                "kind": self.kind,
                "comfyui_version": self.comfyui_version,
                "pytorch_version": self.pytorch_version,
                "devices": [device.to_dict() for device in self.devices],
                "nodes": sorted(self.nodes),
                "models": {folder: sorted(names) for folder, names in self.models.items()},
            }
        )

    def has_node(self, name: str) -> bool:
        return name in self.nodes

    def has_model(self, folder: str, name: str) -> bool:
        return name in self.models.get(folder, ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "url": self.url,
            "comfyui_version": self.comfyui_version,
            "pytorch_version": self.pytorch_version,
            "devices": [device.to_dict() for device in self.devices],
            "nodes": sorted(self.nodes),
            "models": {folder: list(names) for folder, names in self.models.items()},
            "gaps": [gap.to_dict() for gap in self.gaps],
            "profile_hash": self.profile_hash,
        }


@dataclass(frozen=True)
class JobHandle:
    """A backend's reference to a submitted job. `prompt_id` is ours, not the server's."""

    prompt_id: str
    request_hash: str
    asset_id: str


@dataclass(frozen=True)
class ArtifactRef:
    filename: str
    subfolder: str = ""
    type: str = "output"

    def to_dict(self) -> dict[str, Any]:
        return {"filename": self.filename, "subfolder": self.subfolder, "type": self.type}


@dataclass(frozen=True)
class JobReport:
    state: PollState
    progress: float | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    message: str | None = None
    error: Mapping[str, Any] | None = None


@runtime_checkable
class GenerationBackend(Protocol):
    """Everything a backend must do. Nothing else crosses this seam."""

    kind: str

    def probe(self) -> BackendProfile:
        """Report identity and capability. Never raises for a merely incomplete backend."""

    def submit(self, request: GenerationRequest) -> JobHandle:
        """Queue one request. Idempotent for a given `request_hash`."""

    def poll(self, handle: JobHandle) -> JobReport:
        """`pending` | `running` | `succeeded` | `failed`, with progress when known."""

    def cancel(self, handle: JobHandle) -> None: ...

    def fetch(self, artifact: ArtifactRef, dest: Path) -> Path:
        """Write the artifact to `dest` and return the written path."""


__all__ = [
    "ArtifactRef",
    "BackendProfile",
    "CapabilityGap",
    "DeviceInfo",
    "GenerationBackend",
    "JobHandle",
    "JobReport",
    "PollState",
]
