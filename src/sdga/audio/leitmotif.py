"""Leitmotif transforms and the per-track plan (docs/04 §10, tickets T31/T34).

The guarantee this module exists for: every track in a soundtrack is a *derivation* of one
authored phrase, so they cannot drift apart. That means three things, in order:

1. the source key is **detected** from the MIDI, never assumed to be C;
2. transposition moves by **scale degrees**, so a minor third stays a minor third instead of
   being snapped to the nearest semitone of a hardcoded scale (gap analysis A5);
3. the track length is **solved** from bars, beats and tempo, not copied from a file's
   length, so a loop is bar-aligned by construction.

The transform is deliberately small: fragment selection, diatonic transposition, tempo scale.
An arpeggiator or a chord generator would be composition, and composition is the human's job.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..canonical import hash_file
from ..errors import SpecError
from ..paths import relative_path
from .midi import MidiFile, Note

MAJOR = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR = (0, 2, 3, 5, 7, 8, 10)

SCALES: Mapping[str, tuple[int, ...]] = {"major": MAJOR, "minor": NATURAL_MINOR}

# Krumhansl-Kessler key profiles. Correlating a duration-weighted pitch-class histogram
# against all 24 rotations is the standard, deterministic way to name a key.
_MAJOR_PROFILE = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_MINOR_PROFILE = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

TIMBRES = ("pad", "pluck", "bell", "bass")

MUSIC_KEYS = frozenset(
    {
        "leitmotif",
        "bars",
        "bpm",
        "beats_per_bar",
        "transpose",
        "tempo_scale",
        "fragment",
        "fragment_bars",
        "timbre",
        "loop_crossfade_s",
        "melody_gain_db",
    }
)


@dataclass(frozen=True)
class Key:
    tonic: int  # pitch class, 0 = C
    mode: str = "major"

    @property
    def scale(self) -> tuple[int, ...]:
        return SCALES[self.mode]

    @property
    def name(self) -> str:
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        return f"{names[self.tonic % 12]} {self.mode}"

    def to_dict(self) -> dict[str, Any]:
        return {"tonic": self.tonic, "mode": self.mode, "name": self.name}


@dataclass(frozen=True)
class TrackPlan:
    """Loop arithmetic, solved rather than assumed (gap analysis M3).

    `render_s` is what the instrument must produce: the loop length *plus* the crossfade,
    because `loop_crossfade` shortens the file by exactly the fade. Getting this backwards is
    how a "16-second loop" ends up 15.5 seconds long.
    """

    bars: int
    beats_per_bar: int
    bpm: float
    crossfade_s: float

    def __post_init__(self) -> None:
        if self.bars < 1:
            raise ValueError(f"bars must be >= 1, got {self.bars}")
        if self.beats_per_bar < 1:
            raise ValueError(f"beats_per_bar must be >= 1, got {self.beats_per_bar}")
        if self.bpm <= 0:
            raise ValueError(f"bpm must be positive, got {self.bpm}")
        if self.crossfade_s < 0:
            raise ValueError(f"loop_crossfade_s must be >= 0, got {self.crossfade_s}")
        if self.crossfade_s >= self.target_s:
            raise ValueError(
                f"loop_crossfade_s ({self.crossfade_s}s) must be shorter than the loop "
                f"({self.target_s:.3f}s)"
            )

    @property
    def target_s(self) -> float:
        """The bar-aligned loop length: `bars * beats * 60 / bpm`, exactly."""
        return self.bars * self.beats_per_bar * 60.0 / self.bpm

    @property
    def render_s(self) -> float:
        return self.target_s + self.crossfade_s

    @property
    def target_beats(self) -> float:
        return self.bars * self.beats_per_bar

    def to_dict(self) -> dict[str, Any]:
        return {
            "bars": self.bars,
            "beats_per_bar": self.beats_per_bar,
            "bpm": self.bpm,
            "crossfade_s": self.crossfade_s,
            "target_s": round(self.target_s, 6),
            "render_s": round(self.render_s, 6),
        }


def _histogram(midi: MidiFile) -> tuple[float, ...]:
    weights = [0.0] * 12
    for note in midi.notes:
        weights[note.pitch % 12] += max(note.duration, 1e-6)
    return tuple(weights)


def _correlation(values: tuple[float, ...], profile: tuple[float, ...]) -> float:
    count = len(values)
    mean_v = sum(values) / count
    mean_p = sum(profile) / count
    numerator = sum((v - mean_v) * (p - mean_p) for v, p in zip(values, profile, strict=True))
    left = sum((v - mean_v) ** 2 for v in values) ** 0.5
    right = sum((p - mean_p) ** 2 for p in profile) ** 0.5
    if left == 0 or right == 0:
        return -2.0
    return float(numerator / (left * right))


def detect_key(midi: MidiFile) -> Key:
    """Name the key by correlating the phrase's pitch classes with all 24 key profiles.

    Deterministic tie-break: highest correlation, then lower tonic, then major before minor.
    """
    histogram = _histogram(midi)
    if not any(histogram):
        raise ValueError("cannot detect a key: the phrase has no notes")

    best: tuple[float, int, int, Key] | None = None
    for tonic in range(12):
        rotated_major = tuple(_MAJOR_PROFILE[(pitch - tonic) % 12] for pitch in range(12))
        rotated_minor = tuple(_MINOR_PROFILE[(pitch - tonic) % 12] for pitch in range(12))
        for mode, profile, rank in (("major", rotated_major, 0), ("minor", rotated_minor, 1)):
            score = _correlation(histogram, profile)
            candidate = (score, -tonic, -rank, Key(tonic=tonic, mode=mode))
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    assert best is not None
    return best[3]


def _scale_step_semitones(key: Key, degrees: int) -> int:
    """Semitones spanned by `degrees` scale steps, so a chromatic note shifts in context."""
    scale = key.scale
    whole, remainder = divmod(degrees, len(scale))
    return whole * 12 + scale[remainder] - scale[0]


def transpose_diatonic(pitch: int, key: Key, degrees: int) -> int:
    """Move a pitch by scale degrees within the key, keeping chromatic tones chromatic.

    A note outside the scale keeps its own alteration: it is shifted by the interval the
    degree move spans, so a blue note stays blue instead of being quantised into the scale.
    """
    if degrees == 0:
        return pitch
    scale = key.scale
    relative = (pitch - key.tonic) % 12
    octave = (pitch - key.tonic) // 12
    if relative in scale:
        degree = scale.index(relative)
        total = degree + degrees
        steps, position = divmod(total, len(scale))
        semitone = key.tonic + 12 * (octave + steps) + scale[position]
    else:
        semitone = pitch + _scale_step_semitones(key, degrees)
    return max(0, min(127, semitone))


def transform(
    midi: MidiFile,
    *,
    key: Key | None = None,
    degrees: int = 0,
    tempo_scale: float = 1.0,
    fragment: int = 0,
    fragment_bars: int = 2,
) -> MidiFile:
    """Derive one track's phrase: a bar window, moved diatonically, optionally faster.

    Fragment selection happens before transposition so the same window is chosen in every
    track's own key — otherwise track three would start at a different musical place.

    `tempo_scale` is a *speed* factor: 2.0 plays the phrase twice as fast, so positions and
    durations are divided by it. Multiplying would make a combat track slower, which is the
    opposite of what the spec author asked for.
    """
    if tempo_scale <= 0:
        raise ValueError(f"tempo_scale must be positive, got {tempo_scale}")
    if fragment < 0:
        raise ValueError(f"fragment must be >= 0, got {fragment}")
    if fragment_bars < 1:
        raise ValueError(f"fragment_bars must be >= 1, got {fragment_bars}")

    resolved_key = key or detect_key(midi)
    beat_window = fragment_bars * midi.beats_per_bar
    start = fragment * beat_window
    end = start + beat_window

    notes: list[Note] = []
    for note in midi.notes:
        if note.start < start:
            continue
        if note.start >= end:
            continue
        shifted = replace(
            note,
            start=(note.start - start) / tempo_scale,
            duration=note.duration / tempo_scale,
            pitch=transpose_diatonic(note.pitch, resolved_key, degrees),
        )
        # A note crossing the window edge is cut at the bar line: a fragment must not bleed
        # the next phrase into this one. The window itself shrinks when the phrase speeds up.
        overrun = (shifted.start + shifted.duration) - beat_window / tempo_scale
        if overrun > 0:
            shifted = replace(shifted, duration=max(0.0, shifted.duration - overrun))
        if shifted.duration > 0:
            notes.append(shifted)

    if not notes:
        raise ValueError(
            f"fragment {fragment} (bars {fragment + 1}..{fragment + fragment_bars}) is empty: "
            "the phrase is shorter than that window"
        )
    return MidiFile(
        notes=tuple(notes),
        bpm=midi.bpm,
        beats_per_bar=midi.beats_per_bar,
        ppq=midi.ppq,
    )


def tile_to_length(midi: MidiFile, length_beats: float) -> MidiFile:
    """Repeat the phrase until it covers `length_beats`, truncating at the end.

    Repetition is what makes a two-bar motif a four-bar loop without inventing notes; the
    renderer only has to play what is written.
    """
    if length_beats <= 0:
        raise ValueError("length must be positive")
    span = midi.length_beats
    if span <= 0:
        raise ValueError("cannot tile an empty phrase")

    notes: list[Note] = []
    offset = 0.0
    while offset < length_beats:
        for note in midi.notes:
            start = note.start + offset
            if start >= length_beats:
                continue
            duration = min(note.duration, length_beats - start)
            notes.append(replace(note, start=start, duration=duration))
        offset += span
    return MidiFile(
        notes=tuple(notes),
        bpm=midi.bpm,
        beats_per_bar=midi.beats_per_bar,
        ppq=midi.ppq,
    )


def _positive_int(value: Any, key: str, where: str, *, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise SpecError(f"music.{key} is required", location=where)
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpecError(f"music.{key} must be an integer >= 1", location=where)
    return value


def _number(value: Any, key: str, where: str, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"music.{key} must be a number", location=where)
    return float(value)


def resolve_music(root: Path, music: Any, *, where: str) -> dict[str, Any]:
    """Validate a spec's `music:` block and solve its track plan.

    The result is what goes into `GenerationRequest.params`: fully resolved, including the
    leitmotif's content hash and the solved lengths. Hashing the MIDI is what makes swapping
    the source phrase invalidate every derived track's cache entry.
    """
    if not isinstance(music, Mapping):
        raise SpecError("music must be a mapping", location=where)
    unknown = sorted(set(music) - MUSIC_KEYS)
    if unknown:
        raise SpecError(
            f"unknown key(s) in music: {', '.join(unknown)}",
            location=where,
            remedy=f"allowed keys: {', '.join(sorted(MUSIC_KEYS))}",
        )

    leitmotif = music.get("leitmotif")
    if not isinstance(leitmotif, str) or not leitmotif.strip():
        raise SpecError(
            "music.leitmotif must name a .mid file",
            location=where,
            remedy="for example: leitmotif/leitmotif_core.mid",
        )
    relative = relative_path(leitmotif, where, "music.leitmotif")
    source = Path(root) / relative
    if not source.is_file():
        raise SpecError(
            f"leitmotif not found: {relative}",
            location=where,
            remedy="add the .mid under the project root, or fix the path",
        )

    bars = _positive_int(music.get("bars"), "bars", where)
    beats_per_bar = _positive_int(music.get("beats_per_bar"), "beats_per_bar", where, default=4)
    bpm = _number(music.get("bpm"), "bpm", where, default=120.0)
    if bpm <= 0:
        raise SpecError("music.bpm must be positive", location=where)
    crossfade = _number(music.get("loop_crossfade_s"), "loop_crossfade_s", where, default=0.5)
    transpose_value = music.get("transpose", 0)
    if isinstance(transpose_value, bool) or not isinstance(transpose_value, int):
        raise SpecError("music.transpose must be an integer count of scale degrees", location=where)
    fragment = music.get("fragment", 0)
    if isinstance(fragment, bool) or not isinstance(fragment, int) or fragment < 0:
        raise SpecError("music.fragment must be an integer >= 0", location=where)
    fragment_bars = _positive_int(music.get("fragment_bars"), "fragment_bars", where, default=2)
    timbre = str(music.get("timbre", "pad"))
    if timbre not in TIMBRES:
        raise SpecError(
            f"unknown timbre {timbre!r}",
            location=where,
            remedy=f"timbres: {', '.join(TIMBRES)}",
        )
    tempo_scale = _number(music.get("tempo_scale"), "tempo_scale", where, default=1.0)
    if tempo_scale <= 0:
        raise SpecError("music.tempo_scale must be positive", location=where)
    gain_db = _number(music.get("melody_gain_db"), "melody_gain_db", where, default=0.0)

    try:
        plan = TrackPlan(
            bars=bars,
            beats_per_bar=beats_per_bar,
            bpm=bpm,
            crossfade_s=crossfade,
        )
    except ValueError as exc:
        raise SpecError(str(exc), location=where) from None

    resolved = {
        "leitmotif": relative,
        "leitmotif_sha256": hash_file(source),
        **plan.to_dict(),
        "transpose": transpose_value,
        "tempo_scale": tempo_scale,
        "fragment": fragment,
        "fragment_bars": fragment_bars,
        "timbre": timbre,
        "melody_gain_db": gain_db,
    }
    return resolved


__all__ = [
    "MAJOR",
    "MUSIC_KEYS",
    "NATURAL_MINOR",
    "SCALES",
    "TIMBRES",
    "Key",
    "TrackPlan",
    "detect_key",
    "resolve_music",
    "tile_to_length",
    "transform",
    "transpose_diatonic",
]
