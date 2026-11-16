"""Backing beds: texture under an authored melody (docs/04 §10 steps 3-4).

A bed is a *texture*, not a tune: the melody is mixed in afterwards, so a bed that invents
its own lead fights the leitmotif. That is why every music request's negative prompt already
forbids a lead melody, and why the mix is a fixed gain rather than "let the model blend it".

Two backends, one seam:

* `TextureBedBackend` — offline and deterministic. Sustained chord voices with slow amplitude
  drift and a filtered noise wash: no rhythm, no melody, no soundfont. It is what lets the
  whole bed path run in CI, and it is a real texture rather than silence.
* `MusicGenBackend` — a local MusicGen (AudioCraft) service over HTTP. In-process MusicGen
  would mean importing torch, which the pipeline never does, so the model lives behind a
  small service and this is its client. The contract is deliberately tiny:

      GET  {url}/health   -> {"model": "...", "sample_rate": 32000}
      POST {url}/generate -> WAV bytes, given
           {"prompt", "negative_prompt", "duration_s", "sample_rate", "seed"}

  Any wrapper around `audiocraft`'s generator can serve it. When the service is absent,
  `probe()` reports a gap with the remedy and `generate()` raises `missing_capability` — a
  soundtrack must not silently fall back to a different instrument.

A bed of the wrong duration is fitted by the caller (cut or padded to the loop length). A bed
of the wrong sample rate is resampled to the project rate: the melody stays sample-exact, and
the service is free to run at the model's native rate.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..backends.base import CapabilityGap
from ..errors import BackendError
from .base import AudioProfile
from .wav import Audio, read_wav, resample, write_wav

WAV_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})


@dataclass(frozen=True)
class BedRequest:
    """What a bed backend is asked for. The prompt already forbids a lead melody."""

    prompt: str
    negative: str
    duration_s: float
    seed: int
    sample_rate: int


@runtime_checkable
class BedBackend(Protocol):
    @property
    def kind(self) -> str: ...

    def probe(self) -> AudioProfile:
        """Identity and capability; a missing service is a gap, not an exception."""

    def generate(self, request: BedRequest, dest: Path) -> Path:
        """Write a WAV bed of roughly `duration_s`, at `sample_rate`."""


def midi_to_hz(pitch: float) -> float:
    return float(440.0 * (2.0 ** ((pitch - 69) / 12.0)))


@dataclass(frozen=True)
class TextureBedBackend:
    """Deterministic sustained texture: chord, slow drift, noise wash. No rhythm, no lead."""

    sample_rate: int = 32000
    kind: str = "texture"

    def probe(self) -> AudioProfile:
        return AudioProfile(kind=self.kind, version="texture-1", sample_rate=self.sample_rate)

    def generate(self, request: BedRequest, dest: Path) -> Path:
        if request.duration_s <= 0:
            raise BackendError(
                "bad_output", f"bed duration must be positive, got {request.duration_s}"
            )
        return write_wav(Path(dest), render_texture(request))


def render_texture(request: BedRequest) -> Audio:
    """A slow, chordal pad. The seed picks the root, the mode and the drift phases."""
    rate = request.sample_rate
    frames = max(1, int(round(request.duration_s * rate)))
    seed = request.seed & 0xFFFFFFFF
    root = 45 + seed % 12  # A2..Ab3: a bed sits under the melody, not on top of it
    intervals = (0, 3 if seed % 2 else 4, 7, 10 if seed % 3 else 12)
    voices = [
        (midi_to_hz(root + interval - 12), weight)
        for interval, weight in zip(intervals, (0.55, 0.30, 0.22, 0.12), strict=True)
    ]

    # Drift phases and rates derived from the seed, never from a clock.
    drifts = [
        (0.045 + ((seed >> (index * 3)) % 7) * 0.011, (seed >> (index * 5)) % 628 / 100.0)
        for index in range(len(voices))
    ]
    noise_state = (seed ^ 0x9E3779B9) & 0xFFFFFFFF
    filtered_noise = 0.0
    samples = [0.0] * frames

    for index in range(frames):
        seconds = index / rate
        value = 0.0
        for (frequency, weight), (drift_hz, phase) in zip(voices, drifts, strict=True):
            drift = 0.72 + 0.28 * math.sin(2.0 * math.pi * drift_hz * seconds + phase)
            value += weight * drift * math.sin(2.0 * math.pi * frequency * seconds)
        noise_state = (1664525 * noise_state + 1013904223) & 0xFFFFFFFF
        white = noise_state / 0x80000000 - 1.0
        # One-pole low pass: a wash, not hiss. Coefficient fixed, so it is reproducible.
        filtered_noise = filtered_noise * 0.999 + white * 0.001
        samples[index] = value + filtered_noise * 3.0

    peak = max((abs(value) for value in samples), default=0.0)
    scale = 0.35 / peak if peak > 0 else 0.0
    return Audio(channels=(tuple(value * scale for value in samples),), sample_rate=rate)


@dataclass(frozen=True)
class MusicGenBackend:
    """HTTP client for a local MusicGen service. No torch, no audiocraft import."""

    url: str = "http://127.0.0.1:8765"
    sample_rate: int = 32000
    timeout_s: float = 600.0
    kind: str = "musicgen"

    @property
    def base(self) -> str:
        return self.url.rstrip("/")

    def probe(self) -> AudioProfile:
        gaps: list[CapabilityGap] = []
        model = ""
        native_rate = self.sample_rate
        try:
            with urllib.request.urlopen(f"{self.base}/health", timeout=10) as response:
                info = json.loads(response.read() or b"{}")
            model = str(info.get("model") or "")
            reported = info.get("sample_rate")
            if reported is not None:
                try:
                    native_rate = int(reported)
                except (TypeError, ValueError):
                    gaps.append(
                        CapabilityGap(
                            kind="model",
                            item="sample rate",
                            detail=f"the service reported an invalid sample rate: {reported!r}",
                            remedy="the service must report an integer sample_rate in /health",
                        )
                    )
                else:
                    if native_rate <= 0:
                        gaps.append(
                            CapabilityGap(
                                kind="model",
                                item="sample rate",
                                detail=f"the service reported {native_rate} Hz",
                                remedy="the service must report a positive sample_rate in /health",
                            )
                        )
                        native_rate = self.sample_rate
        except (urllib.error.URLError, OSError, ValueError, TypeError) as exc:
            gaps.append(
                CapabilityGap(
                    kind="service",
                    item="musicgen",
                    detail=f"no MusicGen service at {self.base}: {exc}",
                    remedy=(
                        "start a MusicGen service that serves GET /health and POST /generate, "
                        "then set [audio] bed_url; or use [audio] bed = 'texture'"
                    ),
                )
            )
        return AudioProfile(
            kind=self.kind, version=model, sample_rate=native_rate, gaps=tuple(gaps)
        )

    def generate(self, request: BedRequest, dest: Path) -> Path:
        profile = self.probe()
        if not profile.ok:
            raise BackendError(
                "missing_capability",
                "; ".join(gap.detail for gap in profile.gaps),
                remedy="; ".join(gap.remedy for gap in profile.gaps if gap.remedy) or None,
            )
        # Ask the service for its native rate; resample the returned texture to the project's
        # rate below. This is what decouples a model's 32 kHz output from a 44.1 kHz project.
        service_rate = profile.sample_rate
        payload = json.dumps(
            {
                "prompt": request.prompt,
                "negative_prompt": request.negative,
                "duration_s": round(request.duration_s, 6),
                "sample_rate": service_rate,
                "seed": request.seed,
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.base}/generate",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_s) as response:
                content_type = response.headers.get_content_type()
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            raise BackendError(
                "execution_error",
                f"MusicGen returned HTTP {exc.code}: {detail or exc.reason}",
                remedy="check the service console; the request body is in this run's record",
            ) from None
        except (urllib.error.URLError, OSError) as exc:
            raise BackendError(
                "unreachable",
                f"MusicGen at {self.base} failed: {exc}",
                remedy="start the service, then re-run",
            ) from None

        if content_type not in WAV_TYPES or not body.startswith(b"RIFF"):
            raise BackendError(
                "bad_output",
                f"MusicGen returned {content_type!r} ({len(body)} bytes), not a WAV file",
                remedy="the service must answer POST /generate with audio/wav bytes",
            )

        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        audio = read_wav(target)
        if audio.sample_rate != request.sample_rate:
            write_wav(target, resample(audio, request.sample_rate))
        return target


@dataclass(frozen=True)
class NoBedBackend:
    """`bed = "none"`: the melody alone. The default, and a real choice rather than a gap."""

    kind: str = "none"
    sample_rate: int = 32000

    def probe(self) -> AudioProfile:
        return AudioProfile(kind=self.kind, version="", sample_rate=self.sample_rate)

    def generate(self, request: BedRequest, dest: Path) -> Path:
        raise BackendError(
            "missing_capability",
            "bed generation is disabled",
            remedy="set [audio] bed = 'texture' or 'musicgen'",
        )


def build_bed_backend(kind: str, *, url: str, sample_rate: int, timeout_s: float) -> BedBackend:
    if kind == "none":
        return NoBedBackend(sample_rate=sample_rate)
    if kind == "texture":
        return TextureBedBackend(sample_rate=sample_rate)
    if kind == "musicgen":
        return MusicGenBackend(url=url, sample_rate=sample_rate, timeout_s=timeout_s)
    raise ValueError(f"unknown bed backend {kind!r}; known: none, texture, musicgen")


__all__ = [
    "WAV_TYPES",
    "BedBackend",
    "BedRequest",
    "MusicGenBackend",
    "NoBedBackend",
    "TextureBedBackend",
    "build_bed_backend",
    "midi_to_hz",
    "render_texture",
]
