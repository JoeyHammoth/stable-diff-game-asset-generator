from __future__ import annotations

from pathlib import Path

from sdga.backends.comfyui import load_recipes
from sdga.config import load_config
from sdga.planning import build_plan
from sdga.specs import load_specs

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_examples_project_is_valid():
    config = load_config(EXAMPLES)
    # Every image kind in phase P2 is represented, so the project exercises each recipe.
    kinds = {spec.kind.value for spec in load_specs(config)}
    assert kinds == {
        "concept",
        "icon",
        "normal_map",
        "sprite_sheet",
        "terrain_tile",
        "ui_element",
    }


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
