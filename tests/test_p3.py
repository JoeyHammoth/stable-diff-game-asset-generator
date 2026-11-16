"""P3 · run hygiene: T25 cache, T26 resume, T27 retries, T28 concurrency/status, T29 validate.

The interesting failures here are the ones a single-threaded happy path cannot show: a second
run that quietly re-renders, a kill that loses the record, an OOM that retries forever, and a
concurrency setting that is read but never enforced.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from _project import TOML, make_project
from PIL import Image
from replay import ReplayServer

from sdga.backends import FakeBackend, GenerationBackend, JobReport, PollState
from sdga.backends.comfyui import ComfyUIBackend
from sdga.backends.comfyui.client import ComfyUIClient
from sdga.canonical import hash_file
from sdga.cli import main
from sdga.config import load_config
from sdga.errors import BackendError
from sdga.pipeline import ArtifactCache, collect, execute_run, run_dir_for

TILE = "terrain/moss_stone"


def _record(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def _cache_dir(project: Path) -> Path:
    return project / ".sdga" / "cache"


class CountingBackend(FakeBackend):
    """Counts submits, which is how "0 backend calls" is proved rather than assumed."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.submits = 0
        self._lock = threading.Lock()

    def submit(self, request):  # type: ignore[no-untyped-def]
        with self._lock:
            self.submits += 1
        return super().submit(request)


class RecordingBackend(FakeBackend):
    """Keeps the requests it saw, so a resume test can hand one back to `lookup`."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list = []

    def submit(self, request):  # type: ignore[no-untyped-def]
        self.seen.append(request)
        return super().submit(request)


@pytest.fixture
def fast_toml() -> str:
    """No backoff, so a retry test measures behaviour rather than patience."""
    return TOML.replace(
        '[backend]\nkind = "fake"',
        '[backend]\nkind = "fake"\nretry = { attempts = 3, backoff_s = 0.0 }',
    )


# ----------------------------------------------------------------- T25 · cache


def test_second_identical_run_is_all_cache_hits(project: Path):
    config = load_config(project)
    first = execute_run(config, CountingBackend(), assets=[TILE])
    first_job = _record(first.run_dir)["jobs"][0]

    backend = CountingBackend()
    second = execute_run(config, backend, assets=[TILE])

    assert backend.submits == 0, "a cache hit must not reach the backend"
    assert (second.cached, second.generated) == (1, 0)
    assert second.status == "complete"

    job = _record(second.run_dir)["jobs"][0]
    assert job["cached"] is True
    assert job["source"] == "cache"
    # Byte-identical, not merely "similar": the postprocess ran again over the same pixels.
    assert job["post"][0]["sha256"] == first_job["post"][0]["sha256"]
    assert job["raw"][0]["sha256"] == first_job["raw"][0]["sha256"]


def test_a_cache_hit_is_hard_linked(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE])
    second = execute_run(config, CountingBackend(), assets=[TILE])

    raw = config.root / _record(second.run_dir)["jobs"][0]["raw"][0]["path"]
    cached = next(_cache_dir(project).glob("*.png"))
    raw_stat, cached_stat = raw.stat(), cached.stat()
    same_inode = raw_stat.st_ino == cached_stat.st_ino and raw_stat.st_ino != 0
    assert same_inode or raw_stat.st_nlink > 1


def test_a_corrupt_cache_entry_is_a_miss_and_is_regenerated(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE])

    cached = next(_cache_dir(project).glob("*.png"))
    cached.write_bytes(b"not a png at all")

    backend = CountingBackend()
    outcome = execute_run(config, backend, assets=[TILE])

    assert backend.submits == 1, "corrupt bytes must not be served as a hit"
    assert outcome.generated == 1
    job = _record(outcome.run_dir)["jobs"][0]
    assert job["status"] == "accepted"
    index = json.loads((_cache_dir(project) / "index.json").read_text(encoding="utf-8"))
    entry = next(iter(index["entries"].values()))
    assert hash_file(_cache_dir(project) / entry["file"]) == entry["sha256"]


def test_force_regenerates_through_a_warm_cache(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE])

    backend = CountingBackend()
    outcome = execute_run(config, backend, assets=[TILE], force=True)

    assert backend.submits == 1
    assert outcome.generated == 1
    assert _record(outcome.run_dir)["jobs"][0]["source"] == "generated"


def test_no_cache_neither_reads_nor_writes(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE], use_cache=False)
    assert not _cache_dir(project).exists()


def test_the_cache_key_includes_the_profile(project: Path):
    cache = ArtifactCache(_cache_dir(project))
    source = project / "palettes" / "test.gpl"
    assert cache.store("sha256:abc", "sha256:profile-one", source) is not None

    assert ArtifactCache(_cache_dir(project)).lookup("sha256:abc", "sha256:profile-one")
    assert ArtifactCache(_cache_dir(project)).lookup("sha256:abc", "sha256:profile-two") is None


def test_deleting_the_cache_is_always_safe(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE])
    shutil.rmtree(_cache_dir(project))

    backend = CountingBackend()
    outcome = execute_run(config, backend, assets=[TILE])
    assert backend.submits == 1
    assert outcome.status == "complete"


# ---------------------------------------------------------------- T26 · resume

KILL_DRIVER = """
import os, sys
from sdga.backends import FakeBackend
from sdga.config import load_config
from sdga.pipeline import execute_run


class KillAfter(FakeBackend):
    def __init__(self):
        super().__init__()
        self.count = 0

    def submit(self, request):
        self.count += 1
        if self.count == 2:
            os._exit(9)  # the process just dies: no cleanup, no final run.json write
        return super().submit(request)


execute_run(load_config(sys.argv[1]), KillAfter())
"""


def test_a_killed_run_resumes_without_duplicate_generations(project: Path, tmp_path: Path):
    driver = tmp_path / "kill_mid_run.py"
    driver.write_text(KILL_DRIVER, encoding="utf-8")

    killed = subprocess.run(
        [sys.executable, str(driver), str(project)], capture_output=True, text=True
    )
    assert killed.returncode == 9, killed.stderr

    run_dir = run_dir_for(load_config(project))
    interrupted = _record(run_dir)
    assert interrupted["status"] == "running"
    assert interrupted["planned"] == 7
    assert len(interrupted["jobs"]) == 1, "the completed job must survive the kill"
    done = interrupted["jobs"][0]
    done_hash = done["post"][0]["sha256"]

    backend = CountingBackend()
    outcome = execute_run(load_config(project), backend, resume="latest")

    assert outcome.status == "complete"
    assert outcome.accepted + outcome.superseded == 7
    assert backend.submits == 6, "only the jobs that never finished may be generated"
    record = _record(outcome.run_dir)
    assert record["resumed"] is True
    carried = next(job for job in record["jobs"] if job["request_hash"] == done["request_hash"])
    assert carried["source"] == "resume"
    assert carried["post"][0]["sha256"] == done_hash, "a resumed job must not be re-rendered"


def test_resume_asks_the_backend_before_resubmitting(project: Path):
    config = load_config(project)
    first = RecordingBackend()
    execute_run(config, first, assets=[TILE])
    request = first.seen[0]

    # Rewrite the record as a run that was killed after submitting but before collecting.
    run_dir = run_dir_for(config)
    record = _record(run_dir)
    record["jobs"] = []
    record["status"] = "running"
    (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

    class HistoryOnly(FakeBackend):
        def __init__(self) -> None:
            super().__init__()
            self.submit_calls = 0
            self._known = request

        def lookup(self, candidate):  # type: ignore[no-untyped-def]
            if candidate.request_hash != self._known.request_hash:
                return None
            super().submit(self._known)  # register the artifact so fetch() can serve it
            return super().lookup(candidate)

        def submit(self, candidate):  # type: ignore[no-untyped-def]
            self.submit_calls += 1
            return super().submit(candidate)

    backend = HistoryOnly()
    outcome = execute_run(config, backend, resume="latest", assets=[TILE], use_cache=False)

    assert backend.submit_calls == 0, "the server already had the job; do not generate it twice"
    assert outcome.status == "complete"
    assert _record(outcome.run_dir)["jobs"][0]["source"] == "backend"


def test_resuming_a_complete_run_generates_nothing(project: Path):
    config = load_config(project)
    execute_run(config, CountingBackend(), assets=[TILE])

    backend = CountingBackend()
    outcome = execute_run(config, backend, resume="latest", assets=[TILE])
    assert backend.submits == 0
    assert outcome.cached == 1
    assert outcome.status == "complete"


def test_a_killed_record_is_reported_as_not_started(project: Path, capsys):
    config = load_config(project)
    outcome = execute_run(config, CountingBackend(), assets=[TILE])
    record = _record(outcome.run_dir)
    record["planned"] = 4
    record["status"] = "running"
    (outcome.run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

    capsys.readouterr()
    assert main(["status", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    assert "3 of 4 planned request(s) not started" in out
    assert "--resume" in out


# --------------------------------------------------------------- T27 · retries


class OOMBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.submits = 0

    def submit(self, request):  # type: ignore[no-untyped-def]
        self.submits += 1
        return super().submit(request)

    def poll(self, handle):  # type: ignore[no-untyped-def]
        return JobReport(
            state=PollState.FAILED,
            message="node 6 (KSampler): CUDA out of memory. Tried to allocate 2.00 GiB",
        )


def test_out_of_memory_is_retried_exactly_once_then_fails(tmp_path: Path, fast_toml: str):
    make_project(tmp_path, toml=fast_toml)
    lines: list[str] = []
    backend = OOMBackend()
    outcome = execute_run(load_config(tmp_path), backend, assets=[TILE], emit=lines.append)

    assert backend.submits == 2, "one attempt plus exactly one retry, whatever retry.attempts says"
    assert outcome.status == "failed"
    job = _record(outcome.run_dir)["jobs"][0]
    assert job["status"] == "failed"
    assert job["error"]["kind"] == "execution_error"
    assert len(job["retries"]) == 1
    assert job["retries"][0]["out_of_memory"] is True
    assert any("--lowvram" in line for line in lines), "the remedy must be printed, not implied"


class FlakyBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.submits = 0

    def submit(self, request):  # type: ignore[no-untyped-def]
        self.submits += 1
        if self.submits == 1:
            raise BackendError("unreachable", "connection refused")
        return super().submit(request)


def test_a_retryable_error_is_retried(tmp_path: Path, fast_toml: str):
    make_project(tmp_path, toml=fast_toml)
    backend = FlakyBackend()
    outcome = execute_run(load_config(tmp_path), backend, assets=[TILE])

    assert backend.submits == 2
    assert outcome.status == "complete"
    job = _record(outcome.run_dir)["jobs"][0]
    assert job["retries"][0]["kind"] == "unreachable"
    assert job["retries"][0]["out_of_memory"] is False


class RejectingBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.submits = 0

    def submit(self, request):  # type: ignore[no-untyped-def]
        self.submits += 1
        raise BackendError("rejected_graph", "Prompt outputs failed validation")


def test_a_rejected_graph_is_never_retried(tmp_path: Path, fast_toml: str):
    make_project(tmp_path, toml=fast_toml)
    backend = RejectingBackend()
    outcome = execute_run(load_config(tmp_path), backend, assets=[TILE])

    assert backend.submits == 1, "a graph bug is deterministic: retrying it just wastes a minute"
    assert outcome.status == "failed"
    job = _record(outcome.run_dir)["jobs"][0]
    assert job["error"]["kind"] == "rejected_graph"


# ----------------------------------------------------------- T28 · concurrency


class SlowBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__(delay_s=0.05)
        self.in_flight = 0
        self.peak = 0
        self._lock = threading.Lock()

    def submit(self, request):  # type: ignore[no-untyped-def]
        with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        return super().submit(request)

    def poll(self, handle):  # type: ignore[no-untyped-def]
        report = super().poll(handle)
        if report.state is PollState.SUCCEEDED:
            with self._lock:
                self.in_flight -= 1
        return report


def test_max_concurrency_is_enforced(tmp_path: Path):
    toml = TOML.replace(
        '[backend]\nkind = "fake"',
        '[backend]\nkind = "fake"\nmax_concurrency = 2\npoll_interval_s = 0.01',
    )
    make_project(tmp_path, toml=toml)
    backend = SlowBackend()
    outcome = execute_run(load_config(tmp_path), backend, assets=["char/ranger_walk"])

    assert outcome.status in {"complete", "partial"}
    assert backend.peak == 2, "the limiter must be used, not just read"
    assert backend.peak <= 2, "never more than max_concurrency in flight"


def test_status_reports_the_backend_queue_and_the_latest_run(project: Path, capsys):
    execute_run(load_config(project), CountingBackend(), assets=[TILE])

    capsys.readouterr()
    assert main(["status", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    assert "queue: 0 running, 0 pending" in out
    assert "complete" in out
    assert TILE in out


def test_status_json_is_machine_readable(project: Path, capsys):
    execute_run(load_config(project), CountingBackend(), assets=[TILE])

    capsys.readouterr()
    assert main(["status", "--project", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == 1
    assert payload["backend"]["kind"] == "fake"
    assert payload["run"]["counts"]["accepted"] == 1


def test_a_comfyui_queue_is_parsed(tmp_path: Path):
    make_project(tmp_path)
    queue = {
        "queue_running": [[0, "prompt-running", {}, {}, []]],
        "queue_pending": [[1, "prompt-waiting", {}, {}, []]],
    }
    with ReplayServer(queue=queue) as server:
        toml = TOML.replace('kind = "fake"', f'kind = "comfyui"\nurl = "{server.url}"')
        config = load_config(make_project(tmp_path / "comfy", toml=toml))
        backend = ComfyUIBackend(config.backend, client=ComfyUIClient(server.url))
        state = backend.queue()

    assert state.running == ("prompt-running",)
    assert state.pending == ("prompt-waiting",)


def test_status_survives_an_unreachable_backend(tmp_path: Path, capsys):
    make_project(
        tmp_path, toml=TOML.replace('kind = "fake"', 'kind = "comfyui"\nurl = "http://127.0.0.1:9"')
    )
    capsys.readouterr()
    assert main(["status", "--project", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "queue unavailable" in out


def test_the_protocol_is_satisfied_by_both_backends(project: Path):
    config = load_config(project)
    for backend in (
        FakeBackend(),
        ComfyUIBackend(config.backend, client=ComfyUIClient("http://127.0.0.1:9")),
    ):
        assert isinstance(backend, GenerationBackend)
        assert collect(config, backend).to_dict()["schema"] == 1


# -------------------------------------------------------------- T29 · validate


def test_validate_accepts_a_run_directory(project: Path, capsys):
    outcome = execute_run(load_config(project), CountingBackend(), assets=[TILE])
    capsys.readouterr()
    assert main(["validate", "--project", str(project), str(outcome.run_dir)]) == 0
    assert capsys.readouterr().out.strip().endswith("ok")


def test_validate_accepts_a_bare_run_id(project: Path, capsys):
    outcome = execute_run(load_config(project), CountingBackend(), assets=[TILE])
    capsys.readouterr()
    assert main(["validate", "--project", str(project), outcome.run_id]) == 0


def test_validate_json_is_stable_and_diffable(project: Path, capsys):
    outcome = execute_run(load_config(project), CountingBackend(), assets=[TILE])
    capsys.readouterr()

    assert main(["validate", "--project", str(project), "--run", outcome.run_id, "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["validate", "--project", str(project), "--run", outcome.run_id, "--json"]) == 0
    assert capsys.readouterr().out == first

    payload = json.loads(first)
    assert payload["schema"] == 1
    assert payload["ok"] is True
    assert payload["failures"] == 0


def test_validate_json_exits_one_and_counts_failures(project: Path, capsys):
    config = load_config(project)
    outcome = execute_run(config, CountingBackend(), assets=[TILE])
    post = config.root / _record(outcome.run_dir)["jobs"][0]["post"][0]["path"]
    with Image.open(post) as opened:
        image = opened.convert("RGBA")
    image.putpixel((0, 0), (255, 0, 255, 255))
    image.save(post)

    capsys.readouterr()
    assert main(["validate", "--project", str(project), outcome.run_id, "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["failures"] >= 1


def test_resume_reports_a_missing_run_clearly(project: Path, capsys):
    load_config(project)
    capsys.readouterr()
    assert main(["run", "--project", str(project), "--resume", "nope"]) == 1
    assert "no run" in capsys.readouterr().err
