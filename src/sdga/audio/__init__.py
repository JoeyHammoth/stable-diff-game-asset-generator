"""Audio: the second domain (docs/04-pipeline-stages.md §10).

Pure Python, standard library only. `wav` and `midi` are the formats; `leitmotif` turns one
authored phrase into eight derived tracks; `ops` and `gates` are the audio analogues of the
image chain; `synth` is the offline instrument and `fluidsynth` the optional soundfont path.
"""

from __future__ import annotations

from pathlib import Path

from .base import AudioBackend, AudioProfile
from .fluidsynth import FluidSynthBackend
from .gates import (
    AUDIO_GATES,
    AudioGateContext,
    audio_clip,
    audio_loop_seam,
    audio_peak,
    beat_alignment,
    duration_exact,
    evaluate_audio,
)
from .leitmotif import (
    Key,
    TrackPlan,
    detect_key,
    resolve_music,
    tile_to_length,
    transform,
)
from .midi import MidiFile, Note, read_midi, write_midi
from .ops import fade_edges, loop_crossfade, loudness_normalize, mix, trim_silence
from .synth import SynthBackend, render_midi, render_sfx
from .wav import Audio, read_wav, write_wav


def build_audio_backend(kind: str, *, sample_rate: int, soundfont: str, root: Path) -> AudioBackend:
    """The configured audio backend. Paths are resolved against the project root only."""
    if kind == "synth":
        return SynthBackend(sample_rate=sample_rate)
    if kind == "fluidsynth":
        resolved = str(Path(root) / soundfont) if soundfont else ""
        return FluidSynthBackend(soundfont=resolved, sample_rate=sample_rate)
    raise ValueError(f"unknown audio backend {kind!r}; known kinds: synth, fluidsynth")


__all__ = [
    "AUDIO_GATES",
    "Audio",
    "AudioBackend",
    "AudioGateContext",
    "AudioProfile",
    "FluidSynthBackend",
    "Key",
    "MidiFile",
    "Note",
    "SynthBackend",
    "TrackPlan",
    "audio_clip",
    "audio_loop_seam",
    "audio_peak",
    "beat_alignment",
    "build_audio_backend",
    "detect_key",
    "duration_exact",
    "evaluate_audio",
    "fade_edges",
    "loop_crossfade",
    "loudness_normalize",
    "mix",
    "read_midi",
    "read_wav",
    "render_midi",
    "render_sfx",
    "resolve_music",
    "tile_to_length",
    "transform",
    "trim_silence",
    "write_midi",
    "write_wav",
]
