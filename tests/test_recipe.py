from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest
from _project import REPO_ROOT, make_project

from sdga.backends.comfyui.recipe import load_recipe, load_recipes
from sdga.config import load_config
from sdga.errors import RecipeError, SlotResolutionError

RECIPES = REPO_ROOT / "recipes"
TERRAIN = RECIPES / "terrain_tile.yaml"


def _context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "positive": "TestGameStyle, flat colours, moss",
        "negative": "photorealistic",
        "seed": 1234,
        "width": 512,
        "height": 512,
        "final_width": 32,
        "final_height": 32,
        "filename_prefix": "sdga/terrain__moss_stone",
        "style": {
            "checkpoint": "sd_v1-5.safetensors",
            "loras": [
                {
                    "name": "example_style.safetensors",
                    "strength_model": 0.85,
                    "strength_clip": 0.85,
                }
            ],
        },
        "params": {
            "steps": 25,
            "cfg": 7.0,
            "sampler": "euler_ancestral",
            "scheduler": "karras",
            "denoise": 1.0,
        },
        "asset": {"id": "terrain/moss_stone", "kind": "terrain_tile"},
    }
    context.update(overrides)
    return context


def _copy_recipe(
    tmp_path: Path,
    *,
    yaml_edit: Callable[[str], str] | None = None,
    graph_edit: Callable[[dict], dict] | None = None,
) -> Path:
    text = TERRAIN.read_text(encoding="utf-8")
    graph = json.loads((RECIPES / "terrain_tile.graph.json").read_text(encoding="utf-8"))
    if yaml_edit is not None:
        text = yaml_edit(text)
    if graph_edit is not None:
        graph = graph_edit(graph)
    (tmp_path / "terrain_tile.yaml").write_text(text, encoding="utf-8")
    (tmp_path / "terrain_tile.graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return tmp_path / "terrain_tile.yaml"


def test_loads_the_shipped_terrain_recipe():
    recipe = load_recipe(TERRAIN)
    assert recipe.id == "terrain_tile"
    assert recipe.version == 3
    assert recipe.key == "terrain_tile@3"
    assert recipe.output_node == "12"
    assert recipe.postprocess == (
        "downscale_box",
        "palette_snap",
        "alpha_hard",
        "pad_to_grid",
    )
    assert "seamless_tile" in recipe.gates
    assert "KSampler" in recipe.requires_nodes
    assert recipe.requires_models["checkpoints"] == ("${style.checkpoint}",)


def test_binding_preserves_types():
    graph = load_recipe(TERRAIN).bind(_context())
    sampler = graph["6"]["inputs"]
    assert sampler["seed"] == 1234
    assert isinstance(sampler["steps"], int) and sampler["steps"] == 25
    assert isinstance(sampler["cfg"], float) and sampler["cfg"] == 7.0
    assert sampler["sampler_name"] == "euler_ancestral"
    assert graph["5"]["inputs"]["width"] == 512
    assert graph["2"]["inputs"]["strength_model"] == 0.85
    assert graph["12"]["inputs"]["filename_prefix"] == "sdga/terrain__moss_stone"
    assert graph["6"]["inputs"]["model"] == ["2", 0]


def test_binding_leaves_the_recipe_graph_untouched():
    recipe = load_recipe(TERRAIN)
    before = json.dumps(recipe.graph, sort_keys=True)
    recipe.bind(_context())
    assert json.dumps(recipe.graph, sort_keys=True) == before


def test_a_missing_slot_fails_at_bind_time_with_a_location():
    context = _context()
    del context["params"]["denoise"]
    with pytest.raises(SlotResolutionError) as caught:
        load_recipe(TERRAIN).bind(context)
    assert "denoise" in str(caught.value)
    assert (caught.value.location or "").endswith("6.denoise")


def test_a_null_slot_is_never_passed_through():
    with pytest.raises(SlotResolutionError) as caught:
        load_recipe(TERRAIN).bind(_context(width=None))
    assert "null" in str(caught.value)


def test_a_partial_marker_is_rejected(tmp_path: Path):
    path = _copy_recipe(
        tmp_path,
        graph_edit=lambda graph: {
            **graph,
            "12": {
                "class_type": "SaveImage",
                "inputs": {"images": ["7", 0], "filename_prefix": "pre/${seed}"},
            },
        },
    )
    with pytest.raises(SlotResolutionError) as caught:
        load_recipe(path).bind(_context())
    assert "whole string" in str(caught.value)


def test_an_unknown_postprocess_op_is_caught_at_load(tmp_path: Path):
    path = _copy_recipe(tmp_path, yaml_edit=lambda text: text.replace("  - pad_to_grid", "  - sharpen"))
    with pytest.raises(RecipeError) as caught:
        load_recipe(path)
    assert "unknown postprocess op" in str(caught.value)
    assert "palette_snap" in str(caught.value)  # the remedy lists the real ops


def test_an_unknown_gate_is_caught_at_load(tmp_path: Path):
    path = _copy_recipe(
        tmp_path, yaml_edit=lambda text: text.replace("  - seamless_tile", "  - seamlessness")
    )
    with pytest.raises(RecipeError) as caught:
        load_recipe(path)
    assert "unknown gate" in str(caught.value)


def test_the_output_node_must_be_a_save_node(tmp_path: Path):
    path = _copy_recipe(tmp_path, yaml_edit=lambda text: text.replace('output_node: "12"', 'output_node: "7"'))
    with pytest.raises(RecipeError) as caught:
        load_recipe(path)
    assert "not an output node" in str(caught.value)


def test_an_orphaned_link_is_caught(tmp_path: Path):
    path = _copy_recipe(
        tmp_path,
        graph_edit=lambda graph: {
            **graph,
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["99", 0], "vae": ["1", 2]}},
        },
    )
    with pytest.raises(RecipeError) as caught:
        load_recipe(path).bind(_context())
    assert "missing node" in str(caught.value)


def test_a_graph_file_that_is_absent_is_reported(tmp_path: Path):
    path = _copy_recipe(tmp_path)
    (tmp_path / "terrain_tile.graph.json").unlink()
    with pytest.raises(RecipeError) as caught:
        load_recipe(path)
    assert "graph file not found" in str(caught.value)


def test_the_registry_exposes_versions_and_requirements(project: Path):
    config = load_config(project)
    registry = load_recipes(config)
    assert registry.versions == {"terrain_tile": "3"}
    assert registry.for_kind(load_recipe(TERRAIN).id and config.style and __import__("sdga").model.AssetKind.TERRAIN_TILE) is not None

    requirement = registry.requirements(config.style)[0]
    assert requirement.recipe == "terrain_tile@3"
    assert "KSampler" in requirement.nodes
    assert requirement.models["checkpoints"] == ("sd_v1-5.safetensors",)
    assert requirement.models["loras"] == ("testgame_style.safetensors",)


def test_a_project_without_recipes_gets_an_empty_registry(tmp_path: Path):
    make_project(tmp_path, with_recipes=False)
    assert load_recipes(load_config(tmp_path)).versions == {}


def test_duplicate_recipe_ids_are_rejected(project: Path):
    duplicate = project / "recipes" / "terrain_copy.yaml"
    duplicate.write_text(TERRAIN.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(RecipeError) as caught:
        load_recipes(load_config(project))
    assert "duplicate recipe id" in str(caught.value)
