from __future__ import annotations

from pathlib import Path

import pytest
from _project import make_project

from sdga.config import load_config
from sdga.errors import SpecError
from sdga.model import AssetKind
from sdga.specs import load_specs


def _specs(root: Path):
    return load_specs(load_config(root))


def test_loads_all_assets_sorted_by_id(project: Path):
    specs = _specs(project)
    ids = [spec.id for spec in specs]
    assert ids == sorted(ids)
    assert ids == [
        "char/ranger_walk",
        "terrain/moss_stone",
        "terrain/moss_stone_normal",
        "ui/button_normal",
    ]


def test_sprite_sheet_defaults_to_a_single_row(project: Path):
    spec = next(s for s in _specs(project) if s.id == "char/ranger_walk")
    assert spec.kind is AssetKind.SPRITE_SHEET
    assert spec.frames == 8
    assert spec.layout == (8, 1)
    assert spec.slug == "char__ranger_walk"


def test_default_params_merge_under_spec_params(project: Path):
    spec = next(s for s in _specs(project) if s.id == "terrain/moss_stone")
    assert spec.params["steps"] == 25
    assert spec.params["denoise"] == 1.0


def test_unknown_key_reports_the_file_and_the_offending_line(project: Path):
    bad = project / "assets" / "bad.yaml"
    bad.write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/broken\n"
        "    kind: terrain_tile\n"
        "    prompt: moss floor\n"
        "    size: [32, 32]\n"
        "    refernces:\n"
        "      style_anchor: concepts/cleaned/floor.png\n",
        encoding="utf-8",
    )

    with pytest.raises(SpecError) as caught:
        _specs(project)

    error = caught.value
    assert error.location is not None
    path_part, line_part = error.location.rsplit(":", 1)
    assert path_part.endswith("bad.yaml")
    assert "did you mean 'references'" in str(error)
    # The reported line must actually be the typo, not just *a* line.
    assert "refernces" in bad.read_text(encoding="utf-8").splitlines()[int(line_part) - 1]


def test_duplicate_ids_are_rejected_and_both_locations_named(project: Path):
    (project / "assets" / "dup.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/moss_stone\n"
        "    kind: terrain_tile\n"
        "    prompt: another moss floor\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "duplicate asset id" in str(caught.value)
    assert "also declared at" in str(caught.value)


def test_invalid_id_pattern_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: MossStone\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "invalid asset id" in str(caught.value)


def test_missing_reference_file_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n"
        "    references:\n"
        "      style_anchor: concepts/cleaned/missing.png\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "concepts/cleaned/missing.png" in str(caught.value)


def test_absolute_reference_path_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n"
        "    references:\n"
        "      style_anchor: C:/tmp/floor.png\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "relative" in str(caught.value)


def test_unknown_reference_role_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n"
        "    references:\n"
        "      styl_anchor: concepts/cleaned/floor.png\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "unknown reference role" in str(caught.value)


def test_sprite_sheet_requires_frames(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: char/blob\n"
        "    kind: sprite_sheet\n"
        "    prompt: blob\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "requires 'frames'" in str(caught.value)


def test_layout_must_cover_every_frame(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: char/blob\n"
        "    kind: sprite_sheet\n"
        "    prompt: blob\n"
        "    size: [32, 32]\n"
        "    frames: 8\n"
        "    layout: { cols: 3, rows: 3 }\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "layout.cols * layout.rows" in str(caught.value)


def test_frames_on_a_non_animated_kind_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n"
        "    frames: 4\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "only valid for sprite_sheet" in str(caught.value)


def test_depends_on_unknown_id_is_rejected(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other_normal\n"
        "    kind: normal_map\n"
        "    depends_on: [terrain/ghost]\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "terrain/ghost" in str(caught.value)


def test_dependency_cycles_are_rejected(project: Path):
    (project / "assets" / "cycle.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/alpha\n"
        "    kind: normal_map\n"
        "    depends_on: [terrain/beta]\n"
        "    size: [32, 32]\n"
        "  - id: terrain/beta\n"
        "    kind: normal_map\n"
        "    depends_on: [terrain/alpha]\n"
        "    size: [32, 32]\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "cycle" in str(caught.value)


def test_seed_requires_the_fixed_policy(project: Path):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\n"
        "assets:\n"
        "  - id: terrain/other\n"
        "    kind: terrain_tile\n"
        "    prompt: moss\n"
        "    size: [32, 32]\n"
        "    seed: 42\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError) as caught:
        _specs(project)
    assert "seed_policy" in str(caught.value)


def test_empty_project_reports_the_globs_it_looked_for(tmp_path: Path):
    make_project(tmp_path, assets={})
    (tmp_path / "assets").mkdir(exist_ok=True)
    with pytest.raises(SpecError) as caught:
        _specs(tmp_path)
    assert "assets/**/*.yaml" in str(caught.value)
