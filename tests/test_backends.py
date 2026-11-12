from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from sdga.backends import FakeBackend, GenerationBackend, JobHandle, PollState
from sdga.config import load_config
from sdga.errors import BackendError
from sdga.model import AssetKind, GenerationRequest
from sdga.planning import build_plan
from sdga.specs import load_specs


def _request(root: Path, asset_id: str = "terrain/moss_stone") -> GenerationRequest:
    config = load_config(root)
    plan = build_plan(config, load_specs(config))
    return next(r for r in plan.requests if r.asset_id == asset_id)


def test_fake_backend_satisfies_the_protocol():
    assert isinstance(FakeBackend(), GenerationBackend)


def test_profile_hash_is_stable_across_instances():
    assert FakeBackend().probe().profile_hash == FakeBackend().probe().profile_hash


def test_profile_hash_changes_when_capability_changes():
    full = FakeBackend().probe().profile_hash
    reduced = FakeBackend(nodes=("KSampler",)).probe().profile_hash
    assert full != reduced


def test_profile_excludes_url_from_its_hash():
    first = FakeBackend().probe()
    second = replace(first, url="http://elsewhere:8188").profile_hash
    assert first.profile_hash == second


def test_submit_poll_fetch_writes_a_decodable_image(project: Path, tmp_path: Path):
    backend = FakeBackend()
    request = _request(project)

    handle = backend.submit(request)
    report = backend.poll(handle)
    assert report.state is PollState.SUCCEEDED
    assert len(report.artifacts) == 1

    written = backend.fetch(report.artifacts[0], tmp_path / "raw" / "tile.png")
    assert written.is_file()
    with Image.open(written) as image:
        assert image.size == request.size


def test_fetch_is_byte_deterministic(project: Path, tmp_path: Path):
    request = _request(project)

    def render(path: Path) -> bytes:
        backend = FakeBackend()
        handle = backend.submit(request)
        artifact = backend.poll(handle).artifacts[0]
        return backend.fetch(artifact, path).read_bytes()

    assert render(tmp_path / "a.png") == render(tmp_path / "b.png")


def test_different_seeds_produce_different_pixels(project: Path, tmp_path: Path):
    request = _request(project)

    def render(req: GenerationRequest, path: Path) -> bytes:
        backend = FakeBackend()
        artifact = backend.poll(backend.submit(req)).artifacts[0]
        return backend.fetch(artifact, path).read_bytes()

    assert render(request, tmp_path / "a.png") != render(
        replace(request, seed=request.seed + 1), tmp_path / "b.png"
    )


def test_prompt_id_is_derived_from_the_request_hash(project: Path):
    backend = FakeBackend()
    request = _request(project)
    first = backend.submit(request)
    second = FakeBackend().submit(request)
    assert first.prompt_id == second.prompt_id


def test_polling_an_unknown_job_fails_loudly():
    with pytest.raises(BackendError) as caught:
        FakeBackend().poll(JobHandle("nope", "sha256:x", "terrain/x"))
    assert caught.value.kind == "bad_output"


def test_a_request_without_a_render_size_is_rejected():
    request = GenerationRequest(
        asset_id="sfx/click",
        kind=AssetKind.SFX,
        backend="fake",
        positive="",
        negative="",
        seed=1,
        style_hash="sha256:0",
        size=None,
        final_size=(1, 1),
    )
    with pytest.raises(BackendError) as caught:
        FakeBackend().submit(request)
    assert caught.value.kind == "rejected_graph"


def test_delay_reports_running_then_succeeds(project: Path):
    backend = FakeBackend(delay_s=60.0)
    handle = backend.submit(_request(project))
    assert backend.poll(handle).state is PollState.RUNNING


def test_cancel_is_safe_to_call(project: Path):
    backend = FakeBackend()
    handle = backend.submit(_request(project))
    backend.cancel(handle)
    backend.cancel(handle)
