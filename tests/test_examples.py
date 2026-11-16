from __future__ import annotations

from pathlib import Path

from sdga.backends.comfyui import load_recipes
from sdga.config import load_config
from sdga.planning import build_plan
from sdga.specs import load_specs

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_examples_project_is_valid():
    config = load_config(EXAMPLES)
    # Every kind in phases P2 and P4 is represented, so the project exercises each recipe and
    # both backend families.
    kinds = {spec.kind.value for spec in load_specs(config)}
    assert kinds == {
        "concept",
        "icon",
        "music_track",
        "normal_map",
        "sfx",
        "sprite_sheet",
        "terrain_tile",
        "ui_element",
    }


def test_the_soundtrack_derives_from_one_leitmotif():
    # The P4 gate, as a property of the shipped data.
    config = load_config(EXAMPLES)
    tracks = [spec for spec in load_specs(config) if spec.kind.value == "music_track"]
    assert len(tracks) == 8
    sources = {(spec.music or {}).get("leitmotif") for spec in tracks}
    assert sources == {"leitmotif/leitmotif_core.mid"}
    assert (EXAMPLES / "leitmotif" / "leitmotif_core.mid").is_file()


def test_the_examples_palette_is_a_png_swatch_grid():
    # The example project is the only end-to-end config we ship, so it must cover the
    # image palette path (`_read_png`), not just the GIMP `.gpl` one.
    style = load_config(EXAMPLES).style
    assert style.palette.path == "palettes/example16.png"
    assert style.palette.colors == 16


def test_committed_plan_json_matches_a_fresh_plan():
    # The CI check from docs/07: `sdga plan --dry-run examples/ && git diff --exit-code`.
    config = load_config(EXAMPLES)
    expected = build_plan(config, load_specs(config), recipes=load_recipes(config)).to_json()
    actual = (EXAMPLES / "plan.json").read_text(encoding="utf-8")
    assert actual == expected, "run `sdga plan --project examples` and commit plan.json"
