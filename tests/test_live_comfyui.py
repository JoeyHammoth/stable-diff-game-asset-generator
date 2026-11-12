"""Opt-in smoke test against a real ComfyUI with real model files.

Skipped unless the environment names a server and the model filenames installed on it.
CI has neither a GPU nor weights, so this is the nightly hook from
docs/07-testing-and-operations.md §5, not part of the default run.

    SDGA_COMFY_URL=http://127.0.0.1:8188 \
    SDGA_CKPT=sd_v1-5.safetensors \
    SDGA_LORA=my_game_style.safetensors \
    pytest tests/test_live_comfyui.py -m gpu
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from _project import TOML, make_project

from sdga.cli import make_backend
from sdga.config import load_config
from sdga.pipeline import execute_run

pytestmark = pytest.mark.gpu


def test_live_comfyui_generates_one_gated_tile(tmp_path: Path):
    url = os.environ.get("SDGA_COMFY_URL")
    checkpoint = os.environ.get("SDGA_CKPT")
    lora = os.environ.get("SDGA_LORA")

    if not url:
        pytest.skip("set SDGA_COMFY_URL to run against a live ComfyUI")
    if not checkpoint or not lora:
        pytest.skip("set SDGA_CKPT and SDGA_LORA to the model filenames installed there")

    toml = (
        TOML.replace('kind = "fake"', f'kind = "comfyui"\nurl = "{url}"')
        .replace('checkpoint = "sd_v1-5.safetensors"', f'checkpoint = "{checkpoint}"')
        .replace('name = "testgame_style.safetensors"', f'name = "{lora}"')
    )
    make_project(tmp_path, toml=toml)
    config = load_config(tmp_path)

    outcome = execute_run(config, make_backend(config), assets=["terrain/moss_stone"])

    assert outcome.status == "complete", (outcome.rejected, outcome.failed)
    record = (outcome.run_dir / "run.json").read_text(encoding="utf-8")
    assert '"status": "accepted"' in record
    assert '"gate": "seamless_tile",\n        "status": "pass"' in record
