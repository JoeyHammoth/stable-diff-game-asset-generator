"""Stage 1: plan (docs/04-pipeline-stages.md §1).

Deterministic and side-effect-free: the same inputs must produce a byte-identical
`plan.json`. Everything downstream (cache hits, regression diffs, `--dry-run` review)
depends on that property.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace
from typing import Any, Mapping, Protocol, Sequence

from ..canonical import hash_obj, hash_file, pretty_json
from ..config import Config
from ..errors import SpecError
from ..model import (
    SCHEMA,
    AssetKind,
    AssetSpec,
    GenerationRequest,
    ReferenceRole,
    ResolvedRef,
    SeedPolicy,
    StyleContract,
    derive_seed,
)

AUDIO_KINDS = frozenset({AssetKind.SFX, AssetKind.MUSIC_TRACK})

# Screen-space assets are not locked to the world pixel grid: a 16px-tall button is normal
# in a 32px-grid game, so they snap to a finer quantum.
SCREEN_SPACE_KINDS = frozenset({AssetKind.UI_ELEMENT, AssetKind.ICON})
UI_QUANTUM = 8

_WHITESPACE = re.compile(r"\s+")


class RecipeLike(Protocol):
    """What planning needs from a recipe.

    Structural, so planning never imports the ComfyUI package: a recipe is data and the
    binder is injected.
    """

    id: str
    version: int
    output_node: str

    @property
    def key(self) -> str: ...

    def bind(self, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RecipeRegistryLike(Protocol):
    def for_kind(self, kind: AssetKind) -> RecipeLike | None: ...


@dataclass(frozen=True)
class Plan:
    project: str
    style_name: str
    style_hash: str
    requests: tuple[GenerationRequest, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "project": self.project,
            "style": {"name": self.style_name, "contract_hash": self.style_hash},
            "requests": [request.to_dict() for request in self.requests],
        }

    def to_json(self) -> str:
        return pretty_json(self.to_dict())

    @property
    def plan_hash(self) -> str:
        return hash_obj(self.to_dict())


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def grid_quantum(kind: AssetKind, grid: int) -> int:
    """The divisor a final size must satisfy. UI is screen-space, world art is grid-locked."""
    return min(grid, UI_QUANTUM) if kind in SCREEN_SPACE_KINDS else grid


def assemble_positive(style: StyleContract, spec: AssetSpec) -> str:
    """Anchors first, subject last: the order the style LoRA was trained under."""
    parts = [anchor for anchor in style.positive_anchors if anchor.strip()]
    if spec.prompt.strip():
        parts.append(spec.prompt)
    return ", ".join(_normalise(part) for part in parts)


def assemble_negative(style: StyleContract, spec: AssetSpec) -> str:
    """A spec's negative overrides the contract's anchors entirely, never appends."""
    if spec.negative is not None:
        return _normalise(spec.negative)
    return ", ".join(_normalise(anchor) for anchor in style.negative_anchors if anchor.strip())


def render_size(style: StyleContract, spec: AssetSpec) -> tuple[int, int] | None:
    """Backend render size. Final size is the spec's; this is what we ask the sampler for."""
    if spec.kind in AUDIO_KINDS:
        return None
    if spec.kind is AssetKind.SPRITE_SHEET:
        cols, rows = spec.layout or (spec.frames or 1, 1)
        sheet_w = spec.size[0] * cols
        sheet_h = spec.size[1] * rows
        scale = min(
            style.generation_size[0] // sheet_w,
            style.generation_size[1] // sheet_h,
        )
        scale = max(1, scale)
        return (sheet_w * scale, sheet_h * scale)
    return style.generation_size


def resolve_seed(style: StyleContract, spec: AssetSpec) -> int:
    if style.seed_policy is SeedPolicy.FIXED:
        if spec.seed is None:
            raise SpecError(
                f"{spec.id}: seed_policy is 'fixed' but the spec declares no seed",
                location=spec.source.location() if spec.source else None,
                remedy="add `seed: <int>` to the spec, or use seed_policy = 'derived'",
            )
        return spec.seed
    if style.seed_policy is SeedPolicy.RANDOM:
        # Generated once and recorded in plan.json; intentional non-determinism.
        return secrets.randbits(32)
    return derive_seed(spec.id, style.contract_hash)


def resolve_refs(config: Config, spec: AssetSpec) -> tuple[ResolvedRef, ...]:
    """Content-hash each reference, ordered by role so the hash is stable."""
    refs: list[ResolvedRef] = []
    for role_name, rel in sorted(spec.references.items()):
        role = ReferenceRole(role_name)
        refs.append(
            ResolvedRef(
                role=role,
                path=rel,
                sha256=hash_file(config.root / rel),
            )
        )
    return tuple(refs)


def _check_quantum(spec: AssetSpec, style: StyleContract) -> None:
    if spec.kind in AUDIO_KINDS:
        return  # audio has no pixel grid; duration and beat alignment are its quanta
    quantum = grid_quantum(spec.kind, style.grid)
    for axis, dimension in zip(("width", "height"), spec.size):
        if dimension % quantum:
            raise SpecError(
                f"{spec.id}: {axis} {dimension} is not a multiple of {quantum}",
                location=spec.source.location() if spec.source else None,
                remedy=(
                    f"{spec.kind.value} assets snap to a {quantum}px quantum; "
                    "adjust the size or [style] grid"
                ),
            )


def bind_context(
    config: Config, spec: AssetSpec, request: GenerationRequest
) -> dict[str, Any]:
    """The flat namespace a recipe's `${slots}` resolve against (docs/03 §3, binder rule 2)."""
    return {
        "positive": request.positive,
        "negative": request.negative,
        "seed": request.seed,
        "width": None if request.size is None else request.size[0],
        "height": None if request.size is None else request.size[1],
        "final_width": spec.size[0],
        "final_height": spec.size[1],
        "filename_prefix": f"sdga/{spec.slug}",
        "style": config.style.style_body(),
        "params": dict(request.params),
        "asset": {"id": spec.id, "kind": spec.kind.value},
    }


def build_plan(
    config: Config,
    specs: Sequence[AssetSpec],
    *,
    assets: Sequence[str] | None = None,
    recipes: RecipeRegistryLike | None = None,
    require_recipes: bool = False,
) -> Plan:
    style = config.style
    selected = list(specs)

    if assets:
        known = {spec.id for spec in specs}
        unknown = sorted(set(assets) - known)
        if unknown:
            raise SpecError(
                f"unknown asset id(s): {', '.join(unknown)}",
                remedy=f"known ids: {', '.join(sorted(known))}",
            )
        wanted = set(assets)
        selected = [spec for spec in specs if spec.id in wanted]

    style_hash = style.contract_hash
    requests: list[GenerationRequest] = []
    for spec in selected:
        _check_quantum(spec, style)
        recipe = recipes.for_kind(spec.kind) if recipes is not None else None
        if recipe is None and require_recipes:
            raise SpecError(
                f"{spec.id}: no recipe for kind {spec.kind.value!r}",
                location=spec.source.location() if spec.source else None,
                remedy=f"add {config.project.recipes_dir}/{spec.kind.value}.yaml",
            )

        request = GenerationRequest(
            asset_id=spec.id,
            kind=spec.kind,
            backend=config.backend.kind,
            positive=assemble_positive(style, spec),
            negative=assemble_negative(style, spec),
            seed=resolve_seed(style, spec),
            style_hash=style_hash,
            refs=resolve_refs(config, spec),
            params=dict(spec.params),
            size=render_size(style, spec),
            final_size=spec.size,
        )
        if recipe is not None:
            request = replace(
                request,
                recipe=recipe.key,
                output_node=recipe.output_node,
                graph=recipe.bind(bind_context(config, spec, request)),
            )
        requests.append(request)

    return Plan(
        project=config.project.name,
        style_name=style.name,
        style_hash=style_hash,
        requests=tuple(requests),
    )


__all__ = [
    "AUDIO_KINDS",
    "Plan",
    "RecipeLike",
    "RecipeRegistryLike",
    "assemble_negative",
    "assemble_positive",
    "bind_context",
    "build_plan",
    "grid_quantum",
    "render_size",
    "resolve_refs",
    "resolve_seed",
]
