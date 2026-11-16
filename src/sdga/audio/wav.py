"""Audio samples and WAV I/O (docs/04-pipeline-stages.md §10).

Pure standard library: `wave` plus `array`. Not `soundfile`, not `numpy`. The audio layer
must install anywhere the image layer does, and CI has neither a DSP stack nor a GPU — an
audio post chain that needs numpy is a dependency the whole project pays for.

Samples are floats in [-1.0, 1.0], one tuple per channel. Files are written as 16-bit PCM,
which is what a game engine loads and what every gate measures; the header is produced by
`wave`, so the same samples always produce the same bytes.
"""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

PCM_MAX = 32767
PCM_MIN = -32768

# A digital-silence floor, named because `-inf` is not JSON and not printable in a gate row.
SILENCE_DBFS = -999.0


@dataclass(frozen=True)
class Audio:
    """Interleaved-by-channel samples. Immutable, so an op cannot alter its input."""

    channels: tuple[tuple[float, ...], ...]
    sample_rate: int

    def __post_init__(self) -> None:
        if not self.channels:
            raise ValueError("audio needs at least one channel")
        if self.sample_rate <= 0:
            raise ValueError(f"sample rate must be positive, got {self.sample_rate}")
        lengths = {len(channel) for channel in self.channels}
        if len(lengths) != 1:
            raise ValueError(f"channels differ in length: {sorted(lengths)}")

    @property
    def frame_count(self) -> int:
        return len(self.channels[0])

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.sample_rate

    def mono(self) -> tuple[float, ...]:
        """The channel average: every gate measures this, so a stereo file cannot pass by
        having one silent channel."""
        if self.channel_count == 1:
            return self.channels[0]
        count = self.channel_count
        return tuple(sum(frame) / count for frame in zip(*self.channels, strict=True))

    def peak(self) -> float:
        return max((max(abs(value) for value in channel) for channel in self.channels), default=0.0)

    def peak_dbfs(self) -> float:
        return gain_to_db(self.peak())

    def rms(self) -> float:
        samples = self.mono()
        if not samples:
            return 0.0
        return math.sqrt(sum(value * value for value in samples) / len(samples))

    def slice_samples(self, start: int, end: int) -> Audio:
        """Frames `[start, end)`, clamped to the file. Used by ops and gates alike."""
        low = max(0, start)
        high = min(self.frame_count, max(low, end))
        return Audio(
            channels=tuple(channel[low:high] for channel in self.channels),
            sample_rate=self.sample_rate,
        )

    def scaled(self, gain: float) -> Audio:
        return Audio(
            channels=tuple(tuple(value * gain for value in channel) for channel in self.channels),
            sample_rate=self.sample_rate,
        )


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(amplitude: float) -> float:
    if amplitude <= 0.0:
        return SILENCE_DBFS
    return 20.0 * math.log10(amplitude)


def read_wav(path: Path) -> Audio:
    """Read a 16-bit PCM WAV. Anything else is an explicit error, never a reinterpretation.

    A float32 or 24-bit file read as 16-bit sounds like noise, so the format is checked
    rather than assumed.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"{path.name}: not a readable WAV file ({exc})") from None
    if width != 2:
        raise ValueError(
            f"{path.name}: {width * 8}-bit audio is not supported; export 16-bit PCM WAV"
        )

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()  # WAV is little-endian; array('h') is native.

    per_channel = len(samples) // channels if channels else 0
    split = [
        tuple(samples[index * channels + channel] / PCM_MAX for index in range(per_channel))
        for channel in range(channels)
    ]
    return Audio(channels=tuple(split), sample_rate=rate)


def write_wav(path: Path, audio: Audio, *, sample_rate: int | None = None) -> Path:
    """Write 16-bit PCM. Clamps rather than wraps: an over-hot sample must not become a click."""
    rate = sample_rate or audio.sample_rate
    channels = audio.channel_count
    frames = audio.frame_count
    interleaved = array("h")
    for index in range(frames):
        for channel in audio.channels:
            value = channel[index]
            clamped = max(-1.0, min(1.0, value))
            interleaved.append(max(PCM_MIN, min(PCM_MAX, int(round(clamped * PCM_MAX)))))
    if sys.byteorder == "big":
        interleaved.byteswap()

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(interleaved.tobytes())
    return path


__all__ = [
    "PCM_MAX",
    "SILENCE_DBFS",
    "Audio",
    "db_to_gain",
    "gain_to_db",
    "read_wav",
    "write_wav",
]
