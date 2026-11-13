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


def test_a_png_palette_uses_its_distinct_colours(tmp_path: Path):
    from PIL import Image

    toml = TOML.replace('palette = "palettes/test.gpl"', 'palette = "palettes/test.png"').replace(
        "palette_colors = 16", "palette_colors = 3"
    )
    root = make_project(tmp_path, toml=toml)
    image = Image.new("RGBA", (2, 2))
    image.putpixel((0, 0), (31, 34, 41, 255))
    image.putpixel((1, 0), (58, 99, 64, 255))
    image.putpixel((0, 1), (200, 72, 72, 255))
    image.putpixel((1, 1), (0, 0, 0, 0))
    image.save(root / "palettes" / "test.png", format="PNG")

    config = load_config(root)
    assert config.style.palette.path == "palettes/test.png"
    assert config.style.palette.colors == 3
    assert config.style.palette.sha256.startswith("sha256:")


def test_a_png_palette_with_no_opaque_colour_is_rejected(tmp_path: Path):
    from PIL import Image

    toml = TOML.replace('palette = "palettes/test.gpl"', 'palette = "palettes/empty.png"')
    root = make_project(tmp_path, toml=toml)
    Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(root / "palettes" / "empty.png", format="PNG")

    with pytest.raises(ConfigError) as caught:
        load_config(root)
    assert "no colours" in str(caught.value)


def test_an_unknown_palette_format_names_the_supported_ones(tmp_path: Path):
    toml = TOML.replace('palette = "palettes/test.gpl"', 'palette = "palettes/test.pal"')
    root = make_project(tmp_path, toml=toml)
    (root / "palettes" / "test.pal").write_text("x", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        load_config(root)
    message = str(caught.value)
    assert ".gpl" in message and ".png" in message


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
