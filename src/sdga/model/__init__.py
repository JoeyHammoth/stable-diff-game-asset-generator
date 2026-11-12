"""Domain types (docs/02-domain-model.md).

Types only: no I/O, no YAML, no HTTP, no filesystem reads. Anything that touches the world
lives in `config`, `specs`, or `backends`, which is what makes the pipeline testable without
a GPU.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from ..canonical import fold32, hash_obj

SCHEMA = 1


class AssetKind(StrEnum):
    """The closed set of kinds. A kind selects recipe, postprocess chain, gates and hints."""

    CONCEPT = "concept"
    TERRAIN_TILE = "terrain_tile"
    SPRITE_SHEET = "sprite_sheet"
    UI_ELEMENT = "ui_element"
    ICON = "icon"
    NORMAL_MAP = "normal_map"
    SFX = "sfx"
    MUSIC_TRACK = "music_track"

    @classmethod
    def parse(cls, raw: object) -> "AssetKind":
        try:
            return cls(str(raw))
        except ValueError:
            known = ", ".join(kind.value for kind in cls)
            raise ValueError(f"unknown asset kind {raw!r}; known kinds: {known}") from None


class SeedPolicy(StrEnum):
    FIXED = "fixed"
    DERIVED = "derived"
    RANDOM = "random"

    @classmethod
    def parse(cls, raw: object) -> "SeedPolicy":
        try:
            return cls(str(raw))
        except ValueError:
            known = ", ".join(policy.value for policy in cls)
            raise ValueError(f"unknown seed policy {raw!r}; known policies: {known}") from None


class ReferenceRole(StrEnum):
    """Roles, not filenames: a recipe binds a reference by role, so specs never name a node."""

    STYLE_ANCHOR = "style_anchor"
    POSE = "pose"
    WIREFRAME = "wireframe"
    ALBEDO = "albedo"
    PALETTE = "palette"
    MASK = "mask"

    @classmethod
    def parse(cls, raw: object) -> "ReferenceRole":
        try:
            return cls(str(raw))
        except ValueError:
            known = ", ".join(role.value for role in cls)
            raise ValueError(f"unknown reference role {raw!r}; known roles: {known}") from None


@dataclass(frozen=True)
class PaletteRef:
    path: str
    colors: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "colors": self.colors, "sha256": self.sha256}


@dataclass(frozen=True)
class LoraRef:
    name: str
    strength_model: float
    strength_clip: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "strength_model": self.strength_model,
            "strength_clip": self.strength_clip,
        }


@dataclass(frozen=True)
class StyleContract:
    """Everything that must be identical across a pack, reduced to a content hash.

    The hash covers `[style]` in full, the palette file's content hash, and (from phase P1)
    the id+hash of every recipe the pack uses. It deliberately excludes `[backend]`,
    `[pack]`, `[gates]` and `[project]`: changing `max_concurrency` must not invalidate art;
    changing an anchor word must.
    """

    name: str
    trigger_token: str
    grid: int
    generation_size: tuple[int, int]
    palette: PaletteRef
    checkpoint: str
    loras: tuple[LoraRef, ...]
    positive_anchors: tuple[str, ...]
    negative_anchors: tuple[str, ...]
    seed_policy: SeedPolicy

    def style_body(self) -> dict[str, Any]:
        """Exactly the `[style]` table, resolved. This is what the hash is taken over."""
        return {
            "name": self.name,
            "trigger_token": self.trigger_token,
            "grid": self.grid,
            "generation_size": list(self.generation_size),
            "palette": self.palette.to_dict(),
            "checkpoint": self.checkpoint,
            "loras": [lora.to_dict() for lora in self.loras],
            "positive_anchors": list(self.positive_anchors),
            "negative_anchors": list(self.negative_anchors),
            "seed_policy": self.seed_policy.value,
        }

    @property
    def contract_hash(self) -> str:
        return self.hash_with_recipes({})

    def hash_with_recipes(self, recipes: Mapping[str, str]) -> str:
        """Adds recipe id -> version. Used from phase P1, once recipes exist."""
        return hash_obj({"style": self.style_body(), "recipes": dict(sorted(recipes.items()))})


@dataclass(frozen=True)
class SpecSource:
    """Where an asset spec came from, for error messages. Never hashed."""

    path: str
    line: int | None = None

    def location(self, line: int | None = None) -> str:
        chosen = line if line is not None else self.line
        return f"{self.path}:{chosen}" if chosen else self.path


@dataclass(frozen=True)
class AssetSpec:
    """One human-authored asset description. Data, reviewed like code."""

    id: str
    kind: AssetKind
    prompt: str
    size: tuple[int, int]
    negative: str | None = None
    frames: int | None = None
    layout: tuple[int, int] | None = None
    references: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    gates: Mapping[str, Any] = field(default_factory=dict)
    candidates: int = 1
    depends_on: tuple[str, ...] = ()
    seed: int | None = None
    source: SpecSource | None = field(default=None, compare=False, repr=False)

    @property
    def slug(self) -> str:
        """Filesystem-safe form of the id, used for artifact names."""
        return self.id.replace("/", "__")


@dataclass(frozen=True)
class ResolvedRef:
    """A reference image resolved to content, with an optional backend upload handle."""

    role: ReferenceRole
    path: str
    sha256: str
    backend_handle: str | None = None

    def to_dict(self, *, include_handle: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "role": self.role.value,
            "path": self.path,
            "sha256": self.sha256,
        }
        if include_handle and self.backend_handle is not None:
            body["backend_handle"] = self.backend_handle
        return body


@dataclass(frozen=True)
class GenerationRequest:
    """A fully resolved instruction to a backend. Immutable, self-contained, hashable.

    `request_hash` is the cache key: canonical JSON over the body minus `request_id`,
    `graph`, and `refs[].backend_handle` (upload names are volatile). `request_id` is the
    same over the full body including the graph.
    """

    asset_id: str
    kind: AssetKind
    backend: str
    positive: str
    negative: str
    seed: int
    style_hash: str
    refs: tuple[ResolvedRef, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    size: tuple[int, int] | None = None
    final_size: tuple[int, int] | None = None
    recipe: str | None = None
    output_node: str | None = None
    graph: Mapping[str, Any] | None = None

    def _body(self, *, include_graph: bool, include_id: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": SCHEMA,
            "asset_id": self.asset_id,
            "kind": self.kind.value,
            "recipe": self.recipe,
            "backend": self.backend,
            "positive": self.positive,
            "negative": self.negative,
            "size": None if self.size is None else list(self.size),
            "final_size": None if self.final_size is None else list(self.final_size),
            "seed": self.seed,
            "refs": [ref.to_dict(include_handle=include_graph) for ref in self.refs],
            "params": dict(self.params),
            "style_hash": self.style_hash,
            "output_node": self.output_node,
        }
        if include_id:
            body["request_id"] = self.request_id
        if include_graph and self.graph is not None:
            body["graph"] = self.graph
        return body

    @property
    def request_hash(self) -> str:
        """The cache key. Never depends on node ids, upload names, or run identity."""
        return hash_obj(self._body(include_graph=False, include_id=False))

    @property
    def request_id(self) -> str:
        return hash_obj(self._body(include_graph=True, include_id=False))

    def to_dict(self) -> dict[str, Any]:
        return self._body(include_graph=True, include_id=True)


def derive_seed(asset_id: str, style_hash: str, candidate_index: int = 0) -> int:
    """The `derived` seed policy (docs/04-pipeline-stages.md §1 step 4).

    A pure function of identity: adding an unrelated asset can never change an existing
    asset's seed, so re-runs stay stable and diffs stay meaningful.
    """
    return fold32(f"{asset_id}|{style_hash}|{candidate_index}")


__all__ = [
    "SCHEMA",
    "AssetKind",
    "AssetSpec",
    "GenerationRequest",
    "LoraRef",
    "PaletteRef",
    "ReferenceRole",
    "ResolvedRef",
    "SeedPolicy",
    "SpecSource",
    "StyleContract",
    "derive_seed",
]
