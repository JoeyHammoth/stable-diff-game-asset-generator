"""Backend implementations of the single generation seam."""

from __future__ import annotations

from .base import (
    ArtifactRef,
    BackendProfile,
    CapabilityGap,
    DeviceInfo,
    GenerationBackend,
    JobHandle,
    JobReport,
    PollState,
)
from .fake import FakeBackend

__all__ = [
    "ArtifactRef",
    "BackendProfile",
    "CapabilityGap",
    "DeviceInfo",
    "FakeBackend",
    "GenerationBackend",
    "JobHandle",
    "JobReport",
    "PollState",
]
