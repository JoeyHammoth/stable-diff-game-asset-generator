from __future__ import annotations

from pathlib import Path

import pytest
from _project import TOML, make_project

from sdga.config import load_config
from sdga.errors import ConfigError
from sdga.model import SeedPolicy


def test_loads_a_valid_project(project: Path):
    config = load_config(project)
    assert config.project.name == "testgame"
    assert config.style.grid == 32
    assert config.style.palette.colors == 16
    assert config.style.seed_policy is SeedPolicy.DERIVED
    assert config.backend.kind == "fake"
    assert config.project.root == project.resolve()


def test_accepts_a_path_to_the_config_file(project: Path):
    assert load_config(project / "sdga.toml").project.name == "testgame"


def test_missing_config_is_a_schema_error(tmp_path: Path):
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "sdga.toml" in str(caught.value)
    assert caught.value.exit_code == 4


def test_unknown_style_key_suggests_the_real_one(tmp_path: Path):
    broken = TOML.replace("grid = 32", "gird = 32")
    make_project(tmp_path, toml=broken)
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    message = str(caught.value)
    assert "unknown key 'gird'" in message
    assert "did you mean 'grid'" in message
    assert "[style]" in message


def test_palette_count_must_match_the_palette_file(tmp_path: Path):
    broken = TOML.replace("palette_colors = 16", "palette_colors = 32")
    make_project(tmp_path, toml=broken)
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    message = str(caught.value)
    assert "32" in message and "16" in message
    assert "palette_colors" in message


def test_absolute_paths_are_rejected(tmp_path: Path):
    broken = TOML.replace('palette = "palettes/test.gpl"', 'palette = "C:/palettes/x.gpl"')
    make_project(tmp_path, toml=broken)
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "relative" in str(caught.value)


def test_unknown_backend_kind_is_rejected(tmp_path: Path):
    broken = TOML.replace('kind = "fake"', 'kind = "midjourney"')
    make_project(tmp_path, toml=broken)
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "comfyui" in str(caught.value)


def test_invalid_seed_policy_names_the_valid_ones(tmp_path: Path):
    broken = TOML.replace('seed_policy = "derived"', 'seed_policy = "chaotic"')
    make_project(tmp_path, toml=broken)
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "derived" in str(caught.value)


def test_style_hash_ignores_non_style_sections(tmp_path: Path):
    make_project(tmp_path)
    baseline = load_config(tmp_path).style.contract_hash

    changed_pack = TOML.replace("max_concurrency = 1", "max_concurrency = 4").replace(
        "require_review = true", "require_review = false"
    )
    make_project(tmp_path / "other", toml=changed_pack)
    assert load_config(tmp_path / "other").style.contract_hash == baseline


def test_style_hash_changes_when_an_anchor_changes(tmp_path: Path):
    make_project(tmp_path)
    baseline = load_config(tmp_path).style.contract_hash
    changed = TOML.replace('"clean pixel art"]', '"clean pixel art", "no dithering"]')
    make_project(tmp_path / "other", toml=changed)
    assert load_config(tmp_path / "other").style.contract_hash != baseline
