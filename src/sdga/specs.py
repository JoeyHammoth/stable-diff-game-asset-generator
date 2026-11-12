"""`assets/*.yaml` loading and strict validation (docs/03-contracts-and-schemas.md §2).

One file may declare several assets. Validation is deliberately unforgiving: unknown keys
are errors, not warnings, because a typo'd `refernces:` would otherwise produce an asset
that silently ignores its style anchor and still looks plausible.

Error messages carry `file:line`, resolved from the composed YAML node tree.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .config import Config
from .errors import ConfigError, SpecError
from .model import (
    SCHEMA,
    AssetKind,
    AssetSpec,
    ReferenceRole,
    SeedPolicy,
    SpecSource,
)
from .paths import relative_path

ID_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")

_TOP_KEYS = {"schema", "defaults", "assets"}
_DEFAULTS_KEYS = {"params"}
_ASSET_KEYS = {
    "id",
    "kind",
    "prompt",
    "negative",
    "size",
    "frames",
    "layout",
    "references",
    "params",
    "gates",
    "candidates",
    "depends_on",
    "seed",
}
_LAYOUT_KEYS = {"cols", "rows"}

_PROMPT_OPTIONAL_KINDS = {AssetKind.NORMAL_MAP}
_ANIMATED_KINDS = {AssetKind.SPRITE_SHEET}


class _Lines:
    """Best-effort `file:line` from a composed YAML document. Never raises."""

    def __init__(self, root: Any) -> None:
        self._root = root

    def node(self, path: Sequence[object]) -> Any:
        node = self._root
        for step in path:
            if node is None:
                return None
            if isinstance(step, int):
                if not isinstance(node, yaml.SequenceNode):
                    return None
                items = node.value
                if not 0 <= step < len(items):
                    return None
                node = items[step]
            else:
                if not isinstance(node, yaml.MappingNode):
                    return None
                for key, value in node.value:
                    if isinstance(key, yaml.ScalarNode) and key.value == str(step):
                        node = value
                        break
                else:
                    return None
        return node

    def line(self, path: Sequence[object], key: str | None = None) -> int | None:
        node = self.node(path)
        if node is None:
            return None
        if key is None:
            node_line: int = node.start_mark.line + 1
            return node_line
        if not isinstance(node, yaml.MappingNode):
            return None
        for candidate, _ in node.value:
            if isinstance(candidate, yaml.ScalarNode) and candidate.value == str(key):
                key_line: int = candidate.start_mark.line + 1
                return key_line
        return None


def _suggest(key: str, allowed: Iterable[str]) -> str:
    near = difflib.get_close_matches(str(key), sorted(allowed), n=1)
    return f" (did you mean {near[0]!r}?)" if near else ""


def load_specs(config: Config) -> tuple[AssetSpec, ...]:
    """Load, validate, and order every asset spec in the project. Deterministic."""
    paths = config.asset_paths()
    if not paths:
        patterns = ", ".join(config.project.asset_globs)
        raise SpecError(
            f"no asset specs matched {patterns}",
            location=str(config.root),
            remedy="add assets/*.yaml, or fix [project] asset_globs in sdga.toml",
        )

    specs: list[AssetSpec] = []
    for path in paths:
        specs.extend(_load_file(path, config))

    _check_unique_ids(specs)
    _check_depends(specs)
    return tuple(sorted(specs, key=lambda spec: spec.id))


def _load_file(path: Path, config: Config) -> list[AssetSpec]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read asset file: {exc}", location=str(path)) from None

    display = _display(path, config.root)
    try:
        document = yaml.safe_load(text)
        composed = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"invalid YAML: {exc}", location=display) from None

    if document is None:
        raise SpecError("empty asset file", location=display)
    if not isinstance(document, dict):
        raise SpecError(
            "an asset file must be a mapping containing 'assets'",
            location=display,
            remedy="see docs/03-contracts-and-schemas.md §2",
        )

    lines = _Lines(composed)
    for key in document:
        if key not in _TOP_KEYS:
            raise SpecError(
                f"unknown key {key!r}{_suggest(key, _TOP_KEYS)}",
                location=f"{display}:{lines.line((), key)}",
                remedy=f"allowed keys: {', '.join(sorted(_TOP_KEYS))}",
            )

    schema = document.get("schema", SCHEMA)
    if schema != SCHEMA:
        raise SpecError(
            f"unsupported schema {schema!r}",
            location=f"{display}:{lines.line(('schema',))}",
            remedy=f"this build reads schema {SCHEMA} only",
        )

    defaults = document.get("defaults", {})
    if not isinstance(defaults, dict):
        raise SpecError("defaults must be a mapping", location=display)
    for key in defaults:
        if key not in _DEFAULTS_KEYS:
            raise SpecError(
                f"unknown key {key!r} in defaults{_suggest(key, _DEFAULTS_KEYS)}",
                location=f"{display}:{lines.line(('defaults',), key)}",
            )
    default_params = defaults.get("params", {})
    if not isinstance(default_params, dict):
        raise SpecError("defaults.params must be a mapping", location=display)

    raw_assets = document.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise SpecError(
            "assets must be a non-empty list",
            location=f"{display}:{lines.line(('assets',))}",
        )

    specs: list[AssetSpec] = []
    for index, raw in enumerate(raw_assets):
        specs.append(_parse_asset(raw, index, display, lines, config, default_params))
    return specs


def _parse_asset(
    raw: Any,
    index: int,
    display: str,
    lines: _Lines,
    config: Config,
    default_params: Mapping[str, Any],
) -> AssetSpec:
    where = f"{display}:{lines.line(('assets', index))}"

    if not isinstance(raw, dict):
        raise SpecError("each asset must be a mapping", location=where)

    for key in raw:
        if key not in _ASSET_KEYS:
            raise SpecError(
                f"unknown key {key!r}{_suggest(key, _ASSET_KEYS)}",
                location=f"{display}:{lines.line(('assets', index), key)}",
                remedy=f"allowed keys: {', '.join(sorted(_ASSET_KEYS))}",
            )

    asset_id = raw.get("id")
    if not isinstance(asset_id, str) or not ID_RE.match(asset_id):
        raise SpecError(
            f"invalid asset id {asset_id!r}",
            location=where,
            remedy="ids are 'namespace/name' in lowercase: ^[a-z0-9_]+(/[a-z0-9_]+)+$",
        )

    kind_raw = raw.get("kind")
    if kind_raw is None:
        raise SpecError("missing required key 'kind'", location=where)
    try:
        kind = AssetKind.parse(kind_raw)
    except ValueError as exc:
        raise SpecError(str(exc), location=where) from None

    prompt = raw.get("prompt", "")
    if not isinstance(prompt, str):
        raise SpecError("prompt must be a string", location=where)
    if kind not in _PROMPT_OPTIONAL_KINDS and not prompt.strip():
        raise SpecError(
            f"missing required key 'prompt' for kind {kind.value!r}",
            location=where,
            remedy="only normal_map derives its prompt from depends_on",
        )

    negative = raw.get("negative")
    if negative is not None and not isinstance(negative, str):
        raise SpecError("negative must be a string", location=where)

    size = _size(raw.get("size"), where)

    frames = raw.get("frames")
    if frames is not None and (isinstance(frames, bool) or not isinstance(frames, int)):
        raise SpecError("frames must be an integer", location=where)
    if kind in _ANIMATED_KINDS and frames is None:
        raise SpecError(f"kind {kind.value!r} requires 'frames'", location=where)
    if kind not in _ANIMATED_KINDS and frames is not None:
        raise SpecError(
            f"'frames' is only valid for sprite_sheet, not {kind.value!r}",
            location=where,
            remedy="remove frames, or change the kind",
        )
    if frames is not None and frames < 1:
        raise SpecError("frames must be >= 1", location=where)

    layout = _layout(raw.get("layout"), frames, kind, where)

    references = _references(raw.get("references"), where, config)
    params = _mapping(raw.get("params"), "params", where)
    gates = _mapping(raw.get("gates"), "gates", where)

    candidates = raw.get("candidates", 1)
    if isinstance(candidates, bool) or not isinstance(candidates, int) or candidates < 1:
        raise SpecError("candidates must be an integer >= 1", location=where)

    depends_on = raw.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(dep, str) for dep in depends_on):
        raise SpecError("depends_on must be a list of asset ids", location=where)
    for dep in depends_on:
        if not ID_RE.match(dep):
            raise SpecError(f"invalid asset id in depends_on: {dep!r}", location=where)

    seed = raw.get("seed")
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
            raise SpecError("seed must be an integer in [0, 2^64)", location=where)
        if config.style.seed_policy is not SeedPolicy.FIXED:
            raise SpecError(
                f"seed is only valid with seed_policy = 'fixed', not "
                f"{config.style.seed_policy.value!r}",
                location=where,
                remedy="remove the seed to use derived seeding, or change [style] seed_policy",
            )

    merged_params: dict[str, Any] = dict(default_params)
    merged_params.update(params)

    return AssetSpec(
        id=asset_id,
        kind=kind,
        prompt=prompt.strip(),
        size=size,
        negative=None if negative is None else negative.strip(),
        frames=frames,
        layout=layout,
        references=references,
        params=merged_params,
        gates=gates,
        candidates=candidates,
        depends_on=tuple(depends_on),
        seed=seed,
        source=SpecSource(path=display, line=lines.line(("assets", index))),
    )


def _size(value: Any, where: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in value)
    ):
        raise SpecError(
            "size must be two positive integers, e.g. [32, 32]",
            location=where,
            remedy="size is in final pixels; for sprite_sheet it is the cell size",
        )
    return (int(value[0]), int(value[1]))


def _layout(value: Any, frames: int | None, kind: AssetKind, where: str) -> tuple[int, int] | None:
    if value is None:
        return None if frames is None else (frames, 1)
    if not isinstance(value, dict):
        raise SpecError("layout must be a mapping of cols and rows", location=where)
    for key in value:
        if key not in _LAYOUT_KEYS:
            raise SpecError(
                f"unknown key {key!r} in layout{_suggest(key, _LAYOUT_KEYS)}", location=where
            )
    cols = value.get("cols")
    rows = value.get("rows")
    if isinstance(cols, bool) or not isinstance(cols, int) or cols < 1:
        raise SpecError("layout.cols must be an integer >= 1", location=where)
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
        raise SpecError("layout.rows must be an integer >= 1", location=where)
    if frames is None:
        raise SpecError(
            f"layout is only valid for animated kinds, not {kind.value!r}", location=where
        )
    if cols * rows != frames:
        raise SpecError(
            f"layout.cols * layout.rows is {cols * rows} but frames is {frames}",
            location=where,
        )
    return (cols, rows)


def _references(value: Any, where: str, config: Config) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SpecError("references must be a mapping of role: path", location=where)
    resolved: dict[str, str] = {}
    for role_raw, path_raw in value.items():
        try:
            role = ReferenceRole.parse(role_raw)
        except ValueError as exc:
            raise SpecError(str(exc), location=where) from None
        try:
            rel = relative_path(path_raw, where, f"references.{role.value}")
        except ConfigError as exc:
            raise SpecError(exc.message, location=where, remedy=exc.remedy) from None
        if not (config.root / rel).is_file():
            raise SpecError(
                f"reference file not found: {rel}",
                location=where,
                remedy=f"add it under the project root ({config.root.name}/) or fix the path",
            )
        resolved[role.value] = rel
    return resolved


def _mapping(value: Any, key: str, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SpecError(f"{key} must be a mapping", location=where)
    return dict(value)


def _check_unique_ids(specs: Iterable[AssetSpec]) -> None:
    seen: dict[str, AssetSpec] = {}
    for spec in specs:
        other = seen.get(spec.id)
        if other is not None:
            first = other.source.location() if other.source else "another file"
            raise SpecError(
                f"duplicate asset id {spec.id!r} (also declared at {first})",
                location=spec.source.location() if spec.source else None,
                remedy="one asset id, one spec; rename or remove one of them",
            )
        seen[spec.id] = spec


def _check_depends(specs: Sequence[AssetSpec]) -> None:
    known = {spec.id for spec in specs}
    for spec in specs:
        for dep in spec.depends_on:
            if dep not in known:
                raise SpecError(
                    f"{spec.id}: depends_on references unknown asset {dep!r}",
                    location=spec.source.location() if spec.source else None,
                    remedy=f"known ids: {', '.join(sorted(known))}",
                )

    graph = {spec.id: [dep for dep in spec.depends_on] for spec in specs}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in done:
            return
        if node in visiting:
            cycle = " -> ".join([*trail[trail.index(node) :], node])
            raise SpecError(
                f"depends_on cycle: {cycle}",
                remedy="dependency graphs must be acyclic so plan order is well defined",
            )
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep, [*trail, node])
        visiting.discard(node)
        done.add(node)

    for asset_id in sorted(graph):
        visit(asset_id, [])


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = ["ID_RE", "load_specs"]
