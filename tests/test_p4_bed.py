"""Beds: a texture under the authored melody (docs/04-pipeline-stages.md §Audio).

The bed seam has two jobs, and the tests pin both down. The offline texture is what makes the
whole bed path runnable in CI with no model and no soundfont; the MusicGen client is a real
HTTP contract that must fail loudly when the service is absent, never quietly ship a
melody-only track while the project asked for a bed.
"""

from __future__ import annotations

import array
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from _project import TOML as BASE_TOML
from _project import make_project
from test_p4 import YAML_HEADER, _music_spec, _phrase

from sdga.audio import (
    BedRequest,
    MusicGenBackend,
    TextureBedBackend,
    build_bed_backend,
    read_wav,
    write_midi,
)
from sdga.audio.bed import render_texture
from sdga.backends import FakeBackend
from sdga.canonical import hash_file
from sdga.config import load_config
from sdga.doctor import run as doctor_run
from sdga.errors import BackendError
from sdga.pack import publish
from sdga.pipeline import execute_run
from sdga.planning import build_plan
from sdga.specs import load_specs

RATE = 8000
TARGET_S = 2 * 4 * 60 / 90  # bars * beats_per_bar * 60 / bpm
RENDER_S = TARGET_S + 0.25  # the melody is rendered one crossfade longer than the loop


def _toml(bed: str, url: str = "") -> str:
    lines = [
        BASE_TOML,
        "[audio]",
        'kind = "synth"',
        f"sample_rate = {RATE}",
        f'bed = "{bed}"',
        "bed_gain_db = -9.0",
    ]
    if url:
        lines.append(f'bed_url = "{url}"')
    return "\n".join(lines) + "\n"


def _project(tmp_path: Path, bed: str, url: str = "") -> Path:
    root = make_project(
        tmp_path,
        toml=_toml(bed, url),
        assets={"assets/audio.yaml": YAML_HEADER + _music_spec("music/title")},
        with_recipes=False,
    )
    write_midi(root / "leitmotif" / "core.mid", _phrase())
    return root


def _job(outcome) -> dict:
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    return record["jobs"][0]


# ----------------------------------------------------------------- the offline texture


def test_the_texture_bed_is_deterministic_and_exactly_long(tmp_path: Path):
    backend = TextureBedBackend(sample_rate=RATE)
    request = BedRequest(
        prompt="ambient bed, no lead",
        negative="lead melody",
        duration_s=2.0,
        seed=7,
        sample_rate=RATE,
    )
    first = backend.generate(request, tmp_path / "a.wav")
    second = backend.generate(request, tmp_path / "b.wav")

    assert hash_file(first) == hash_file(second)
    audio = read_wav(first)
    assert audio.frame_count == 2 * RATE
    assert audio.peak_dbfs() > -20  # audible, not a silent file


def test_the_seed_selects_a_different_texture(tmp_path: Path):
    backend = TextureBedBackend(sample_rate=RATE)
    base = dict(prompt="p", negative="n", duration_s=1.0, sample_rate=RATE)
    first = backend.generate(BedRequest(seed=1, **base), tmp_path / "a.wav")
    second = backend.generate(BedRequest(seed=2, **base), tmp_path / "b.wav")
    assert hash_file(first) != hash_file(second)


# ----------------------------------------------------------------- the seam in a run


def test_a_bed_is_mixed_under_the_melody(tmp_path: Path):
    root = _project(tmp_path, "texture")
    outcome = execute_run(load_config(root), FakeBackend(), emit=lambda _m: None)

    assert outcome.status == "complete"
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    job = record["jobs"][0]
    assert job["status"] == "accepted"
    assert job["bed"]["kind"] == "texture"
    assert job["postprocess"] == ["mix", "loop_crossfade", "loudness_normalize"]
    assert record["audio"]["bed"]["kind"] == "texture"
    # Melody and bed are both raw artifacts, so a hit can rebuild the mix from either.
    assert len(job["raw"]) == 2
    assert (root / job["bed"]["path"]).is_file()


def test_the_bed_is_cached_and_the_second_mix_is_byte_identical(tmp_path: Path):
    root = _project(tmp_path, "texture")
    config = load_config(root)

    first = execute_run(config, FakeBackend(), emit=lambda _m: None)
    second = execute_run(config, FakeBackend(), emit=lambda _m: None)

    assert (second.cached, second.generated) == (1, 0)
    before, after = _job(first), _job(second)
    assert after["source"] == "cache"
    assert before["bed"]["sha256"] == after["bed"]["sha256"]
    # The melody is deterministic and local, so the hit re-renders and re-mixes rather than
    # serving a stored mix that would hide a postprocess change.
    assert before["post"][0]["sha256"] == after["post"][0]["sha256"]


def test_the_pack_records_the_bed(tmp_path: Path):
    root = _project(tmp_path, "texture")
    config = load_config(root)
    outcome = execute_run(config, FakeBackend(), emit=lambda _m: None)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)

    pack = json.loads((result.path / "pack.json").read_text(encoding="utf-8"))
    music = pack["assets"][0]["engine"]["music"]
    assert music["bed"] == {"kind": "texture", "gain_db": -9.0}


def test_the_bed_kind_is_part_of_the_request_hash(tmp_path: Path):
    def request_hash(bed: str) -> str:
        root = _project(tmp_path / bed, bed)
        config = load_config(root)
        return build_plan(config, load_specs(config)).requests[0].request_hash

    assert request_hash("none") != request_hash("texture")


def test_an_unknown_bed_backend_is_rejected():
    with pytest.raises(ValueError):
        build_bed_backend("magic", url="", sample_rate=RATE, timeout_s=1.0)


# ----------------------------------------------------------------- the MusicGen client


def _send(handler: BaseHTTPRequestHandler, status: int, content_type: str, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _wav(seconds: float, rate: int = RATE) -> bytes:
    audio = render_texture(
        BedRequest(prompt="", negative="", duration_s=seconds, seed=1, sample_rate=rate)
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        pcm = array.array("h", (int(round(value * 32767)) for value in audio.channels[0]))
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


class _BedServer(BaseHTTPRequestHandler):
    payloads: list[dict] = []
    mode = "wav"
    native_rate = RATE

    def do_GET(self) -> None:  # noqa: N802 - http.server names the verb this way
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps(
            {"model": "musicgen-test", "sample_rate": type(self).native_rate}
        ).encode()
        _send(self, 200, "application/json", body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).payloads.append(payload)
        if type(self).mode == "json":
            _send(self, 200, "application/json", b'{"error": "not a wav"}')
            return
        _send(
            self,
            200,
            "audio/wav",
            _wav(float(payload["duration_s"]), type(self).native_rate),
        )

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def musicgen_server():
    _BedServer.payloads = []
    _BedServer.mode = "wav"
    _BedServer.native_rate = RATE
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BedServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _BedServer
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_musicgen_posts_the_track_prompt_and_the_run_records_it(tmp_path, musicgen_server):
    url, handler = musicgen_server
    root = _project(tmp_path, "musicgen", url)
    outcome = execute_run(load_config(root), FakeBackend(), emit=lambda _m: None)

    assert outcome.status == "complete"
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    job = record["jobs"][0]
    assert job["status"] == "accepted"
    assert job["bed"]["kind"] == "musicgen"
    assert record["audio"]["bed"]["version"] == "musicgen-test"

    assert len(handler.payloads) == 1
    payload = handler.payloads[0]
    assert payload["prompt"]
    assert "lead melody" in payload["negative_prompt"]
    assert payload["sample_rate"] == RATE
    assert payload["duration_s"] == pytest.approx(RENDER_S, abs=1e-3)

    post = read_wav(root / job["post"][0]["path"])
    assert post.duration_s == pytest.approx(TARGET_S, abs=1e-3)


def test_musicgen_runs_at_its_native_rate_and_returns_the_project_rate(tmp_path, musicgen_server):
    url, handler = musicgen_server
    handler.native_rate = 16000
    backend = MusicGenBackend(url=url, sample_rate=RATE)
    target = backend.generate(
        BedRequest(
            prompt="ambient bed, no lead",
            negative="lead melody",
            duration_s=1.0,
            seed=7,
            sample_rate=RATE,
        ),
        tmp_path / "bed.wav",
    )

    assert handler.payloads[0]["sample_rate"] == 16000
    audio = read_wav(target)
    assert audio.sample_rate == RATE
    assert audio.duration_s == pytest.approx(1.0, abs=1e-3)


def test_a_missing_musicgen_service_is_missing_capability(tmp_path: Path):
    backend = MusicGenBackend(url="http://127.0.0.1:9", sample_rate=RATE)
    profile = backend.probe()
    assert not profile.ok
    assert any(gap.kind == "service" for gap in profile.gaps)

    with pytest.raises(BackendError) as caught:
        backend.generate(
            BedRequest(prompt="p", negative="n", duration_s=1.0, seed=1, sample_rate=RATE),
            tmp_path / "x.wav",
        )
    assert caught.value.kind == "missing_capability"


def test_a_run_with_a_dead_bed_service_fails_rather_than_dropping_the_bed(tmp_path: Path):
    root = _project(tmp_path, "musicgen", "http://127.0.0.1:9")
    outcome = execute_run(load_config(root), FakeBackend(), emit=lambda _m: None)

    assert outcome.status == "failed"
    job = _job(outcome)
    assert job["status"] == "failed"
    assert job["error"]["kind"] == "missing_capability"
    assert "bed" not in job or job.get("bed") is None


def test_a_non_wav_response_is_bad_output(tmp_path: Path, musicgen_server):
    url, handler = musicgen_server
    handler.mode = "json"
    backend = MusicGenBackend(url=url, sample_rate=RATE)

    with pytest.raises(BackendError) as caught:
        backend.generate(
            BedRequest(prompt="p", negative="n", duration_s=1.0, seed=1, sample_rate=RATE),
            tmp_path / "x.wav",
        )
    assert caught.value.kind == "bad_output"


def test_doctor_fails_a_missing_musicgen_service(tmp_path: Path):
    root = _project(tmp_path, "musicgen", "http://127.0.0.1:9")
    config = load_config(root)
    report = doctor_run(
        config,
        FakeBackend(),
        bed=MusicGenBackend(url="http://127.0.0.1:9", sample_rate=RATE),
    )

    assert not report.ok
    assert any(
        check.name == "audio:bed:musicgen" and check.status == "fail" for check in report.checks
    )
