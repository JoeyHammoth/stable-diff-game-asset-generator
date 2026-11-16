"""Phase P4: audio (docs/06-implementation-plan.md, T30-T35).

One test per ticket, plus the properties the phase gate names: eight tracks from one
leitmotif, beat-aligned, seam-gated, published with loop points.

The regression guard worth keeping is `test_swap_halves_loop_fails_the_seam_gate`: the source
guide's "make it seamless" script fades the midpoint and swaps halves, which leaves the actual
wrap discontinuity untouched (gap analysis A5). If someone reintroduces that method, this test
goes red.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest
from _project import TOML as BASE_TOML
from _project import make_project

from sdga.audio import (
    Audio,
    AudioGateContext,
    FluidSynthBackend,
    Key,
    MidiFile,
    Note,
    SynthBackend,
    TrackPlan,
    audio_clip,
    audio_loop_seam,
    audio_peak,
    beat_alignment,
    detect_key,
    duration_exact,
    fade_edges,
    loop_crossfade,
    loudness_normalize,
    mix,
    read_midi,
    read_wav,
    render_sfx,
    resample,
    trim_silence,
    write_midi,
)
from sdga.audio.leitmotif import resolve_music, tile_to_length, transform, transpose_diatonic
from sdga.audio.ops import peak_report
from sdga.backends import FakeBackend
from sdga.backends.comfyui import load_recipes
from sdga.canonical import hash_file
from sdga.config import load_config
from sdga.errors import BackendError, SpecError
from sdga.pack import publish
from sdga.pipeline import execute_run, verify_pack
from sdga.planning import build_plan
from sdga.specs import load_specs

# A project that can render audio: the fake image backend is present but unused.
TOML = BASE_TOML + '\n[audio]\nkind = "synth"\nsample_rate = 32000\n'

YAML_HEADER = "schema: 1\nassets:\n"


def _phrase() -> MidiFile:
    """Eight bars in D minor at 90 bpm. D, not C: key detection must read the file."""
    notes = [
        (0, 1, 62),
        (1, 1, 65),
        (2, 1, 69),
        (3, 1, 67),
        (4, 1.5, 65),
        (5.5, 0.5, 64),
        (6, 1, 62),
        (8, 1, 69),
        (9, 1, 72),
        (10, 2, 74),
        (12, 1, 72),
        (13, 1, 69),
        (14, 2, 67),
        (16, 1, 62),
        (17, 1, 65),
        (18, 1, 69),
        (19, 1, 67),
        (20, 1.5, 65),
        (21.5, 0.5, 64),
        (22, 1, 62),
        (24, 1, 64),
        (25, 1, 65),
        (26, 1, 67),
        (27, 1, 69),
        (28, 1, 67),
        (29, 1, 64),
        (30, 2, 62),
    ]
    return MidiFile(
        notes=tuple(
            Note(start=start, duration=duration, pitch=pitch, velocity=92)
            for start, duration, pitch in notes
        ),
        bpm=90.0,
        beats_per_bar=4,
    )


def _music_spec(
    asset_id: str,
    *,
    bpm: float = 90,
    bars: int = 2,
    transpose: int = 0,
    fragment: int = 0,
    crossfade: float = 0.25,
    timbre: str = "pad",
) -> str:
    return (
        f"  - id: {asset_id}\n"
        "    kind: music_track\n"
        "    prompt: ambient bed, no lead\n"
        "    music:\n"
        "      leitmotif: leitmotif/core.mid\n"
        f"      bars: {bars}\n"
        f"      bpm: {bpm}\n"
        f"      fragment: {fragment}\n"
        f"      transpose: {transpose}\n"
        f"      timbre: {timbre}\n"
        f"      loop_crossfade_s: {crossfade}\n"
    )


def _sfx_spec(asset_id: str, *, duration: float = 0.3) -> str:
    return (
        f"  - id: {asset_id}\n"
        "    kind: sfx\n"
        "    prompt: short crisp ui click\n"
        f"    duration_s: {duration}\n"
    )


def _audio_project(tmp_path: Path, assets: str) -> Path:
    root = make_project(
        tmp_path,
        toml=TOML,
        assets={"assets/audio.yaml": YAML_HEADER + assets},
        with_recipes=False,
    )
    write_midi(root / "leitmotif" / "core.mid", _phrase())
    return root


def _run(root: Path):
    return execute_run(load_config(root), FakeBackend(), emit=lambda _message: None)


def _tone(seconds: float, frequency: float, rate: int = 8000) -> Audio:
    frames = int(round(seconds * rate))
    return Audio(
        channels=(
            tuple(math.sin(2 * math.pi * frequency * index / rate) for index in range(frames)),
        ),
        sample_rate=rate,
    )


# --------------------------------------------------------------------------- T30


def test_midi_round_trip_preserves_notes_tempo_and_meter(tmp_path: Path):
    target = write_midi(tmp_path / "phrase.mid", _phrase())
    back = read_midi(target)
    assert len(back.notes) == len(_phrase().notes)
    assert back.beats_per_bar == 4
    assert abs(back.bpm - 90.0) < 0.01
    assert [note.pitch for note in back.notes] == [note.pitch for note in _phrase().notes]
    assert [round(note.start, 3) for note in back.notes] == [
        round(note.start, 3) for note in _phrase().notes
    ]


def test_the_same_midi_twice_is_byte_identical(tmp_path: Path):
    midi = write_midi(tmp_path / "phrase.mid", _phrase())
    backend = SynthBackend(sample_rate=8000)
    first = backend.render_melody(midi, tmp_path / "a.wav")
    second = backend.render_melody(midi, tmp_path / "b.wav")
    assert hash_file(first) == hash_file(second)


def test_a_missing_soundfont_is_missing_capability(tmp_path: Path):
    backend = FluidSynthBackend(soundfont=str(tmp_path / "absent.sf2"), sample_rate=8000)
    profile = backend.probe()
    assert not profile.ok
    assert any(gap.item == "absent.sf2" for gap in profile.gaps)
    assert all(gap.remedy for gap in profile.gaps)

    with pytest.raises(BackendError) as caught:
        backend.render_melody(tmp_path / "phrase.mid", tmp_path / "out.wav")
    assert caught.value.kind == "missing_capability"


def test_switching_instrument_changes_the_profile_hash():
    synth = SynthBackend(sample_rate=8000).probe()
    other = SynthBackend(sample_rate=16000).probe()
    assert synth.profile_hash != other.profile_hash


# --------------------------------------------------------------------------- T31


def test_the_key_is_detected_from_the_file_not_assumed_to_be_c(tmp_path: Path):
    midi = read_midi(write_midi(tmp_path / "phrase.mid", _phrase()))
    key = detect_key(midi)
    assert key.tonic == 2 and key.mode == "minor"
    assert key.name == "D minor"


def test_diatonic_transposition_keeps_the_contour():
    key = Key(tonic=2, mode="minor")
    scale_tones = [62, 64, 65, 67, 69, 70, 72]  # D E F G A Bb C
    moved = [transpose_diatonic(pitch, key, 2) for pitch in scale_tones]
    # Every note moved two degrees along the same scale, so the degree contour is unchanged:
    # D E F G A Bb C becomes F G A Bb C D E (an octave up at the wrap).
    assert moved == [65, 67, 69, 70, 72, 74, 76]


def test_a_chromatic_note_keeps_its_alteration():
    key = Key(tonic=2, mode="minor")
    # Eb is a semitone below the second degree; two degrees up it becomes Gb, still a
    # semitone below the moved degree (G). Snapping into the scale would give G natural.
    assert transpose_diatonic(63, key, 2) == 66


def test_transform_reads_the_declared_bar_window():
    phrase = _phrase()
    first = transform(phrase, fragment=0, fragment_bars=2)
    third = transform(phrase, fragment=2, fragment_bars=2)
    assert first.notes[0].start == 0.0
    assert all(note.start < 8 for note in first.notes)
    # Bars 5-6 start at beat 16, so the window's first note is that bar's downbeat D.
    assert third.notes[0].pitch == 62
    assert max(note.start for note in third.notes) < 8


def test_tempo_scale_is_a_speed_factor():
    phrase = _phrase()
    normal = transform(phrase, fragment=0, fragment_bars=4)
    faster = transform(phrase, fragment=0, fragment_bars=4, tempo_scale=2.0)
    # 2.0 means twice as fast, so the same phrase occupies half the beats.
    assert faster.length_beats == pytest.approx(normal.length_beats / 2)


def test_tiling_reaches_the_requested_length():
    phrase = transform(_phrase(), fragment=0, fragment_bars=2)
    tiled = tile_to_length(phrase, 16)
    assert tiled.length_beats == pytest.approx(16)
    assert len(tiled.notes) > len(phrase.notes)


def test_unknown_music_keys_are_rejected_with_the_allowed_set(tmp_path: Path):
    with pytest.raises(SpecError) as caught:
        resolve_music(
            tmp_path,
            {"leitmotif": "x.mid", "bars": 4, "tempoo": 1.5},
            where="assets/audio.yaml:1",
        )
    assert "tempoo" in str(caught.value)
    assert "allowed keys" in str(caught.value)


# --------------------------------------------------------------------------- T32


def test_loop_crossfade_shortens_by_the_fade_and_joins_the_tail():
    audio = _tone(1.0, 220.0)
    faded = loop_crossfade(audio, 0.1)
    assert faded.frame_count == audio.frame_count - int(round(0.1 * audio.sample_rate))
    # The new head is the old tail: the wrap is now interior continuity.
    tail_start = faded.frame_count
    assert faded.channels[0][0] == pytest.approx(audio.channels[0][tail_start])


def test_a_crossfaded_sine_loop_passes_the_seam_gate():
    audio = _tone(1.0, 220.0)
    gate = audio_loop_seam(loop_crossfade(audio, 0.1), AudioGateContext())
    assert gate.status == "pass", gate.to_dict()


def test_a_fade_at_the_seam_is_reported_as_a_level_drop():
    """A rest and a fade-out are identical by level, so the drop is reported, not failed.

    Continuity (the wrap delta) is the pass/fail question; this value tells a reviewer that
    the loop ends quietly so they can listen rather than guess.
    """
    rate = 8000
    tone = _tone(0.5, 220.0, rate)
    samples = list(tone.channels[0])
    for index in range(1, 801):
        samples[-index] *= index / 800
    faded = Audio(channels=(tuple(samples),), sample_rate=rate)
    gate = audio_loop_seam(faded, AudioGateContext())
    assert gate.status == "pass"
    assert gate.value["level_drop_db"] > 0.0


def test_a_swap_halves_loop_fails_the_seam_gate():
    """The source guide's method (fade the midpoint, swap halves) leaves the wrap broken.

    The fixture ends a half-cycle late, so the last sample is a full-amplitude jump away from
    the first — exactly what swapping halves at the midpoint cannot repair.
    """
    rate = 8000
    head = _tone(0.5, 220.0, rate)
    tail = _tone(0.5, 220.5, rate)
    broken = Audio(channels=(head.channels[0] + tail.channels[0],), sample_rate=rate)
    assert broken.channels[0][-1] > 0.9  # ends near the top of the waveform
    assert audio_loop_seam(broken, AudioGateContext()).status == "fail"
    # Folding the tail into the head passes the same gate, which is what makes it meaningful.
    assert audio_loop_seam(loop_crossfade(broken, 0.1), AudioGateContext()).status == "pass"


def test_loudness_normalize_hits_the_target_peak():
    normalized = loudness_normalize(_tone(1.0, 440.0).scaled(0.1), -3.0)
    assert normalized.peak_dbfs() == pytest.approx(-3.0, abs=0.01)


def test_trim_silence_drops_leading_and_trailing_silence():
    rate = 8000
    body = _tone(0.2, 440.0, rate)
    padded = Audio(
        channels=((0.0,) * 400 + body.channels[0] + (0.0,) * 400,),
        sample_rate=rate,
    )
    trimmed = trim_silence(padded)
    # A sine starts at zero, so the first "audible" sample is index 1 and the last is n - 2.
    assert trimmed.frame_count == pytest.approx(body.frame_count, abs=2)
    assert trimmed.channels[0][0] == pytest.approx(body.channels[0][1])


def test_fade_edges_starts_and_ends_at_silence():
    faded = fade_edges(_tone(0.5, 220.0), 0.01)
    assert faded.channels[0][0] < 0.05
    assert faded.channels[0][-1] < 0.05
    assert faded.frame_count == _tone(0.5, 220.0).frame_count


def test_mix_adds_the_bed_under_the_melody():
    melody = _tone(0.2, 220.0).scaled(0.5)
    bed = _tone(0.2, 110.0).scaled(0.25)
    mixed = mix(melody, bed)
    assert mixed.frame_count == melody.frame_count
    assert mixed.peak() >= melody.peak()


def test_mix_resamples_a_bed_recorded_at_another_rate():
    melody = _tone(0.2, 220.0, 8000)
    bed = _tone(0.2, 110.0, 16000)
    mixed = mix(melody, bed)
    assert mixed.sample_rate == melody.sample_rate
    assert mixed.frame_count == melody.frame_count


def test_resample_keeps_duration_and_a_constant_signal_constant():
    source = Audio(channels=((0.5,) * 8000,), sample_rate=8000)
    converted = resample(source, 16000)
    assert converted.sample_rate == 16000
    assert converted.frame_count == 16000
    assert converted.duration_s == pytest.approx(source.duration_s, abs=1e-6)
    assert all(abs(value - 0.5) < 1e-6 for value in converted.channels[0])


def test_resample_attenuates_above_the_target_nyquist():
    source = _tone(1.0, 7000.0, 16000)
    folded = resample(source, 8000)
    assert folded.frame_count == 8000
    # 7 kHz is above the 4 kHz Nyquist limit of the target rate; a low-passed downsample must
    # remove it instead of folding it back in as a 1 kHz whistle.
    assert folded.rms() < source.rms() * 0.1


def test_read_wav_accepts_unsigned_8_bit_pcm(tmp_path: Path):
    target = tmp_path / "eight_bit.wav"
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(8000)
        handle.writeframes(bytes([128, 255, 0]))

    audio = read_wav(target)
    assert audio.sample_rate == 8000
    assert audio.channels[0][0] == pytest.approx(0.0)
    assert audio.channels[0][1] == pytest.approx(127 / 128)
    assert audio.channels[0][2] == pytest.approx(-1.0)


def test_read_midi_converts_smpte_ticks_through_seconds(tmp_path: Path):
    # 25 fps, 40 ticks/frame, 120 bpm: 1000 ticks per second and one beat per half second.
    # The note starts at tick 500 (one beat) and lasts 500 ticks (one beat).
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
    header += (1).to_bytes(2, "big") + bytes([0xE7, 40])
    track = (
        b"\x00\xff\x51\x03\x07\xa1\x20"
        + b"\x83\x74\x90\x3c\x60"
        + b"\x83\x74\x80\x3c\x40"
        + b"\x00\xff\x2f\x00"
    )
    target = tmp_path / "smpte.mid"
    target.write_bytes(header + b"MTrk" + len(track).to_bytes(4, "big") + track)

    midi = read_midi(target)
    assert midi.bpm == pytest.approx(120.0)
    assert midi.ppq == 480
    assert len(midi.notes) == 1
    assert midi.notes[0].start == pytest.approx(1.0)
    assert midi.notes[0].duration == pytest.approx(1.0)


def test_peak_report_describes_the_file():
    report = peak_report(loudness_normalize(_tone(0.5, 220.0), -3.0))
    assert report["duration_s"] == pytest.approx(0.5, abs=1e-3)
    assert report["peak_dbfs"] == pytest.approx(-3.0, abs=0.01)


# --------------------------------------------------------------------------- T33


def test_wrong_bar_count_fails_beat_alignment():
    plan = TrackPlan(bars=2, beats_per_bar=4, bpm=120, crossfade_s=0.0)
    correct = Audio(channels=((0.1,) * int(4.0 * 8000),), sample_rate=8000)
    wrong = Audio(channels=((0.1,) * int(3.5 * 8000),), sample_rate=8000)
    context = AudioGateContext(bpm=120, bars=2, beats_per_bar=4, expected_duration_s=4.0)
    assert beat_alignment(correct, context).status == "pass"
    assert beat_alignment(wrong, context).status == "fail"
    assert plan.target_s == pytest.approx(4.0)


def test_a_clipped_file_fails_audio_clip():
    hot = Audio(channels=((1.0, 0.5, -1.0),), sample_rate=8000)
    assert audio_clip(hot, AudioGateContext()).status == "fail"
    quiet = Audio(channels=((0.5, 0.25, -0.5),), sample_rate=8000)
    assert audio_clip(quiet, AudioGateContext()).status == "pass"


def test_peak_off_target_fails_audio_peak():
    audio = _tone(0.2, 220.0).scaled(0.1)
    assert audio_peak(audio, AudioGateContext(target_peak_dbfs=-3.0)).status == "fail"
    assert audio_peak(loudness_normalize(audio, -3.0), AudioGateContext()).status == "pass"


def test_duration_exact_needs_a_declared_duration():
    audio = _tone(0.3, 220.0)
    assert duration_exact(audio, AudioGateContext()).status == "skipped"
    assert duration_exact(audio, AudioGateContext(expected_duration_s=0.3)).status == "pass"
    assert duration_exact(audio, AudioGateContext(expected_duration_s=0.5)).status == "fail"


def test_audio_gates_never_mutate_their_input():
    audio = _tone(0.2, 220.0)
    before = audio.channels
    audio_loop_seam(audio, AudioGateContext())
    audio_peak(audio, AudioGateContext())
    audio_clip(audio, AudioGateContext())
    assert audio.channels == before


# --------------------------------------------------------------------------- T34


def test_track_plan_solves_the_bar_aligned_length():
    plan = TrackPlan(bars=4, beats_per_bar=4, bpm=90, crossfade_s=0.5)
    assert plan.target_s == pytest.approx(4 * 4 * 60 / 90)
    assert plan.render_s == pytest.approx(plan.target_s + 0.5)
    with pytest.raises(ValueError):
        TrackPlan(bars=1, beats_per_bar=4, bpm=120, crossfade_s=3.0)


def test_a_music_request_forbids_a_lead_melody(tmp_path: Path):
    root = _audio_project(tmp_path, _music_spec("music/title"))
    config = load_config(root)
    request = next(request for request in build_plan(config, load_specs(config)).requests)
    assert "lead melody" in request.negative
    assert request.params["music"]["target_s"] == pytest.approx(2 * 4 * 60 / 90)
    assert request.params["music"]["leitmotif_sha256"].startswith("sha256:")
    assert request.size is None and request.final_size is None


def test_swapping_the_leitmotif_changes_the_request_hash(tmp_path: Path):
    root = _audio_project(tmp_path, _music_spec("music/title"))
    config = load_config(root)
    before = build_plan(config, load_specs(config)).requests[0].request_hash
    write_midi(
        root / "leitmotif" / "core.mid",
        MidiFile(notes=(Note(start=0, duration=1, pitch=65),), bpm=90.0),
    )
    after = build_plan(config, load_specs(config)).requests[0].request_hash
    assert before != after


def test_eight_tracks_share_one_tempo_grid_and_derive_from_one_leitmotif(tmp_path: Path):
    assets = "".join(
        _music_spec(
            f"music/biome_{index}",
            transpose=index - 3,
            fragment=index % 4,
            timbre="pad" if index % 2 else "pluck",
        )
        for index in range(8)
    )
    root = _audio_project(tmp_path, assets)
    outcome = _run(root)
    assert outcome.status == "complete", outcome
    assert outcome.accepted == 8

    record = __import__("json").loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    keys = {job["midi"]["key"]["name"] for job in record["jobs"]}
    assert keys == {"D minor"}
    durations = {job["post"][0]["duration_s"] for job in record["jobs"]}
    assert len(durations) == 1
    assert durations.pop() == pytest.approx(2 * 4 * 60 / 90, abs=0.001)
    for job in record["jobs"]:
        gates = {gate["gate"]: gate["status"] for gate in job["gates"]}
        assert gates == {
            "beat_alignment": "pass",
            "audio_loop_seam": "pass",
            "audio_peak": "pass",
            "audio_clip": "pass",
        }, gates
    assert record["audio"]["kind"] == "synth"


def test_a_second_audio_run_is_all_cache_hits(tmp_path: Path):
    root = _audio_project(tmp_path, _music_spec("music/title"))
    first = _run(root)
    second = _run(root)
    assert first.generated == 1 and second.cached == 1 and second.generated == 0
    first_job = __import__("json").loads((first.run_dir / "run.json").read_text(encoding="utf-8"))[
        "jobs"
    ][0]
    second_job = __import__("json").loads(
        (second.run_dir / "run.json").read_text(encoding="utf-8")
    )["jobs"][0]
    assert first_job["post"][0]["sha256"] == second_job["post"][0]["sha256"]


# --------------------------------------------------------------------------- T35


def test_a_short_sfx_passes_peak_clip_and_duration(tmp_path: Path):
    root = _audio_project(tmp_path, _sfx_spec("sfx/ui_click", duration=0.3))
    outcome = _run(root)
    assert outcome.status == "complete"
    record = __import__("json").loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    job = record["jobs"][0]
    gates = {gate["gate"]: gate["status"] for gate in job["gates"]}
    assert gates == {"duration_exact": "pass", "audio_peak": "pass", "audio_clip": "pass"}
    artifact = read_wav(root / job["post"][0]["path"])
    assert artifact.duration_s == pytest.approx(0.3, abs=1e-4)
    assert artifact.peak_dbfs() == pytest.approx(-3.0, abs=0.5)


def test_sfx_rendering_is_deterministic_and_seed_sensitive():
    first = render_sfx(seed=1, duration_s=0.2, sample_rate=8000)
    again = render_sfx(seed=1, duration_s=0.2, sample_rate=8000)
    other = render_sfx(seed=2, duration_s=0.2, sample_rate=8000)
    assert first.channels == again.channels
    assert first.channels != other.channels


# --------------------------------------------------------------------------- the P4 gate


def test_the_soundtrack_publishes_with_loop_points(tmp_path: Path):
    assets = "".join(
        _music_spec(f"music/biome_{index}", fragment=index % 4) for index in range(8)
    ) + _sfx_spec("sfx/ui_click")
    root = _audio_project(tmp_path, assets)
    config = load_config(root)

    outcome = _run(root)
    assert outcome.status == "complete"
    result = publish(config, outcome.run_dir, allow_unreviewed=True)

    import json

    manifest = json.loads((result.path / "pack.json").read_text(encoding="utf-8"))
    by_id = {asset["id"]: asset for asset in manifest["assets"]}
    assert len(by_id) == 9

    for index in range(8):
        asset = by_id[f"music/biome_{index}"]
        assert asset["files"][0]["format"] == "wav"
        assert asset["files"][0]["role"] == "audio"
        loop = asset["engine"]["music"]
        assert loop["bpm"] == 90
        assert loop["bars"] == 2
        assert loop["loop"]["end_s"] == pytest.approx(2 * 4 * 60 / 90, abs=1e-6)
        assert loop["loop"]["crossfade_s"] == pytest.approx(0.25)
        assert (result.path / asset["files"][0]["path"]).is_file()

    click = by_id["sfx/ui_click"]
    assert click["engine"]["sfx"]["one_shot"] is True
    assert click["files"][0]["duration_s"] == pytest.approx(0.3, abs=1e-4)

    ok, rows = verify_pack(config, result.path, load_recipes(config))
    assert ok, [row for row in rows if row["status"] == "fail"]
