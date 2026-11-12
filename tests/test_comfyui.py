from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _project import make_project
from replay import ReplayServer, checkerboard_png, load

from sdga.backends.base import PollState
from sdga.backends.comfyui import (
    ComfyUIBackend,
    ComfyUIClient,
    load_recipes,
    prompt_id_for,
)
from sdga.backends.comfyui.progress import WebSocketTracker, parse_event
from sdga.config import load_config
from sdga.errors import BackendError
from sdga.pack import publish
from sdga.pipeline import execute_run, verify_pack
from sdga.planning import build_plan
from sdga.specs import load_specs


def _project_and_request(project: Path):
    config = load_config(project)
    plan = build_plan(config, load_specs(config), recipes=load_recipes(config))
    request = next(r for r in plan.requests if r.asset_id == "terrain/moss_stone")
    return config, request


def _backend(config, url: str, **kwargs: Any) -> ComfyUIBackend:
    backend_config = replace(
        config.backend,
        kind="comfyui",
        url=url,
        ws_url="",
        timeout_s=5.0,
        poll_interval_s=0.001,
    )
    return ComfyUIBackend(backend_config, **kwargs)


# --------------------------------------------------------------------- contract


def test_submit_sends_the_caller_supplied_prompt_id(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer() as server:
        backend = _backend(config, server.url)
        handle = backend.submit(request)
        body = server.prompt_requests[0]

    assert body["prompt_id"] == handle.prompt_id == prompt_id_for(request.request_hash)
    assert body["prompt"]["6"]["inputs"]["seed"] == request.seed
    assert isinstance(body["prompt"]["6"]["inputs"]["steps"], int)
    assert body["prompt"]["12"]["inputs"]["filename_prefix"] == "sdga/terrain__moss_stone"


def test_submitting_twice_in_one_process_does_not_queue_twice(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer() as server:
        backend = _backend(config, server.url)
        first = backend.submit(request)
        second = backend.submit(request)
        assert len(server.prompt_requests) == 1
    assert first == second


def test_a_rejected_graph_is_not_retried(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer(prompt_status=400) as server:
        backend = _backend(config, server.url)
        with pytest.raises(BackendError) as caught:
            backend.submit(request)

    error = caught.value
    assert error.kind == "rejected_graph"
    assert error.retryable is False
    assert "KSampler" in json.dumps(error.payload)
    assert error.exit_code == 1


def test_the_declared_output_node_is_the_artifact(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer(history=load("history_multisave.json")) as server:
        backend = _backend(config, server.url)
        report = backend.poll(backend.submit(request))

    assert report.state is PollState.SUCCEEDED
    assert report.artifacts[0].filename == "final_00001_.png"
    assert report.artifacts[0].subfolder == "sdga"


def test_a_missing_output_node_is_bad_output(project: Path):
    config, request = _project_and_request(project)
    history = {
        "__PROMPT_ID__": {
            "outputs": {"8": {"images": [{"filename": "wrong.png", "subfolder": "", "type": "temp"}]}},
            "status": {"status_str": "success", "completed": True},
        }
    }
    with ReplayServer(history=history) as server:
        backend = _backend(config, server.url)
        with pytest.raises(BackendError) as caught:
            backend.poll(backend.submit(request))
    assert caught.value.kind == "bad_output"


def test_no_terminal_event_times_out(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer(history={}) as server:
        backend_config = replace(
            config.backend, kind="comfyui", url=server.url, ws_url="", timeout_s=0.0
        )
        backend = ComfyUIBackend(backend_config)
        with pytest.raises(BackendError) as caught:
            backend.poll(backend.submit(request))
    assert caught.value.kind == "timeout"
    assert caught.value.exit_code == 3


def test_view_requests_the_declared_file():
    with ReplayServer() as server:
        payload = ComfyUIClient(server.url).view("final_00001_.png", "sdga", "output")
        assert payload == server.view_bytes
        assert server.view_queries[0]["filename"] == ["final_00001_.png"]
        assert server.view_queries[0]["subfolder"] == ["sdga"]


def test_upload_image_sends_the_file_as_multipart(tmp_path: Path):
    image = tmp_path / "floor.png"
    image.write_bytes(checkerboard_png((8, 8)))

    with ReplayServer() as server:
        response = ComfyUIClient(server.url).upload_image(image)

    assert response == {}
    path, body = server.post_requests[0]
    assert path == "/upload/image"
    assert b'name="image"; filename="floor.png"' in body
    assert b"\x89PNG" in body  # the file bytes really travelled, not just a filename


def test_cancel_posts_an_interrupt(project: Path):
    config, request = _project_and_request(project)
    with ReplayServer() as server:
        backend = _backend(config, server.url)
        backend.cancel(backend.submit(request))
        assert any(path == "/interrupt" for path, _ in server.post_requests)


def test_a_connection_failure_is_unreachable():
    with pytest.raises(BackendError) as caught:
        ComfyUIClient("http://127.0.0.1:9", timeout_s=1.0).object_info()
    assert caught.value.kind == "unreachable"
    assert caught.value.retryable is True


# --------------------------------------------------------------------- progress


def test_binary_frames_do_not_break_progress_tracking():
    frames = [
        b"\xff\xd8\xff\xe0binary-preview",
        json.dumps({"type": "executing", "data": {"node": "6", "prompt_id": "p"}}),
        json.dumps({"type": "executing", "data": {"node": None, "prompt_id": "p"}}),
    ]
    terminal = WebSocketTracker("p", lambda: frames).poll()
    assert terminal is not None and terminal.kind == "completed"


def test_progress_and_status_events_are_not_terminal():
    assert parse_event(json.dumps({"type": "progress", "data": {"value": 3, "max": 25}}), "p") is None
    assert parse_event(json.dumps({"type": "status", "data": {"status": {}}}), "p") is None
    assert parse_event("not json at all", "p") is None


def test_an_execution_error_carries_the_node_and_message():
    terminal = parse_event(
        json.dumps(
            {
                "type": "execution_error",
                "data": {
                    "prompt_id": "p",
                    "node_id": "6",
                    "node_type": "KSampler",
                    "exception_message": "CUDA out of memory",
                },
            }
        ),
        "p",
    )
    assert terminal is not None
    assert terminal.kind == "error"
    assert terminal.node_type == "KSampler"
    assert "out of memory" in (terminal.message or "")


def test_events_for_another_prompt_are_ignored():
    assert (
        parse_event(json.dumps({"type": "executing", "data": {"node": None, "prompt_id": "other"}}), "p")
        is None
    )


def test_a_broken_socket_falls_back_to_polling_rather_than_failing():
    def explode():
        raise OSError("connection reset")

    tracker = WebSocketTracker("p", explode)
    assert tracker.poll() is None
    assert tracker.poll() is None


def test_a_tracked_execution_error_fails_the_job(project: Path):
    config, request = _project_and_request(project)
    prompt_id = prompt_id_for(request.request_hash)
    frames = [
        json.dumps(
            {
                "type": "execution_error",
                "data": {
                    "prompt_id": prompt_id,
                    "node_id": "6",
                    "node_type": "KSampler",
                    "exception_message": "CUDA out of memory",
                },
            }
        )
    ]
    with ReplayServer() as server:
        backend = _backend(
            config,
            server.url,
            tracker_factory=lambda pid: WebSocketTracker(pid, lambda: frames),
        )
        report = backend.poll(backend.submit(request))

    assert report.state is PollState.FAILED
    assert report.error is not None
    assert report.error["node_type"] == "KSampler"
    assert "out of memory" in (report.message or "")


# --------------------------------------------------------------------- probe


def test_probe_reads_nodes_models_and_version(project: Path):
    config, _ = _project_and_request(project)
    with ReplayServer() as server:
        profile = _backend(config, server.url).probe()

    assert profile.has_node("KSampler")
    assert profile.has_model("checkpoints", "sd_v1-5.safetensors")
    assert profile.has_model("loras", "example_style.safetensors")
    assert profile.comfyui_version == "0.23.0"
    assert profile.devices[0].vram_total == 12803203072
    assert profile.profile_hash.startswith("sha256:")


def test_a_model_removed_from_the_combo_becomes_visible(project: Path):
    config, _ = _project_and_request(project)
    info = load("object_info.json")
    info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [
        ["sdxl_base.safetensors"],
        {},
    ]
    with ReplayServer(object_info=info) as server:
        profile = _backend(config, server.url).probe()
    assert not profile.has_model("checkpoints", "sd_v1-5.safetensors")


# --------------------------------------------------------------------- end to end


def test_a_full_run_over_http_produces_a_valid_pack(project: Path):
    config, _ = _project_and_request(project)
    with ReplayServer() as server:
        outcome = execute_run(config, _backend(config, server.url), assets=["terrain/moss_stone"])

    assert outcome.status == "complete"
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["profile"]["kind"] == "comfyui"
    assert record["profile"]["comfyui_version"] == "0.23.0"

    job = record["jobs"][0]
    assert job["status"] == "accepted"
    assert job["request_hash"].startswith("sha256:")
    statuses = {gate["gate"]: gate["status"] for gate in job["gates"]}
    assert statuses["seamless_tile"] == "pass", statuses
    assert statuses["palette_conformance"] == "pass", statuses

    result = publish(config, outcome.run_dir, allow_unreviewed=True)
    ok, rows = verify_pack(config, result.path, load_recipes(config))
    assert ok, rows

    manifest = json.loads((result.path / "pack.json").read_text(encoding="utf-8"))
    assert manifest["generator"]["backend"] == "comfyui"
    assert manifest["assets"][0]["engine"]["tile"] == {"size": [32, 32], "seamless": True}
