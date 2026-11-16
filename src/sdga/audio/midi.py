"""Standard MIDI File reading and writing, without a dependency.

Why hand-rolled: `mido` is a fine library, but this module reads and writes exactly one
thing — a monophonic phrase with tempo and time signature — and the audio layer's promise is
that no part of it needs a package outside the standard library. The parser is deliberately
strict: an unsupported file is an error, not a best guess.

Times are in **quarter notes**, not ticks. Ticks are a file-format detail; every transform,
plan and gate reasons in beats, and converting once at the boundary keeps that honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HEADER_CHUNK = b"MThd"
TRACK_CHUNK = b"MTrk"

DEFAULT_PPQ = 480
DEFAULT_BPM = 120.0
DEFAULT_BEATS_PER_BAR = 4

NOTE_ON = 0x90
NOTE_OFF = 0x80
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
PITCH_BEND = 0xE0
CHANNEL_PRESSURE = 0xD0
AFTERTOUCH = 0xA0
META = 0xFF
SYSEX = 0xF0
SYSEX_ESCAPE = 0xF7


@dataclass(frozen=True)
class Note:
    """One sounding note. `start` and `duration` are quarter notes from the phrase start."""

    start: float
    duration: float
    pitch: int
    velocity: int = 96

    def to_dict(self) -> dict[str, float | int]:
        return {
            "start": round(self.start, 6),
            "duration": round(self.duration, 6),
            "pitch": self.pitch,
            "velocity": self.velocity,
        }


@dataclass(frozen=True)
class MidiFile:
    notes: tuple[Note, ...]
    bpm: float = DEFAULT_BPM
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR
    ppq: int = DEFAULT_PPQ

    @property
    def length_beats(self) -> float:
        return max((note.start + note.duration for note in self.notes), default=0.0)

    @property
    def bar_seconds(self) -> float:
        return self.beats_per_bar * 60.0 / self.bpm


def read_midi(path: Path) -> MidiFile:
    data = Path(path).read_bytes()
    try:
        return _parse(data)
    except (IndexError, ValueError) as exc:
        raise ValueError(f"{Path(path).name}: {exc}") from None


def write_midi(path: Path, midi: MidiFile) -> Path:
    """Format 0: one track, all notes, tempo and time signature first. Deterministic."""
    events: list[tuple[int, int, int, bytes]] = []
    microseconds = int(round(60_000_000 / midi.bpm))
    events.append((0, 0, 0, bytes([META, 0x51, 0x03, *microseconds.to_bytes(3, "big")])))
    events.append((0, 0, 1, bytes([META, 0x58, 0x04, midi.beats_per_bar, 2, 24, 8])))
    for index, note in enumerate(midi.notes):
        on = int(round(note.start * midi.ppq))
        off = int(round((note.start + note.duration) * midi.ppq))
        pitch = max(0, min(127, note.pitch))
        velocity = max(1, min(127, note.velocity))
        events.append((on, 1, index, bytes([NOTE_ON, pitch, velocity])))
        events.append((off, 0, index, bytes([NOTE_OFF, pitch, 64])))
    # Note-offs sort before note-ons at the same tick so a repeated pitch retriggers cleanly.
    events.sort(key=lambda event: (event[0], event[1], event[2]))

    track = bytearray()
    last_tick = 0
    for tick, _order, _index, payload in events:
        track += _vlq(tick - last_tick)
        track += payload
        last_tick = tick
    track += _vlq(0) + bytes([META, 0x2F, 0x00])

    header = HEADER_CHUNK + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
    header += (1).to_bytes(2, "big") + midi.ppq.to_bytes(2, "big")
    body = TRACK_CHUNK + len(track).to_bytes(4, "big") + bytes(track)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(header + body)
    return target


# --------------------------------------------------------------------------- parsing


def _parse(data: bytes) -> MidiFile:
    if not data.startswith(HEADER_CHUNK):
        raise ValueError("not a Standard MIDI File (missing MThd)")
    header_length = int.from_bytes(data[4:8], "big")
    if header_length < 6:
        raise ValueError(f"invalid header length {header_length}")
    fmt = int.from_bytes(data[8:10], "big")
    track_count = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    if fmt not in (0, 1):
        raise ValueError(f"unsupported MIDI format {fmt}; only 0 and 1 are read")
    if division & 0x8000:
        raise ValueError("SMPTE time division is not supported; save as ticks-per-quarter")
    if division <= 0:
        raise ValueError("time division must be positive")

    offset = 8 + header_length
    bpm = DEFAULT_BPM
    beats_per_bar = DEFAULT_BEATS_PER_BAR
    notes: list[Note] = []
    seen_tracks = 0
    while offset + 8 <= len(data) and seen_tracks < track_count:
        chunk_type = data[offset : offset + 4]
        chunk_length = int.from_bytes(data[offset + 4 : offset + 8], "big")
        body = data[offset + 8 : offset + 8 + chunk_length]
        if len(body) != chunk_length:
            raise ValueError("truncated track chunk")
        if chunk_type == TRACK_CHUNK:
            track_bpm, track_meter, track_notes = _parse_track(body, division)
            bpm = track_bpm or bpm
            beats_per_bar = track_meter or beats_per_bar
            notes.extend(track_notes)
        offset += 8 + chunk_length
        seen_tracks += 1

    if not notes:
        raise ValueError("no notes found")
    notes.sort(key=lambda note: (note.start, note.pitch))
    return MidiFile(notes=tuple(notes), bpm=bpm, beats_per_bar=beats_per_bar, ppq=division)


def _parse_track(body: bytes, division: int) -> tuple[float | None, int | None, list[Note]]:
    position = 0
    tick = 0
    status = 0
    bpm: float | None = None
    beats_per_bar: int | None = None
    open_notes: dict[tuple[int, int], tuple[int, int]] = {}
    notes: list[Note] = []

    while position < len(body):
        delta, position = _read_vlq(body, position)
        tick += delta
        if position >= len(body):
            break
        byte = body[position]
        if byte < 0x80:
            if status == 0:
                raise ValueError("data byte before any status byte")
            # Running status: the byte is already the first data byte.
            first = byte
            position += 1
        else:
            status = byte
            position += 1
            if status in (SYSEX, SYSEX_ESCAPE):
                length, position = _read_vlq(body, position)
                position += length
                continue
            if status == META:
                if position >= len(body):
                    break
                meta_type = body[position]
                position += 1
                length, position = _read_vlq(body, position)
                payload = body[position : position + length]
                position += length
                if meta_type == 0x51 and len(payload) >= 3:
                    micros = int.from_bytes(payload[:3], "big")
                    if micros:
                        bpm = 60_000_000 / micros
                elif meta_type == 0x58 and payload:
                    beats_per_bar = payload[0] or beats_per_bar
                elif meta_type == 0x2F:
                    break
                continue
            if position >= len(body):
                break
            first = body[position]
            position += 1

        command = status & 0xF0
        channel = status & 0x0F
        if command in (NOTE_ON, NOTE_OFF, AFTERTOUCH, CONTROL_CHANGE, PITCH_BEND):
            second = body[position] if position < len(body) else 0
            position += 1
            if command == NOTE_ON and second > 0:
                open_notes[(channel, first)] = (tick, second)
            elif command == NOTE_OFF or (command == NOTE_ON and second == 0):
                opened = open_notes.pop((channel, first), None)
                if opened is not None:
                    start_tick, velocity = opened
                    notes.append(
                        Note(
                            start=start_tick / division,
                            duration=max(1, tick - start_tick) / division,
                            pitch=first,
                            velocity=velocity,
                        )
                    )
        elif command in (PROGRAM_CHANGE, CHANNEL_PRESSURE):
            position += 1  # one data byte

    # A note left sounding at end-of-track lasts one beat, which is audible but not silent.
    for (_channel, pitch), (start_tick, velocity) in sorted(open_notes.items()):
        notes.append(
            Note(
                start=start_tick / division,
                duration=max(1, tick - start_tick) / division,
                pitch=pitch,
                velocity=velocity,
            )
        )
    return bpm, beats_per_bar, notes


def _read_vlq(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ValueError("variable-length quantity longer than 4 bytes")


def _vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("delta time cannot be negative")
    buffer = [value & 0x7F]
    value >>= 7
    while value:
        buffer.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buffer))


__all__ = [
    "DEFAULT_BEATS_PER_BAR",
    "DEFAULT_BPM",
    "DEFAULT_PPQ",
    "MidiFile",
    "Note",
    "read_midi",
    "write_midi",
]
