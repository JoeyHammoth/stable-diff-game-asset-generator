"""Godot adapter: a pack, translated into engine data (docs/04 §8).

Godot is a consumer, not a dependency. This module reads `pack.json`, writes JSON, and never
invokes the engine, so it runs in the same GPU-less CI job as the rest of the pipeline.

Four artifacts, all schema-tagged and deterministic:

* `godot_import.json` — per-file import settings (`filter`, `mipmaps`, compression, WAV loops).
* `ninepatch.json` — `NinePatchRect` margins. The pack stores margins as `[horizontal, vertical]`
  (the uniform border found by the gate); Godot wants four edges, so each pair is applied to
  both sides.
* `sprite_frames.json` — an `AnimatedSprite2D` `SpriteFrames` descriptor: frame size, grid and
  the frame list. The animation clock is an adapter option (`--fps`, default 8), because the pack
  deliberately carries layout but not playback speed.
* `audio_buses.json` — the bus each track belongs to, plus loop points in seconds and frames.

A malformed advisory hint is an error with a remedy, never a guessed default that would ship a
broken import.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from ..canonical import pretty_json, sha256_tagged
from ..config import Config
from ..errors import SdgaError, UsageError
from ..model import SCHEMA

ENGINE = "godot"
DEFAULT_FPS = 8
PIXEL_KINDS = frozenset({"terrain_tile", "sprite_sheet", "ui_element", "icon", "normal_map"})
AUDIO_KINDS = frozenset({"music_track", "sfx"})
ARTIFACTS = (
    "audio_buses.json",
    "godot_import.json",
    "manifest.json",
    "ninepatch.json",
    "sprite_frames.json",
)


@dataclass(frozen=True)
class AdaptResult:
    engine: str
    pack_id: str
    path: Path
    files: tuple[str, ...]


def _fail(detail: str) -> NoReturn:
    raise SdgaError(
        f"Godot adapter: {detail}",
        remedy="re-publish the pack; its engine hints are advisory but must be well formed",
    )


def read_pack(pack_dir: Path) -> dict[str, Any]:
    """Load and structurally check `pack.json`. Deeper checks happen per artifact."""
    path = Path(pack_dir) / "pack.json"
    if not path.is_file():
        raise SdgaError(
            f"no pack.json in {pack_dir}",
            remedy="pass --pack <pack directory>, or run `sdga publish` first",
        )
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SdgaError(
            f"cannot read {path}: {exc}", remedy="re-publish the pack"
        ) from None
    if not isinstance(parsed, dict):
        _fail(f"{path} is not a JSON object")
    document: dict[str, Any] = parsed
    if document.get("schema") != SCHEMA:
        _fail(f"{path} has schema {parsed.get('schema')!r}, expected {SCHEMA}")
    if not isinstance(document.get("pack_id"), str):
        _fail(f"{path} has no pack_id")
    assets = document.get("assets")
    if not isinstance(assets, list):
        _fail(f"{path} has no assets list")
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), str):
            _fail(f"{path} contains an asset without an id")
        if not isinstance(asset.get("kind"), str):
            _fail(f"{path}: asset {asset.get('id')!r} has no kind")
        files = asset.get("files")
        if not isinstance(files, list) or not files:
            _fail(f"{path}: asset {asset.get('id')!r} has no files")
        for entry in files:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                _fail(f"{path}: asset {asset.get('id')!r} has a file without a path")
    return document


def _engine(asset: Mapping[str, Any]) -> Mapping[str, Any]:
    engine = asset.get("engine")
    return engine if isinstance(engine, dict) else {}


def _first_path(asset: Mapping[str, Any]) -> str:
    files = asset["files"]
    entry = files[0]
    return str(entry["path"])


def _bus(asset: Mapping[str, Any]) -> str:
    audio = _engine(asset).get("audio")
    if isinstance(audio, dict) and isinstance(audio.get("bus"), str):
        return str(audio["bus"])
    if asset["kind"] == "music_track":
        return "Music"
    if asset["kind"] == "sfx":
        return "SFX"
    _fail(f"asset {asset['id']!r} is audio but declares no bus")


def _positive_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{what} must be a positive integer, got {value!r}")
    return int(value)


def _loop(asset: Mapping[str, Any]) -> Mapping[str, Any]:
    loop = _engine(asset).get("music")
    if not isinstance(loop, dict):
        return {}
    inner = loop.get("loop")
    return inner if isinstance(inner, dict) else {}


def build_godot_bundle(pack: Mapping[str, Any], *, fps: int = DEFAULT_FPS) -> dict[str, dict[str, Any]]:
    """Pure pack -> documents. No filesystem access beyond the parsed manifest."""
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise UsageError(f"--fps must be a positive integer, got {fps!r}")
    return {
        "godot_import.json": _import_hints(pack),
        "ninepatch.json": _ninepatch(pack),
        "sprite_frames.json": _sprite_frames(pack, fps),
        "audio_buses.json": _audio_buses(pack),
    }


def _import_hints(pack: Mapping[str, Any]) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for asset in pack["assets"]:
        kind = str(asset["kind"])
        for entry in asset["files"]:
            path = str(entry["path"])
            if path.endswith(".png"):
                files[path] = {
                    "importer": "texture",
                    "filter": False,
                    "mipmaps": False,
                    "compression": "lossless" if kind in PIXEL_KINDS else "vram_compressed",
                }
            elif path.endswith(".wav"):
                hint: dict[str, Any] = {
                    "importer": "wav",
                    "loop_mode": 1 if kind == "music_track" else 0,
                }
                loop = _loop(asset)
                if loop:
                    begin = float(loop.get("start_s", 0.0))
                    end = float(loop["end_s"])
                    if begin < 0 or end <= begin:
                        _fail(f"{asset['id']}: loop points {begin}..{end} are not increasing")
                    hint["loop_begin_s"] = round(begin, 6)
                    hint["loop_end_s"] = round(end, 6)
                    rate = entry.get("sample_rate") or (
                        _engine(asset).get("audio") or {}
                    ).get("sample_rate")
                    if isinstance(rate, int) and rate > 0:
                        # Godot's WAV importer stores loop points in frames.
                        hint["loop_begin_frame"] = int(round(begin * rate))
                        hint["loop_end_frame"] = int(round(end * rate))
                files[path] = hint
            else:
                _fail(f"{asset['id']}: no Godot importer for {path}")
    return {"schema": SCHEMA, "engine": ENGINE, "pack_id": pack["pack_id"], "files": files}


def _ninepatch(pack: Mapping[str, Any]) -> dict[str, Any]:
    assets: dict[str, dict[str, Any]] = {}
    for asset in pack["assets"]:
        ui = _engine(asset).get("ui")
        if not isinstance(ui, dict) or "margins" not in ui:
            continue
        margins = ui["margins"]
        if (
            not isinstance(margins, Sequence)
            or isinstance(margins, str)
            or len(margins) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in margins)
        ):
            _fail(f"{asset['id']}: ui.margins must be [horizontal, vertical], got {margins!r}")
        horizontal, vertical = int(margins[0]), int(margins[1])
        assets[str(asset["id"])] = {
            "path": _first_path(asset),
            "margins": {
                "left": horizontal,
                "top": vertical,
                "right": horizontal,
                "bottom": vertical,
            },
        }
    return {"schema": SCHEMA, "engine": ENGINE, "pack_id": pack["pack_id"], "assets": assets}


def _sprite_frames(pack: Mapping[str, Any], fps: int) -> dict[str, Any]:
    sprites: dict[str, dict[str, Any]] = {}
    for asset in pack["assets"]:
        if asset["kind"] != "sprite_sheet":
            continue
        sprite = _engine(asset).get("sprite")
        if not isinstance(sprite, dict):
            # Not every sprite sheet is animated; only one with a published hint gets a
            # SpriteFrames resource.
            continue
        frame_size = sprite.get("frame_size")
        if (
            not isinstance(frame_size, Sequence)
            or isinstance(frame_size, str)
            or len(frame_size) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in frame_size
            )
        ):
            _fail(f"{asset['id']}: sprite.frame_size must be two positive integers")
        cols = _positive_int(sprite.get("cols"), f"{asset['id']}: sprite.cols")
        rows = _positive_int(sprite.get("rows"), f"{asset['id']}: sprite.rows")
        frames = _positive_int(sprite.get("frames"), f"{asset['id']}: sprite.frames")
        if cols * rows < frames:
            _fail(
                f"{asset['id']}: sprite grid {cols}x{rows} cannot hold {frames} frame(s)"
            )
        sprites[str(asset["id"])] = {
            "path": _first_path(asset),
            "frame_size": [int(frame_size[0]), int(frame_size[1])],
            "cols": cols,
            "rows": rows,
            "frames": frames,
            "animations": {
                "default": {
                    "frames": list(range(frames)),
                    "loop": True,
                    "speed": fps,
                }
            },
        }
    return {
        "schema": SCHEMA,
        "engine": ENGINE,
        "pack_id": pack["pack_id"],
        "fps": fps,
        "sprites": sprites,
    }


def _audio_buses(pack: Mapping[str, Any]) -> dict[str, Any]:
    assets: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for asset in pack["assets"]:
        kind = str(asset["kind"])
        if kind not in AUDIO_KINDS:
            continue
        bus = _bus(asset)
        used.add(bus)
        entry: dict[str, Any] = {"path": _first_path(asset), "bus": bus}
        loop = _loop(asset)
        if kind == "music_track" and loop:
            entry["loop"] = {
                "begin_s": round(float(loop.get("start_s", 0.0)), 6),
                "end_s": round(float(loop["end_s"]), 6),
            }
        if kind == "sfx":
            entry["one_shot"] = True
        assets[str(asset["id"])] = entry
    buses = [
        {"name": name, "volume_db": 0.0, "send": "Master"} for name in sorted(used)
    ]
    return {
        "schema": SCHEMA,
        "engine": ENGINE,
        "pack_id": pack["pack_id"],
        "buses": buses,
        "assets": assets,
    }


def _validate_bundle(bundle: Mapping[str, Mapping[str, Any]], pack_id: str) -> None:
    """Structural checks over the adapter's own output, before anything is written."""
    for name, document in bundle.items():
        if document.get("schema") != SCHEMA or document.get("engine") != ENGINE:
            _fail(f"{name} is missing its schema/engine tag")
        if document.get("pack_id") != pack_id:
            _fail(f"{name} belongs to {document.get('pack_id')!r}, not {pack_id!r}")

    for path, hint in bundle["godot_import.json"]["files"].items():
        if hint.get("importer") not in {"texture", "wav"}:
            _fail(f"import hint for {path} has no known importer")
        if hint["importer"] == "texture" and (
            hint.get("filter") is not False or hint.get("mipmaps") is not False
        ):
            _fail(f"import hint for {path} must disable filter and mipmaps")
    for asset_id, sprite in bundle["sprite_frames.json"]["sprites"].items():
        if len(sprite["frame_size"]) != 2 or sprite["cols"] * sprite["rows"] < sprite["frames"]:
            _fail(f"SpriteFrames for {asset_id} has an impossible grid")
        if sprite["animations"]["default"]["frames"] != list(range(sprite["frames"])):
            _fail(f"SpriteFrames for {asset_id} does not list every frame")
    for asset_id, ui in bundle["ninepatch.json"]["assets"].items():
        if set(ui["margins"]) != {"left", "top", "right", "bottom"}:
            _fail(f"ninepatch margins for {asset_id} are incomplete")
    for asset_id, audio in bundle["audio_buses.json"]["assets"].items():
        if not audio.get("bus"):
            _fail(f"audio asset {asset_id} has no bus")


def adapt_godot(pack_dir: Path, out_dir: Path, *, fps: int = DEFAULT_FPS) -> AdaptResult:
    """Read a pack, build and validate the documents, then write them deterministically."""
    pack = read_pack(Path(pack_dir))
    bundle = build_godot_bundle(pack, fps=fps)
    _validate_bundle(bundle, str(pack["pack_id"]))

    texts = {name: pretty_json(document) for name, document in bundle.items()}
    hashes = {
        name: sha256_tagged(text.encode("utf-8")) for name, text in sorted(texts.items())
    }
    texts["manifest.json"] = pretty_json(
        {
            "schema": SCHEMA,
            "engine": ENGINE,
            "pack_id": pack["pack_id"],
            "fps": fps,
            "files": hashes,
        }
    )

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name in sorted(texts):
        with (target / name).open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(texts[name])
    return AdaptResult(
        engine=ENGINE,
        pack_id=str(pack["pack_id"]),
        path=target,
        files=tuple(sorted(texts)),
    )


def resolve_pack(config: Config, pack: str | Path | None) -> Path:
    """`--pack` if given, else the newest published pack."""
    if pack is None:
        directory = config.root / config.project.packs_dir
        candidates = (
            sorted(
                (path for path in directory.glob("*") if (path / "pack.json").is_file()),
                key=lambda path: path.name,
            )
            if directory.is_dir()
            else []
        )
        if not candidates:
            raise SdgaError(
                "no published packs yet",
                remedy="run `sdga publish`, or pass --pack <pack directory>",
            )
        return candidates[-1]

    path = Path(pack)
    if not path.is_absolute() and not (path / "pack.json").is_file():
        path = config.root / path
    if not (path / "pack.json").is_file():
        raise SdgaError(
            f"no pack.json in {pack}",
            remedy="pass the directory `sdga publish` wrote, e.g. packs/mygame-2026-11-16-01",
        )
    return path


def adapt(
    config: Config,
    *,
    pack: str | Path | None = None,
    out: str | Path | None = None,
    engine: str = ENGINE,
    fps: int = DEFAULT_FPS,
) -> AdaptResult:
    if engine != ENGINE:
        raise UsageError(f"unknown engine {engine!r}", remedy="known engines: godot")
    pack_dir = resolve_pack(config, pack)
    manifest = read_pack(pack_dir)
    target = (
        Path(out)
        if out is not None
        else config.root / "adapters" / str(manifest["pack_id"]) / ENGINE
    )
    return adapt_godot(pack_dir, target, fps=fps)


__all__ = [
    "ARTIFACTS",
    "DEFAULT_FPS",
    "ENGINE",
    "AdaptResult",
    "adapt",
    "adapt_godot",
    "build_godot_bundle",
    "read_pack",
    "resolve_pack",
]
