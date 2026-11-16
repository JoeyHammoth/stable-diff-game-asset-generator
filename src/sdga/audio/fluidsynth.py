"""The soundfont path: MIDI through FluidSynth, when a soundfont is installed (T30).

Optional by design. It is the one audio backend that can sound like an orchestra, and the one
that needs two things this machine may not have: the `fluidsynth` binary and a `.sf2` bank.
Both are reported as `CapabilityGap`s at probe time, with the remedy, so `sdga doctor` says
"install this here" instead of the run failing halfway through a soundtrack.

Determinism: given the same binary, soundfont and MIDI, FluidSynth's fast render (`-F`) is
sample-identical. `profile_hash` therefore includes the backend name and the soundfont path,
so switching soundfonts invalidates cache entries rather than mixing two instruments.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..backends.base import CapabilityGap
from ..errors import BackendError
from .base import AudioProfile


@dataclass(frozen=True)
class FluidSynthBackend:
    soundfont: str = ""
    sample_rate: int = 32000
    binary: str = "fluidsynth"
    kind: str = "fluidsynth"

    @property
    def _executable(self) -> str | None:
        return shutil.which(self.binary)

    def _gaps(self) -> tuple[CapabilityGap, ...]:
        gaps: list[CapabilityGap] = []
        if self._executable is None:
            gaps.append(
                CapabilityGap(
                    kind="tool",
                    item=self.binary,
                    detail=f"{self.binary!r} is not on PATH",
                    remedy=(
                        "install FluidSynth and put it on PATH, or set [audio] kind = 'synth' "
                        "for the offline instrument"
                    ),
                )
            )
        if not self.soundfont:
            gaps.append(
                CapabilityGap(
                    kind="model",
                    item="soundfont",
                    detail="[audio] soundfont is empty",
                    remedy="point [audio] soundfont at a project-relative .sf2 file",
                )
            )
        elif not Path(self.soundfont).is_file():
            gaps.append(
                CapabilityGap(
                    kind="model",
                    item=Path(self.soundfont).name,
                    detail=f"soundfont not found: {self.soundfont}",
                    remedy="copy the .sf2 into the project, or fix [audio] soundfont",
                )
            )
        return tuple(gaps)

    def _version(self) -> str:
        executable = self._executable
        if executable is None:
            return ""
        try:
            completed = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        first = (completed.stdout or completed.stderr or "").strip().splitlines()
        return first[0] if first else ""

    def probe(self) -> AudioProfile:
        return AudioProfile(
            kind=self.kind,
            version=self._version(),
            sample_rate=self.sample_rate,
            gaps=self._gaps(),
        )

    def render_melody(self, midi: Path, dest: Path, *, timbre: str = "pad") -> Path:
        """`timbre` is ignored: the soundfont decides the instrument. Recorded, not silent."""
        gaps = self._gaps()
        if gaps:
            raise BackendError(
                "missing_capability",
                "; ".join(gap.detail for gap in gaps),
                remedy="; ".join(gap.remedy for gap in gaps if gap.remedy) or None,
            )
        executable = self._executable
        assert executable is not None  # guarded above

        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            executable,
            "-ni",
            "-F",
            str(target),
            "-r",
            str(self.sample_rate),
            self.soundfont,
            str(midi),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackendError(
                "execution_error",
                f"fluidsynth could not run: {exc}",
                remedy="check that the binary and the soundfont are both readable",
            ) from None
        if completed.returncode != 0 or not target.is_file():
            detail = (completed.stderr or completed.stdout or "").strip()[:300]
            raise BackendError(
                "execution_error",
                f"fluidsynth exited {completed.returncode}: {detail or 'no output'}",
                remedy="run the same command by hand to see the full error",
            )
        return target


__all__ = ["FluidSynthBackend"]
