"""`sdga.toml` loading and strict validation (docs/03-contracts-and-schemas.md §1).

Rules enforced here:

* unknown keys are errors, with a "did you mean" suggestion, never silent ignores;
* no absolute paths and no `..` escapes in configuration values;
* the declared palette colour count must match the palette file, so a palette that drifted
  is caught before it silently changes every asset in a pack.
"""

from __future__ import annotations

import difflib
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .canonical import sha256_tagged
from .errors import ConfigError
from .model import LoraRef, PaletteRef, SeedPolicy, StyleContract
from .paths import relative_path

CONFIG_NAME = "sdga.toml"

_TOP_KEYS = {"schema", "project", "style", "backend", "pack", "gates"}
_PROJECT_KEYS = {
    "name",
    "root",
    "asset_globs",
    "recipes_dir",
    "runs_dir",
    "packs_dir",
    "cache_dir",
}
_STYLE_KEYS = {
    "name",
    "trigger_token",
    "grid",
    "generation_size",
    "palette",
    "palette_colors",
    "checkpoint",
    "seed_policy",
    "positive_anchors",
    "negative_anchors",
    "loras",
}
_LORA_KEYS = {"name", "strength_model", "strength_clip"}
_BACKEND_KEYS = {
    "kind",
    "url",
    "ws_url",
    "timeout_s",
    "poll_interval_s",
    "max_concurrency",
    "retry",
}
_RETRY_KEYS = {"attempts", "backoff_s"}
_PACK_KEYS = {"id_template", "require_review", "include_raw"}
_GATES_KEYS = {"on_fail", "thresholds"}

_GPL_LINE = re.compile(r"^\s*(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\b")


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    root: Path
    asset_globs: tuple[str, ...]
    recipes_dir: str
    runs_dir: str
    packs_dir: str
    cache_dir: str


@dataclass(frozen=True)
class BackendConfig:
    kind: str
    url: str
    ws_url: str
    timeout_s: float
    poll_interval_s: float
    max_concurrency: int
    retry_attempts: int
    retry_backoff_s: float


@dataclass(frozen=True)
class PackConfig:
    id_template: str
    require_review: bool
    include_raw: bool


@dataclass(frozen=True)
class GatesConfig:
    on_fail: str
    thresholds: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    path: Path
    project: ProjectConfig
    style: StyleContract
    backend: BackendConfig
    pack: PackConfig
    gates: GatesConfig

    @property
    def root(self) -> Path:
        return self.project.root

    def plan_path(self) -> Path:
        return self.root / "plan.json"

    def asset_paths(self) -> list[Path]:
        found: dict[Path, None] = {}
        for pattern in self.project.asset_globs:
            for path in sorted(self.root.glob(pattern)):
                if path.is_file():
                    found[path] = None
        return sorted(found, key=lambda p: p.as_posix())


# --------------------------------------------------------------------------- helpers


def _keys(table: Mapping[str, Any], allowed: set[str], where: str) -> None:
    for key in table:
        if key not in allowed:
            near = difflib.get_close_matches(str(key), sorted(allowed), n=1)
            hint = f" (did you mean {near[0]!r}?)" if near else ""
            raise ConfigError(
                f"unknown key {key!r}{hint}",
                location=where,
                remedy=f"allowed keys: {', '.join(sorted(allowed))}",
            )


def _table(
    raw: Mapping[str, Any], key: str, where: str, *, required: bool = True
) -> dict[str, Any]:
    if key not in raw:
        if required:
            raise ConfigError(f"missing required table [{key}]", location=where)
        return {}
    value = raw[key]
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table", location=where)
    return value


def _str(
    table: Mapping[str, Any],
    key: str,
    where: str,
    *,
    default: str | None = None,
    required: bool = False,
) -> str:
    if key not in table:
        if required:
            raise ConfigError(f"missing required key {key!r}", location=where)
        return default or ""
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string", location=where)
    return value.strip()


def _int(
    table: Mapping[str, Any],
    key: str,
    where: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    required: bool = False,
) -> int:
    if key not in table:
        if required:
            raise ConfigError(f"missing required key {key!r}", location=where)
        return int(default or 0)
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer", location=where)
    if minimum is not None and value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}", location=where)
    return value


def _num(table: Mapping[str, Any], key: str, where: str, *, default: float = 0.0) -> float:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number", location=where)
    return float(value)


def _bool(table: Mapping[str, Any], key: str, where: str, *, default: bool = False) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false", location=where)
    return value


def _relative(value: str, where: str, key: str) -> str:
    """Project-relative only. Rule 3: no machine-specific paths, ever."""
    return relative_path(value, where, key)


def _string_list(table: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    if key not in table:
        return ()
    value = table[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings", location=where)
    return tuple(item.strip() for item in value if item.strip())


def read_palette(path: Path, where: str) -> tuple[tuple[int, int, int], ...]:
    """Read a palette: a GIMP `.gpl`, or a `.png` whose distinct colours are the entries."""
    suffix = path.suffix.lower()
    if suffix == ".gpl":
        return _read_gpl(path, where)
    if suffix == ".png":
        return _read_png(path, where)
    raise ConfigError(
        f"unsupported palette format {suffix!r}",
        location=where,
        remedy="use a GIMP .gpl file, or a .png whose distinct colours are the palette",
    )


def _read_gpl(path: Path, where: str) -> tuple[tuple[int, int, int], ...]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ConfigError(f"cannot read palette {path.name}: {exc}", location=where) from None
    colors: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        match = _GPL_LINE.match(line)
        if not match:
            continue
        rgb = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if any(channel > 255 for channel in rgb):
            raise ConfigError(
                f"colour component out of range in palette: {line.strip()!r}", location=where
            )
        colors.append(rgb)
    if not colors:
        raise ConfigError(
            f"no colours found in {path.name}",
            location=where,
            remedy="a .gpl file lists 'R G B' triples, one per line",
        )
    return tuple(colors)


def _read_png(path: Path, where: str) -> tuple[tuple[int, int, int], ...]:
    """Every distinct opaque colour, in scan order: a Lospec palette image works as-is."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            raw = image.convert("RGBA").tobytes()
    except (OSError, UnidentifiedImageError) as exc:
        raise ConfigError(f"cannot read palette {path.name}: {exc}", location=where) from None

    colors: dict[tuple[int, int, int], None] = {}
    for offset in range(0, len(raw), 4):
        if raw[offset + 3]:
            colors[(raw[offset], raw[offset + 1], raw[offset + 2])] = None
    if not colors:
        raise ConfigError(
            f"no colours found in {path.name}",
            location=where,
            remedy="a .png palette has one opaque pixel per colour",
        )
    if len(colors) > 256:
        raise ConfigError(
            f"{path.name} defines {len(colors)} distinct colours",
            location=where,
            remedy="a pixel-art palette holds at most 256 colours; crop the image",
        )
    return tuple(colors)


# --------------------------------------------------------------------------- loading


def find_config(project: str | Path) -> Path:
    candidate = Path(project)
    if candidate.is_file():
        return candidate
    config_path = candidate / CONFIG_NAME
    if not config_path.is_file():
        raise ConfigError(
            f"no {CONFIG_NAME} in {candidate}",
            remedy=f"pass --project <dir> pointing at a project, or create {CONFIG_NAME}",
        )
    return config_path


def load_config(project: str | Path) -> Config:
    path = find_config(project)
    where = path.name
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read configuration: {exc}", location=str(path)) from None

    _keys(raw, _TOP_KEYS, where)
    schema = _int(raw, "schema", where, default=1)
    if schema != 1:
        raise ConfigError(
            f"unsupported schema {schema}",
            location=where,
            remedy="this build reads schema 1 only",
        )

    project_table = _table(raw, "project", where)
    _keys(project_table, _PROJECT_KEYS, f"{where} [project]")
    name = _str(project_table, "name", f"{where} [project]", required=True)
    root_rel = _relative(
        _str(project_table, "root", f"{where} [project]", default="."), f"{where} [project]", "root"
    )
    root = (path.parent / root_rel).resolve()

    globs = _string_list(project_table, "asset_globs", f"{where} [project]") or (
        "assets/**/*.yaml",
    )
    for pattern in globs:
        _relative(pattern, f"{where} [project]", "asset_globs")

    project_cfg = ProjectConfig(
        name=name,
        root=root,
        asset_globs=tuple(globs),
        recipes_dir=_relative(
            _str(project_table, "recipes_dir", where, default="recipes"), where, "recipes_dir"
        ),
        runs_dir=_relative(
            _str(project_table, "runs_dir", where, default="runs"), where, "runs_dir"
        ),
        packs_dir=_relative(
            _str(project_table, "packs_dir", where, default="packs"), where, "packs_dir"
        ),
        cache_dir=_relative(
            _str(project_table, "cache_dir", where, default=".sdga/cache"), where, "cache_dir"
        ),
    )

    style_table = _table(raw, "style", where)
    style_where = f"{where} [style]"
    _keys(style_table, _STYLE_KEYS, style_where)

    palette_rel = _relative(
        _str(style_table, "palette", style_where, required=True), style_where, "palette"
    )
    palette_file = project_cfg.root / palette_rel
    colors = read_palette(palette_file, style_where)
    declared_colors = _int(style_table, "palette_colors", style_where, default=len(colors))
    if declared_colors != len(colors):
        raise ConfigError(
            f"palette_colors is {declared_colors} but {palette_rel} defines {len(colors)} colours",
            location=style_where,
            remedy="fix the count, or replace the palette file",
        )

    generation_size = style_table.get("generation_size", [512, 512])
    if (
        not isinstance(generation_size, list)
        or len(generation_size) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in generation_size)
    ):
        raise ConfigError(
            "generation_size must be two positive integers, e.g. [512, 512]", location=style_where
        )

    try:
        seed_policy = SeedPolicy.parse(style_table.get("seed_policy", "derived"))
    except ValueError as exc:
        raise ConfigError(str(exc), location=style_where) from None

    loras_raw = style_table.get("loras", [])
    if not isinstance(loras_raw, list):
        raise ConfigError("loras must be an array of tables", location=style_where)
    loras: list[LoraRef] = []
    for index, entry in enumerate(loras_raw):
        item_where = f"{style_where} [[style.loras]] #{index + 1}"
        if not isinstance(entry, dict):
            raise ConfigError("each lora must be a table", location=item_where)
        _keys(entry, _LORA_KEYS, item_where)
        loras.append(
            LoraRef(
                name=_str(entry, "name", item_where, required=True),
                strength_model=_num(entry, "strength_model", item_where, default=1.0),
                strength_clip=_num(entry, "strength_clip", item_where, default=1.0),
            )
        )

    style = StyleContract(
        name=_str(style_table, "name", style_where, default=name),
        trigger_token=_str(style_table, "trigger_token", style_where, default=""),
        grid=_int(style_table, "grid", style_where, default=32, minimum=1),
        generation_size=(int(generation_size[0]), int(generation_size[1])),
        palette=PaletteRef(
            path=palette_rel,
            colors=len(colors),
            sha256=sha256_tagged(palette_file.read_bytes()),
        ),
        checkpoint=_str(style_table, "checkpoint", style_where, required=True),
        loras=tuple(loras),
        positive_anchors=_string_list(style_table, "positive_anchors", style_where),
        negative_anchors=_string_list(style_table, "negative_anchors", style_where),
        seed_policy=seed_policy,
    )

    backend_table = _table(raw, "backend", where)
    backend_where = f"{where} [backend]"
    _keys(backend_table, _BACKEND_KEYS, backend_where)
    kind = _str(backend_table, "kind", backend_where, default="comfyui")
    if kind not in {"comfyui", "fake"}:
        raise ConfigError(
            f"unknown backend kind {kind!r}",
            location=backend_where,
            remedy="known kinds: comfyui, fake",
        )
    url = _str(backend_table, "url", backend_where, default="http://127.0.0.1:8188")
    retry_table = _table(backend_table, "retry", backend_where, required=False)
    _keys(retry_table, _RETRY_KEYS, f"{backend_where} retry")
    backend_cfg = BackendConfig(
        kind=kind,
        url=url,
        ws_url=_str(backend_table, "ws_url", backend_where, default="ws://127.0.0.1:8188/ws"),
        timeout_s=_num(backend_table, "timeout_s", backend_where, default=900.0),
        poll_interval_s=_num(backend_table, "poll_interval_s", backend_where, default=0.5),
        max_concurrency=_int(backend_table, "max_concurrency", backend_where, default=1, minimum=1),
        retry_attempts=_int(retry_table, "attempts", backend_where, default=2, minimum=0),
        retry_backoff_s=_num(retry_table, "backoff_s", backend_where, default=5.0),
    )

    pack_table = _table(raw, "pack", where, required=False)
    pack_where = f"{where} [pack]"
    _keys(pack_table, _PACK_KEYS, pack_where)
    pack_cfg = PackConfig(
        id_template=_str(pack_table, "id_template", pack_where, default="{project}-{date}-{seq}"),
        require_review=_bool(pack_table, "require_review", pack_where, default=True),
        include_raw=_bool(pack_table, "include_raw", pack_where, default=False),
    )

    gates_table = _table(raw, "gates", where, required=False)
    gates_where = f"{where} [gates]"
    _keys(gates_table, _GATES_KEYS, gates_where)
    thresholds = _table(gates_table, "thresholds", gates_where, required=False)
    on_fail = _str(gates_table, "on_fail", gates_where, default="reject")
    if on_fail not in {"reject", "warn"}:
        raise ConfigError(
            f"on_fail must be 'reject' or 'warn', got {on_fail!r}", location=gates_where
        )
    gates_cfg = GatesConfig(on_fail=on_fail, thresholds=dict(thresholds))

    return Config(
        path=path,
        project=project_cfg,
        style=style,
        backend=backend_cfg,
        pack=pack_cfg,
        gates=gates_cfg,
    )


__all__: Sequence[str] = [
    "BackendConfig",
    "Config",
    "GatesConfig",
    "PackConfig",
    "ProjectConfig",
    "find_config",
    "load_config",
    "read_palette",
]
