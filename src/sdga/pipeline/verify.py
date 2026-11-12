"""Standalone validation: re-run gates over files already on disk, with no backend.

This is what lets CI prove a pack is still correct after a tool upgrade, and what makes
`pack.json` claims checkable rather than trusted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from ..backends.comfyui.recipe import RecipeRegistry
from ..config import Config
from ..errors import SdgaError
from ..specs import load_specs
from ..validate import evaluate, severity
from .run import gate_context, gate_names, palette_for


def _rows_for(
    config: Config,
    specs: Mapping[str, Any],
    recipes: RecipeRegistry,
    asset_id: str,
    path: Path,
    palette: tuple[tuple[int, int, int], ...],
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
        raise SdgaError(
            f"no pack.json in {pack_dir}", remedy="point validate at a pack directory"
        )
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
        rows.extend(_rows_for(config, specs, recipes, job["asset_id"], path, palette))
    return not _has_error(config, specs, rows), rows


__all__ = ["verify_pack", "verify_run"]
