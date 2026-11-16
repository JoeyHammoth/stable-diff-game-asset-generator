"""The audio backend seam (docs/04-pipeline-stages.md §10).

Images and audio do not share a protocol, and pretending they do would mean threading a
sample rate through `GenerationRequest`. What they share is the *shape*: probe, produce
bytes, report what is missing with a remedy. This is that shape for audio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..backends.base import CapabilityGap
from ..canonical import hash_obj


@dataclass(frozen=True)
class AudioProfile:
    """What an audio backend is and can do.

    `profile_hash` enters the cache key, so switching from the offline synth to a soundfont
    invalidates cached renders instead of silently mixing two different instruments.
    """

    kind: str
    version: str = ""
    sample_rate: int = 32000
    gaps: tuple[CapabilityGap, ...] = ()

    @property
    def profile_hash(self) -> str:
        return hash_obj(
            {
                "kind": self.kind,
                "version": self.version,
                "sample_rate": self.sample_rate,
            }
        )

    @property
    def ok(self) -> bool:
        return not self.gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "version": self.version,
            "sample_rate": self.sample_rate,
            "gaps": [gap.to_dict() for gap in self.gaps],
            "profile_hash": self.profile_hash,
        }


@runtime_checkable
class AudioBackend(Protocol):
    """MIDI in, WAV out. Determinism is part of the contract, not a bonus."""

    # Read-only properties rather than mutable attributes: implementations are frozen
    # dataclasses, and a protocol member that promises settability cannot be satisfied by one.
    @property
    def kind(self) -> str: ...

    @property
    def sample_rate(self) -> int: ...

    def probe(self) -> AudioProfile:
        """Identity and capability. Never raises for a merely incomplete backend."""

    def render_melody(self, midi: Path, dest: Path, *, timbre: str = "pad") -> Path:
        """Render a MIDI phrase to 16-bit PCM WAV at `dest`, deterministically."""


__all__ = ["AudioBackend", "AudioProfile"]
