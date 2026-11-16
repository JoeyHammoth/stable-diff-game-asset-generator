"""The offline instrument: deterministic MIDI to WAV, and procedural SFX (T30, T35).

This is the audio counterpart of `FakeBackend`, and it is a real backend rather than a test
double: it renders an audible phrase, offline, with no soundfont and no binary to install, so
the whole audio pipeline is runnable in CI on a machine with no audio stack at all.

Determinism rules, the same ones the image side lives by: no wall clock, no `random`, no
floating RNG. Pitch comes from the MIDI, amplitude from the velocity, and noise (for SFX)
from a small integer LCG seeded by the request seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .base import AudioProfile
from .midi import MidiFile, read_midi
from .wav import Audio, write_wav

# Harmonic weights per timbre: (fundamental, 2nd, 3rd, 4th).
TIMBRE_HARMONICS: dict[str, tuple[float, ...]] = {
    "pad": (1.0, 0.35, 0.18, 0.07),
    "pluck": (1.0, 0.55, 0.22, 0.0),
    "bell": (1.0, 0.0, 0.55, 0.0),
    "bass": (1.0, 0.5, 0.0, 0.0),
}

_ATTACK_S = 0.006
_DECAY_S = 0.07
_SUSTAIN = 0.55
_RELEASE_S = 0.12
_HEADROOM = 0.85

_TABLE_BITS = 12
_TABLE_SIZE = 1 << _TABLE_BITS
_MASK = _TABLE_SIZE - 1
_TABLE = tuple(math.sin(2.0 * math.pi * index / _TABLE_SIZE) for index in range(_TABLE_SIZE))


def _sine(phase: float) -> float:
    """Wavetable sine with linear interpolation. ~20x faster than `math.sin` per sample."""
    position = (phase % 1.0) * _TABLE_SIZE
    index = int(position)
    fraction = position - index
    left = _TABLE[index & _MASK]
    right = _TABLE[(index + 1) & _MASK]
    return left + (right - left) * fraction


def _envelope(position_s: float, duration_s: float) -> float:
    if position_s < 0:
        return 0.0
    if position_s < _ATTACK_S:
        return position_s / _ATTACK_S
    if position_s < _ATTACK_S + _DECAY_S:
        into_decay = (position_s - _ATTACK_S) / _DECAY_S
        return 1.0 - (1.0 - _SUSTAIN) * into_decay
    if position_s < duration_s:
        return _SUSTAIN
    released = position_s - duration_s
    if released < _RELEASE_S:
        return _SUSTAIN * (1.0 - released / _RELEASE_S)
    return 0.0


def _midi_total_seconds(midi: MidiFile) -> float:
    seconds = midi.length_beats * 60.0 / midi.bpm
    return seconds + _RELEASE_S + 0.01


def render_midi(midi: MidiFile, *, sample_rate: int, timbre: str = "pad") -> Audio:
    """Sum every note into one mono buffer, then normalise down only if it would clip."""
    harmonics = TIMBRE_HARMONICS.get(timbre)
    if harmonics is None:
        raise ValueError(f"unknown timbre {timbre!r}; known: {', '.join(sorted(TIMBRE_HARMONICS))}")
    total_s = _midi_total_seconds(midi)
    frames = max(1, int(math.ceil(total_s * sample_rate)))
    buffer = [0.0] * frames
    seconds_per_beat = 60.0 / midi.bpm

    for note in midi.notes:
        frequency = 440.0 * (2.0 ** ((note.pitch - 69) / 12.0))
        start_s = note.start * seconds_per_beat
        duration_s = max(0.02, note.duration * seconds_per_beat)
        level = (max(1, min(127, note.velocity)) / 127.0) ** 1.2
        first = int(round(start_s * sample_rate))
        last = min(frames, int(round((start_s + duration_s + _RELEASE_S) * sample_rate)))
        phases = [0.0] * len(harmonics)
        increments = [frequency * (order + 1) / sample_rate for order in range(len(harmonics))]
        for index in range(first, last):
            position_s = (index - first) / sample_rate
            envelope = _envelope(position_s, duration_s)
            if envelope <= 0.0:
                continue
            value = 0.0
            for order, weight in enumerate(harmonics):
                if weight == 0.0:
                    continue
                value += weight * _sine(phases[order])
                phases[order] += increments[order]
            buffer[index] += value * envelope * level

    peak = max((abs(value) for value in buffer), default=0.0)
    if peak > _HEADROOM:
        scale = _HEADROOM / peak
        buffer = [value * scale for value in buffer]
    return Audio(channels=(tuple(buffer),), sample_rate=sample_rate)


@dataclass
class _Lcg:
    """A 32-bit linear congruential generator: identical noise on every platform and version."""

    state: int

    def next_float(self) -> float:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 0x100000000


def render_sfx(*, seed: int, duration_s: float, sample_rate: int) -> Audio:
    """A short procedural one-shot, chosen by the seed so it is stable and re-rollable.

    Not a model: when an AI one-shot backend is wired in, this becomes its offline fallback.
    The shape — a pitched body with a fast decay, sometimes noise on top — is enough for UI
    clicks and pickups, and it exercises the duration/peak/clip gates the real path shares.
    """
    if duration_s <= 0:
        raise ValueError("duration must be positive")
    rng = _Lcg(seed & 0xFFFFFFFF)
    family = seed % 4
    base = 180.0 + (seed % 600)
    sweep = (0.5, 1.0, 1.6, 2.4)[family]
    noise_mix = (0.0, 0.15, 0.35, 0.05)[family]
    frames = max(1, int(round(duration_s * sample_rate)))
    buffer: list[float] = []
    phase = 0.0
    for index in range(frames):
        progress = index / max(1, frames - 1)
        frequency = base * (sweep**progress)
        phase += frequency / sample_rate
        tone = _sine(phase)
        if family == 1:
            tone = 1.0 if tone >= 0 else -1.0  # square: a chip blip
        noise = rng.next_float() * 2.0 - 1.0
        envelope = math.exp(-5.0 * progress)
        buffer.append((tone * (1.0 - noise_mix) + noise * noise_mix) * envelope)

    peak = max(abs(value) for value in buffer)
    if peak > 0:
        scale = 0.8 / peak
        buffer = [value * scale for value in buffer]
    return Audio(channels=(tuple(buffer),), sample_rate=sample_rate)


@dataclass(frozen=True)
class SynthBackend:
    """The default audio backend: offline, deterministic, dependency-free."""

    sample_rate: int = 32000
    kind: str = "synth"

    def probe(self) -> AudioProfile:
        return AudioProfile(kind=self.kind, version="synth-1", sample_rate=self.sample_rate)

    def render_melody(self, midi: Path, dest: Path, *, timbre: str = "pad") -> Path:
        phrase = read_midi(Path(midi))
        audio = render_midi(phrase, sample_rate=self.sample_rate, timbre=timbre)
        return write_wav(Path(dest), audio)


__all__ = [
    "TIMBRE_HARMONICS",
    "SynthBackend",
    "render_midi",
    "render_sfx",
]
