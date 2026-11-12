"""Recipe loading and `${slot}` binding (docs/03-contracts-and-schemas.md §3).

Recipes are data: a graph in API format with markers, a `requires` block, a declared output
node, and the deterministic chain that follows generation. Nothing here knows about any
particular asset kind.

Markers rather than node-number patching because node ids are an artefact of graph editing:
a marker survives renumbering, shows up in a diff, and documents which parameters a recipe
accepts. Binding is also what lets the fake backend exercise slot bugs without a GPU.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ...config import Config
from ...doctor import Requirement
from ...errors import RecipeError, SlotResolutionError
from ...model import AssetKind, StyleContract
from ...postprocess import OPS
from ...validate import GATES

CONTEXT_ROOTS = frozenset(
    {
        "positive",
        "negative",
        "seed",
        "width",
        "height",
        "final_width",
        "final_height",
        "filename_prefix",
        "style",
        "params",
        "asset",
    }
)

OUTPUT_CLASSES = frozenset({"SaveImage", "PreviewImage", "SaveAnimatedWEBP"})

_RECIPE_KEYS = {
    "schema",
    "id",
    "version",
    "graph",
    "output_node",
    "postprocess",
    "gates",
    "requires",
    "slots",
}
_MARKER = re.compile(r"^\$\{(.+)\}$")
_PART = re.compile(r"^(?P<name>[A-Za-z_][\w]*)(?P<index>\[(?P<position>\d+)\])?$")


@dataclass(frozen=True)
class Recipe:
    id: str
    version: int
    output_node: str
    graph: Mapping[str, Any]
    postprocess: tuple[str, ...]
    gates: tuple[str, ...]
    requires_nodes: tuple[str, ...]
    requires_models: Mapping[str, tuple[str, ...]]
    slots_required: tuple[str, ...]
    slots_optional: tuple[str, ...]
    source: str = ""

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    def bind(self, context: Mapping[str, Any]) -> dict[str, Any]:
        """Copy the graph with every marker resolved. Types are preserved."""
        bound: dict[str, Any] = {}
        for node_id, node in self.graph.items():
            inputs = {
                name: _resolve(value, context, where=f"{self.key}:{node_id}.{name}")
                for name, value in (node.get("inputs") or {}).items()
            }
            bound[str(node_id)] = {"class_type": node["class_type"], "inputs": inputs}
        _validate_links(bound, self.key)
        return bound


@dataclass(frozen=True)
class RecipeRegistry:
    recipes: Mapping[str, Recipe]

    @property
    def versions(self) -> dict[str, str]:
        return {recipe_id: str(recipe.version) for recipe_id, recipe in self.recipes.items()}

    def get(self, recipe_id: str) -> Recipe | None:
        return self.recipes.get(recipe_id)

    def for_kind(self, kind: AssetKind) -> Recipe | None:
        return self.recipes.get(kind.value)

    def requirements(self, style: StyleContract) -> tuple[Requirement, ...]:
        """What each recipe needs from a backend, with `${style.*}` resolved."""
        context: dict[str, Any] = {"style": style.style_body(), "params": {}, "asset": {}}
        result: list[Requirement] = []
        for recipe in self.recipes.values():
            models: dict[str, tuple[str, ...]] = {}
            for folder, templates in recipe.requires_models.items():
                resolved: list[str] = []
                for template in templates:
                    try:
                        value = _resolve(template, context, where=f"{recipe.key}.requires")
                    except SlotResolutionError:
                        # Unresolvable here (e.g. no lora configured) is a bind-time error,
                        # not a reason for doctor to crash.
                        continue
                    resolved.append(str(value))
                models[folder] = tuple(resolved)
            result.append(
                Requirement(recipe=recipe.key, nodes=recipe.requires_nodes, models=models)
            )
        return tuple(result)


def load_recipes(config: Config) -> RecipeRegistry:
    directory = config.root / config.project.recipes_dir
    if not directory.is_dir():
        return RecipeRegistry({})

    recipes: dict[str, Recipe] = {}
    for path in sorted(directory.glob("*.yaml")):
        recipe = load_recipe(path)
        if recipe.id in recipes:
            raise RecipeError(
                f"duplicate recipe id {recipe.id!r}",
                location=path.name,
                remedy=f"already defined by {recipes[recipe.id].source}",
            )
        recipes[recipe.id] = recipe
    return RecipeRegistry(recipes)


def load_recipe(path: Path) -> Recipe:
    display = path.as_posix()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RecipeError(f"cannot read recipe: {exc}", location=display) from None

    if not isinstance(document, dict):
        raise RecipeError("a recipe must be a mapping", location=display)

    for key in document:
        if key not in _RECIPE_KEYS:
            near = difflib.get_close_matches(str(key), sorted(_RECIPE_KEYS), n=1)
            hint = f" (did you mean {near[0]!r}?)" if near else ""
            raise RecipeError(
                f"unknown recipe key {key!r}{hint}",
                location=display,
                remedy=f"allowed keys: {', '.join(sorted(_RECIPE_KEYS))}",
            )

    schema = document.get("schema", 1)
    if schema != 1:
        raise RecipeError(f"unsupported recipe schema {schema!r}", location=display)

    recipe_id = document.get("id")
    if not isinstance(recipe_id, str) or not recipe_id:
        raise RecipeError("recipe id must be a non-empty string", location=display)

    version = document.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise RecipeError("recipe version must be an integer >= 1", location=display)

    graph_name = document.get("graph")
    if not isinstance(graph_name, str) or not graph_name:
        raise RecipeError("recipe graph must name a JSON file", location=display)
    graph_path = path.parent / graph_name
    if not graph_path.is_file():
        raise RecipeError(f"graph file not found: {graph_name}", location=display)
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecipeError(f"invalid graph JSON: {exc}", location=graph_path.as_posix()) from None
    if not isinstance(graph, dict) or not graph:
        raise RecipeError("graph must be a non-empty object", location=graph_path.as_posix())

    for node_id, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node:
            raise RecipeError(f"node {node_id!r} has no class_type", location=graph_path.as_posix())

    output_node = str(document.get("output_node", ""))
    if not output_node:
        raise RecipeError("output_node is required", location=display)
    if output_node not in graph:
        raise RecipeError(
            f"output_node {output_node!r} is not in the graph",
            location=display,
            remedy=f"known node ids: {', '.join(sorted(graph))}",
        )
    output_class = graph[output_node].get("class_type")
    if output_class not in OUTPUT_CLASSES:
        raise RecipeError(
            f"output_node {output_node!r} is a {output_class!r}, not an output node",
            location=display,
            remedy=f"output nodes are: {', '.join(sorted(OUTPUT_CLASSES))}",
        )

    postprocess = _names(document.get("postprocess"), "postprocess", display)
    for name in postprocess:
        if name not in OPS:
            raise RecipeError(
                f"unknown postprocess op {name!r}",
                location=display,
                remedy=f"known ops: {', '.join(sorted(OPS))}",
            )

    gates = _names(document.get("gates"), "gates", display)
    for name in gates:
        if name not in GATES:
            raise RecipeError(
                f"unknown gate {name!r}",
                location=display,
                remedy=f"known gates: {', '.join(sorted(GATES))}",
            )

    requires = document.get("requires") or {}
    if not isinstance(requires, dict):
        raise RecipeError("requires must be a mapping", location=display)
    nodes = tuple(str(node) for node in requires.get("nodes") or ())
    raw_models = requires.get("models") or {}
    if not isinstance(raw_models, dict):
        raise RecipeError("requires.models must be a mapping of folder: [names]", location=display)
    models = {
        str(folder): tuple(str(name) for name in names or ())
        for folder, names in raw_models.items()
    }

    slots = document.get("slots") or {}
    if not isinstance(slots, dict):
        raise RecipeError("slots must be a mapping", location=display)
    slots_required = tuple(str(name) for name in slots.get("required") or ())
    slots_optional = tuple(str(name) for name in slots.get("optional") or ())

    for expr in _markers(graph):
        root = re.split(r"[.\[]", expr, maxsplit=1)[0]
        if root not in CONTEXT_ROOTS:
            raise RecipeError(
                f"unknown slot root {root!r} in ${{{expr}}}",
                location=graph_path.as_posix(),
                remedy=f"slot roots are: {', '.join(sorted(CONTEXT_ROOTS))}",
            )

    return Recipe(
        id=recipe_id,
        version=version,
        output_node=output_node,
        graph=graph,
        postprocess=postprocess,
        gates=gates,
        requires_nodes=nodes,
        requires_models=models,
        slots_required=slots_required,
        slots_optional=slots_optional,
        source=display,
    )


def _names(raw: Any, key: str, display: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise RecipeError(f"{key} must be a list of names", location=display)
    return tuple(raw)


def _markers(value: Any) -> list[str]:
    """Every `${...}` expression in a graph, in encounter order."""
    found: list[str] = []
    if isinstance(value, str):
        match = _MARKER.match(value)
        if match:
            found.append(match.group(1))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_markers(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_markers(item))
    return found


def _resolve(value: Any, context: Mapping[str, Any], *, where: str) -> Any:
    if isinstance(value, str):
        match = _MARKER.match(value)
        if match:
            return _lookup(match.group(1), context, where=where)
        if "${" in value:
            raise SlotResolutionError(
                f"slot marker must be the whole string: {value!r}",
                location=where,
                remedy='use a full marker, for example "${params.sampler}"',
            )
        return value
    if isinstance(value, list):
        if (
            len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
            and not isinstance(value[1], bool)
        ):
            return [value[0], value[1]]
        return [_resolve(item, context, where=where) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, context, where=where) for key, item in value.items()}
    return value


def _lookup(expr: str, context: Mapping[str, Any], *, where: str) -> Any:
    current: Any = context
    for part in expr.split("."):
        match = _PART.match(part)
        if match is None:
            raise SlotResolutionError(
                f"malformed slot expression ${{{expr}}}",
                location=where,
                remedy="use dotted paths like style.loras[0].name",
            )
        name = match.group("name")
        if name:
            if not isinstance(current, Mapping) or name not in current:
                raise SlotResolutionError(
                    f"cannot resolve ${{{expr}}}: no {name!r}",
                    location=where,
                    remedy="check the spec params and [style] table provide this value",
                )
            current = current[name]
        position = match.group("position")
        if position is not None:
            try:
                current = current[int(position)]
            except (IndexError, KeyError, TypeError):
                raise SlotResolutionError(
                    f"cannot resolve ${{{expr}}}: index {position} is out of range",
                    location=where,
                ) from None

    if current is None:
        raise SlotResolutionError(
            f"${{{expr}}} resolved to null",
            location=where,
            remedy="a missing slot must fail at plan time, never reach the backend as null",
        )
    return current


def _validate_links(graph: Mapping[str, Any], recipe_key: str) -> None:
    for node_id, node in graph.items():
        for name, value in node["inputs"].items():
            if not (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                continue
            source = value[0]
            if source not in graph:
                raise RecipeError(
                    f"{recipe_key}: input {node_id}.{name} links to missing node {source!r}",
                    remedy="hand-editing the graph orphaned a node",
                )
            if value[1] < 0:
                raise RecipeError(
                    f"{recipe_key}: input {node_id}.{name} has a negative output slot"
                )


__all__ = [
    "CONTEXT_ROOTS",
    "OUTPUT_CLASSES",
    "Recipe",
    "RecipeRegistry",
    "load_recipe",
    "load_recipes",
]
