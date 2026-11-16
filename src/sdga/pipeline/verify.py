"""Standalone validation: re-run gates over files already on disk, with no backend.

This is what lets CI prove a pack is still correct after a tool upgrade, and what makes
`pack.json` claims checkable rather than trusted. Audio is verified by ear only when a human
listens; here the same four audio gates the run applied are measured again from the WAV.

For a pack there is no `run.json` next to the file, so the parameters are recomputed from the
spec. That is deliberate: a pack whose spec has since changed must fail validation, not pass
on a stale recorded plan.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from ..audio import evaluate_audio, read_wav
from ..backends.comfyui.recipe import RecipeRegistry
from ..config import Config
from ..errors import SdgaError
from ..model import AssetKind
from ..planning.plan import audio_params
from ..specs import load_specs
from ..validate import evaluate, severity
from .run import audio_gate_context, gate_context, gate_names, palette_for

AUDIO_KINDS = frozenset({AssetKind.SFX, AssetKind.MUSIC_TRACK})


def _audio_rows(
    config: Config,
    spec: Any,
    asset_id: str,
    path: Path,
    params: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    try:
        audio = read_wav(path)
    except (OSError, ValueError) as exc:
        return [
            {
                "asset_id": asset_id,
                "gate": "audio",
                "status": "fail",
                "value": None,
                "detail": str(exc),
            }
        ]
    resolved = params or audio_params(config, spec)
    results = evaluate_audio(
        gate_names(None, spec), audio, audio_gate_context(config, spec, resolved)
    )
    return [{"asset_id": asset_id, **result.to_dict()} for result in results]


def _rows_for(
    config: Config,
    specs: Mapping[str, Any],
    recipes: RecipeRegistry,
    asset_id: str,
    path: Path,
    palette: tuple[tuple[int, int, int], ...],
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    spec = specs.get(asset_id)
    if spec is None:
        return [
            {
                "asset_id": asset_id,
                "gate": "spec",
                "status": "fail",
                "value": None,
                "detail": "no spec declares this asset id any more",
            }
        ]
    if not path.is_file():
        return [
            {
                "asset_id": asset_id,
                "gate": "file",
                "status": "fail",
                "value": None,
                "detail": f"missing {path.as_posix()}",
            }
        ]

    if spec.kind in AUDIO_KINDS:
        return _audio_rows(config, spec, asset_id, path, params)

    with Image.open(path) as opened:
        image = opened.convert("RGBA")

    results = evaluate(
        gate_names(recipes.for_kind(spec.kind), spec),
        image,
        gate_context(config, spec, palette),
    )
    return [{"asset_id": asset_id, **result.to_dict()} for result in results]


def _has_error(config: Config, specs: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    for row in rows:
        if row.get("status") != "fail":
            continue
        spec = specs.get(row["asset_id"])
        overrides = spec.gates if spec is not None else {}
        if severity(str(row.get("gate")), overrides) == "error":
            return True
    return False


def verify_pack(
    config: Config, pack_dir: Path, recipes: RecipeRegistry
) -> tuple[bool, list[dict[str, Any]]]:
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise SdgaError(f"no pack.json in {pack_dir}", remedy="point validate at a pack directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs = {spec.id: spec for spec in load_specs(config)}
    palette = palette_for(config)

    rows: list[dict[str, Any]] = []
    for asset in manifest.get("assets", []):
        files = asset.get("files") or []
        path = pack_dir / files[0]["path"] if files else pack_dir / "missing"
        rows.extend(_rows_for(config, specs, recipes, asset["id"], path, palette))
    return not _has_error(config, specs, rows), rows


def verify_run(
    config: Config, run_dir: Path, recipes: RecipeRegistry
) -> tuple[bool, list[dict[str, Any]]]:
    record_path = run_dir / "run.json"
    if not record_path.is_file():
        raise SdgaError(f"no run.json in {run_dir}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    specs = {spec.id: spec for spec in load_specs(config)}
    palette = palette_for(config)

    rows: list[dict[str, Any]] = []
    for job in record.get("jobs", []):
        post = (job.get("post") or [{}])[0]
        path = config.root / post["path"] if post.get("path") else run_dir / "missing"
        rows.extend(
            _rows_for(
                config,
                specs,
                recipes,
                job["asset_id"],
                path,
                palette,
                params=job.get("params") or None,
            )
        )
    return not _has_error(config, specs, rows), rows


__all__ = ["verify_pack", "verify_run"]
