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
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from ..audio import evaluate_audio, read_wav
from ..backends.comfyui.recipe import RecipeRegistry
from ..canonical import hash_file
from ..config import Config
from ..errors import SdgaError
from ..model import AssetKind
from ..planning.plan import audio_params
from ..specs import load_specs
from ..validate import evaluate, severity
from .run import audio_gate_context, gate_context, gate_names, palette_for

AUDIO_KINDS = frozenset({AssetKind.SFX, AssetKind.MUSIC_TRACK})
INTEGRITY_GATES = frozenset({"manifest", "asset_file", "provenance", "artifact"})


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
        # Integrity is never downgradeable by a spec: a pack whose bytes do not match
        # its manifest is broken regardless of what the asset's gate policy says.
        if row.get("gate") in INTEGRITY_GATES:
            return True
        spec = specs.get(row["asset_id"])
        overrides = spec.gates if spec is not None else {}
        if severity(str(row.get("gate")), overrides) == "error":
            return True
    return False


def _integrity(asset_id: str, gate: str, detail: str, value: Any = None) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "gate": gate,
        "status": "fail",
        "value": value,
        "detail": detail,
    }


def _safe_member(pack_dir: Path, relative: object) -> Path | None:
    """Resolve a pack-relative path, rejecting absolute paths, `..`, and backslashes."""
    if not isinstance(relative, str) or not relative.strip() or "\\" in relative:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return pack_dir / pure


def _manifest_rows(pack_dir: Path) -> list[dict[str, Any]]:
    """Verify `MANIFEST.sha256` against every file in the pack.

    The manifest is the pack's own integrity claim. Checking only the gates would let a
    byte-level edit that still satisfies the palette and dimensions ship unnoticed.
    """
    manifest_path = pack_dir / "MANIFEST.sha256"
    if not manifest_path.is_file():
        return [_integrity("pack", "manifest", "missing MANIFEST.sha256")]
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [_integrity("pack", "manifest", f"cannot read MANIFEST.sha256: {exc}")]

    rows: list[dict[str, Any]] = []
    entries: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        digest, separator, relative = line.partition("  ")
        relative = relative.strip()
        if not separator or not relative:
            rows.append(_integrity("pack", "manifest", f"malformed line {number}: {line!r}"))
            continue
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            rows.append(_integrity("pack", "manifest", f"malformed sha256 on line {number}"))
            continue
        if relative in entries:
            rows.append(_integrity("pack", "manifest", f"duplicate entry: {relative}"))
            continue
        entries[relative] = digest

    if not entries:
        rows.append(_integrity("pack", "manifest", "MANIFEST.sha256 lists no files"))

    for relative, digest in sorted(entries.items()):
        target = _safe_member(pack_dir, relative)
        if target is None:
            rows.append(_integrity("pack", "manifest", f"unsafe path: {relative!r}"))
        elif not target.is_file():
            rows.append(_integrity("pack", "manifest", f"listed file is missing: {relative}"))
        elif hash_file(target) != "sha256:" + digest:
            rows.append(_integrity("pack", "manifest", f"sha256 mismatch: {relative}"))

    actual = {
        path.relative_to(pack_dir).as_posix()
        for path in pack_dir.rglob("*")
        if path.is_file() and path.resolve() != manifest_path.resolve()
    }
    for relative in sorted(actual - set(entries)):
        rows.append(_integrity("pack", "manifest", f"file is not listed: {relative}"))
    return rows


def _asset_rows(pack_dir: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify the per-file hashes/sizes and provenance that `pack.json` advertises."""
    rows: list[dict[str, Any]] = []
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        return [_integrity("pack", "manifest", "pack.json lists no assets")]

    for asset in assets:
        if not isinstance(asset, dict):
            rows.append(_integrity("pack", "manifest", "pack.json contains a non-object asset"))
            continue
        asset_id = str(asset.get("id") or "pack")
        provenance = asset.get("provenance")
        required = ("run_id", "request_hash", "seed", "recipe", "created")
        if not isinstance(provenance, dict) or any(key not in provenance for key in required):
            rows.append(_integrity(asset_id, "provenance", "missing provenance field(s)"))

        files = asset.get("files")
        if not isinstance(files, list) or not files:
            rows.append(_integrity(asset_id, "asset_file", "no files listed"))
            continue
        for entry in files:
            if not isinstance(entry, dict):
                rows.append(_integrity(asset_id, "asset_file", "non-object file entry"))
                continue
            relative = entry.get("path")
            target = _safe_member(pack_dir, relative)
            if target is None:
                rows.append(_integrity(asset_id, "asset_file", f"unsafe path: {relative!r}"))
                continue
            if not target.is_file():
                rows.append(_integrity(asset_id, "asset_file", f"missing file: {relative}"))
                continue
            if entry.get("sha256") != hash_file(target):
                rows.append(_integrity(asset_id, "asset_file", f"sha256 mismatch: {relative}"))
            if "bytes" in entry and entry.get("bytes") != target.stat().st_size:
                rows.append(_integrity(asset_id, "asset_file", f"byte count mismatch: {relative}"))
    return rows


def _artifact_rows(config: Config, record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify that a run's postprocessed artifacts are still the ones it recorded."""
    rows: list[dict[str, Any]] = []
    for job in record.get("jobs", []):
        if not isinstance(job, dict):
            continue
        asset_id = str(job.get("asset_id") or "pack")
        for post in job.get("post") or []:
            if not isinstance(post, dict) or not post.get("path"):
                rows.append(_integrity(asset_id, "artifact", "postprocess entry has no path"))
                continue
            target = config.root / str(post["path"])
            if not target.is_file():
                rows.append(_integrity(asset_id, "artifact", f"missing file: {post['path']}"))
            elif post.get("sha256") and hash_file(target) != post["sha256"]:
                rows.append(_integrity(asset_id, "artifact", f"sha256 mismatch: {post['path']}"))
    return rows


def verify_pack(
    config: Config, pack_dir: Path, recipes: RecipeRegistry
) -> tuple[bool, list[dict[str, Any]]]:
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise SdgaError(f"no pack.json in {pack_dir}", remedy="point validate at a pack directory")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SdgaError(
            f"cannot read {manifest_path}: {exc}", remedy="re-publish the pack"
        ) from None
    if not isinstance(manifest, dict):
        raise SdgaError(f"{manifest_path} is not a JSON object", remedy="re-publish the pack")
    specs = {spec.id: spec for spec in load_specs(config)}
    palette = palette_for(config)

    rows: list[dict[str, Any]] = _manifest_rows(pack_dir) + _asset_rows(pack_dir, manifest)
    assets = manifest.get("assets")
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict):
            continue
        files = asset.get("files") or []
        path = pack_dir / files[0]["path"] if files else pack_dir / "missing"
        rows.extend(_rows_for(config, specs, recipes, str(asset["id"]), path, palette))
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

    rows: list[dict[str, Any]] = _artifact_rows(config, record)
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
