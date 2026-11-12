from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from _project import TOML, make_project

from sdga.config import load_config
from sdga.errors import SpecError
from sdga.model import AssetKind
from sdga.planning import build_plan
from sdga.specs import load_specs


def _plan(root: Path):
    config = load_config(root)
    return build_plan(config, load_specs(config))


def _by_id(root: Path, asset_id: str):
    return next(r for r in _plan(root).requests if r.asset_id == asset_id)


def test_plan_json_is_byte_stable(project: Path):
    assert _plan(project).to_json() == _plan(project).to_json()


def test_adding_an_asset_does_not_disturb_existing_seeds(project: Path):
    before = {r.asset_id: r.seed for r in _plan(project).requests}

    (project / "assets" / "extra.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/cave_floor\n"
        "    kind: terrain_tile\n"
        "    prompt: damp cave floor\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    after = {r.asset_id: r.seed for r in _plan(project).requests}

    for asset_id, seed in before.items():
        assert after[asset_id] == seed


def test_derived_seed_matches_the_documented_formula(project: Path):
    request = _by_id(project, "terrain/moss_stone")
    style = load_config(project).style
    tag = f"terrain/moss_stone|{style.contract_hash}|0"
    expected = int.from_bytes(hashlib.sha256(tag.encode("utf-8")).digest()[:4], "big")
    assert request.seed == expected


def test_changing_an_anchor_changes_every_seed(tmp_path: Path):
    make_project(tmp_path)
    before = {r.asset_id: r.seed for r in _plan(tmp_path).requests}

    changed = TOML.replace('"clean pixel art"]', '"clean pixel art", "no dithering"]')
    make_project(tmp_path / "changed", toml=changed)
    after = {r.asset_id: r.seed for r in _plan(tmp_path / "changed").requests}

    assert before.keys() == after.keys()
    assert all(before[key] != after[key] for key in before)


def test_prompt_puts_anchors_before_the_subject(project: Path):
    positive = _by_id(project, "terrain/moss_stone").positive
    assert positive.startswith("TestGameStyle, flat colours, clean pixel art, ")
    assert positive.endswith("seamless mossy cobblestone floor, top-down tile")


def test_negative_defaults_to_the_contract_anchors(project: Path):
    assert _by_id(project, "terrain/moss_stone").negative == ("photorealistic, blurry, gradient")


def test_negative_override_replaces_rather_than_appends(tmp_path: Path):
    make_project(
        tmp_path,
        assets={
            "assets/one.yaml": (
                "schema: 1\n"
                "assets:\n"
                "  - id: terrain/other\n"
                "    kind: terrain_tile\n"
                "    prompt: moss\n"
                "    size: [32, 32]\n"
                "    negative: watermark, text\n"
            )
        },
    )
    negative = _by_id(tmp_path, "terrain/other").negative
    assert negative == "watermark, text"
    assert "photorealistic" not in negative


def test_sprite_sheet_renders_the_whole_sheet_scaled_to_fit(project: Path):
    request = _by_id(project, "char/ranger_walk")
    # 8 cells of 32px across, 1 down -> a 256x32 sheet, doubled to 512x64.
    assert request.size == (512, 64)
    assert request.final_size == (32, 32)


def test_world_tiles_render_at_the_generation_size(project: Path):
    assert _by_id(project, "terrain/moss_stone").size == (512, 512)


def test_screen_space_ui_may_use_a_finer_quantum_than_the_grid(project: Path):
    # 64x16 on a 32px grid is legitimate for UI, and must not be rejected.
    request = _by_id(project, "ui/button_normal")
    assert request.final_size == (64, 16)


def test_world_assets_must_be_a_multiple_of_the_grid(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/odd\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [33, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _plan(project)
    assert "not a multiple of 32" in str(caught.value)


def test_asset_filter_limits_the_plan(project: Path):
    config = load_config(project)
    plan = build_plan(config, load_specs(config), assets=["ui/button_normal"])
    assert [r.asset_id for r in plan.requests] == ["ui/button_normal"]


def test_unknown_asset_filter_is_an_error(project: Path):
    config = load_config(project)
    with pytest.raises(SpecError) as caught:
        build_plan(config, load_specs(config), assets=["terrain/nope"])
    assert "unknown asset id" in str(caught.value)


def test_references_are_hashed_by_content(project: Path):
    request = _by_id(project, "terrain/moss_stone")
    ref = request.refs[0]
    assert ref.role.value == "style_anchor"
    assert ref.sha256.startswith("sha256:")
    assert ref.backend_handle is None


def test_request_hash_ignores_volatile_upload_handles(project: Path):
    request = _by_id(project, "terrain/moss_stone")
    with_handle = replace(
        request,
        refs=tuple(replace(ref, backend_handle="floor_uploaded.png") for ref in request.refs),
    )
    assert with_handle.request_hash == request.request_hash


def test_request_hash_changes_with_the_seed(project: Path):
    request = _by_id(project, "terrain/moss_stone")
    assert replace(request, seed=request.seed + 1).request_hash != request.request_hash


def test_plan_carries_the_style_hash_into_every_request(project: Path):
    plan = _plan(project)
    style_hash = load_config(project).style.contract_hash
    assert plan.style_hash == style_hash
    assert all(request.style_hash == style_hash for request in plan.requests)


def test_audio_kinds_have_no_render_size(tmp_path: Path):
    make_project(
        tmp_path,
        assets={
            "assets/audio.yaml": (
                "schema: 1\n"
                "assets:\n"
                "  - id: sfx/click\n"
                "    kind: sfx\n"
                "    prompt: short wooden ui click\n"
                "    size: [1, 1]\n"
            )
        },
    )
    request = _by_id(tmp_path, "sfx/click")
    assert request.kind is AssetKind.SFX
    assert request.size is None
