"""Audio samples and WAV I/O (docs/04-pipeline-stages.md §10).

Pure standard library: `wave` plus `array`. Not `soundfile`, not `numpy`. The audio layer
must install anywhere the image layer does, and CI has neither a DSP stack nor a GPU — an
audio post chain that needs numpy is a dependency the whole project pays for.

Samples are floats in [-1.0, 1.0], one tuple per channel. Files are written as 16-bit PCM,
which is what a game engine loads and what every gate measures; the header is produced by
`wave`, so the same samples always produce the same bytes. 8-bit and 16-bit PCM are read:
the former is what older tools and small SFX packs ship, and rejecting it forced a manual
conversion for no gain.
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

# Half-width of the windowed-sinc kernel, in zero crossings. Eight is enough to keep a
# texture bed clean at the rates a game project uses without turning resampling into a
# dependency on a DSP package.
RESAMPLE_RADIUS = 8


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
    """Read 8-bit or 16-bit PCM WAV. Anything else is an explicit error.

    A float32 or 24-bit file read as 16-bit sounds like noise, so the format is checked
    rather than assumed. 8-bit WAV is unsigned (`128` is silence); 16-bit is signed.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"{path.name}: not a readable WAV file ({exc})") from None
    if width not in (1, 2):
        raise ValueError(
            f"{path.name}: {width * 8}-bit audio is not supported; export 8-bit or 16-bit PCM WAV"
        )

    if width == 1:
        per_channel = len(frames) // channels if channels else 0
        split = [
            tuple(
                (frames[index * channels + channel] - 128) / 128.0 for index in range(per_channel)
            )
            for channel in range(channels)
        ]
    else:
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


def resample(audio: Audio, target_rate: int) -> Audio:
    """Band-limited resampling to `target_rate`, in pure Python.

    A bed service runs at its model's rate (often 32 kHz) while a project may ask for 44.1
    kHz. Refusing that combination made the service and the config share a hidden coupling;
    this function removes it. The windowed-sinc kernel is scaled by the lower of the two
    Nyquist limits, so downsampling is low-passed instead of aliased. Edge samples are
    clamped and weights are normalised, which keeps a constant signal constant.
    """
    if target_rate <= 0:
        raise ValueError(f"sample rate must be positive, got {target_rate}")
    if target_rate == audio.sample_rate:
        return audio
    if audio.frame_count == 0:
        return Audio(
            channels=tuple(() for _ in audio.channels),
            sample_rate=target_rate,
        )

    ratio = target_rate / audio.sample_rate
    frames = max(1, int(round(audio.frame_count * ratio)))
    cutoff = min(1.0, ratio)
    radius = max(2, int(math.ceil(RESAMPLE_RADIUS / cutoff)))
    limit = audio.frame_count - 1

    channels: list[tuple[float, ...]] = []
    for channel in audio.channels:
        output: list[float] = []
        for index in range(frames):
            position = index / ratio
            base = int(math.floor(position))
            total = 0.0
            norm = 0.0
            for offset in range(-radius, radius + 1):
                distance = position - (base + offset)
                if abs(distance) > radius:
                    continue
                sample_index = min(limit, max(0, base + offset))
                angle = distance * cutoff * math.pi
                sinc = 1.0 if abs(angle) < 1e-12 else math.sin(angle) / angle
                window = 0.5 + 0.5 * math.cos(math.pi * distance / radius)
                weight = cutoff * sinc * window
                total += channel[sample_index] * weight
                norm += weight
            output.append(total / norm if abs(norm) > 1e-12 else channel[min(limit, max(0, base))])
        channels.append(tuple(output))
    return Audio(channels=tuple(channels), sample_rate=target_rate)


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
    "RESAMPLE_RADIUS",
    "SILENCE_DBFS",
    "Audio",
    "db_to_gain",
    "gain_to_db",
    "read_wav",
    "resample",
    "write_wav",
]
