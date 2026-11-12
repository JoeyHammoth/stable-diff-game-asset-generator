"""Pack publishing (docs/03-contracts-and-schemas.md §6, docs/04 §7).

A pack is the only thing an engine consumes, and it is immutable: republishing produces a
new `pack_id` rather than mutating an old directory. Every file in it carries provenance
back to a `run.json` job, which is what makes a bad batch a one-line revert instead of an
archaeology project.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..canonical import hash_file
from ..config import Config
from ..errors import SdgaError
from ..model import SCHEMA


@dataclass(frozen=True)
class PackResult:
    pack_id: str
    path: Path
    asset_ids: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_run(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run.json"
    if not path.is_file():
        raise SdgaError(
            f"no run.json in {run_dir}",
            remedy="pass --run <run_id>, or run `sdga run` first",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _packs_dir(config: Config) -> Path:
    return config.root / config.project.packs_dir


def next_pack_id(config: Config, *, today: str | None = None) -> str:
    """`{project}-{date}-{seq}`, with the sequence chosen past anything already on disk."""
    date = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    template = config.pack.id_template
    directory = _packs_dir(config)
    directory.mkdir(parents=True, exist_ok=True)

    sequence = 1
    while True:
        candidate = template.format(
            project=config.project.name, date=date, seq=f"{sequence:02d}"
        )
        if not (directory / candidate).exists():
            return candidate
        sequence += 1


def _engine_hints(asset: Mapping[str, Any], checks: Sequence[Mapping[str, Any]]) -> dict:
    """Advisory facts an engine needs, derived from the gates rather than guessed."""
    hints: dict[str, Any] = {}
    files = asset.get("files") or []
    if not files:
        return hints
    width = files[0].get("width")
    height = files[0].get("height")
    seamless = any(
        check.get("gate") == "seamless_tile" and check.get("status") == "pass"
        for check in checks
    )
    if asset.get("kind") == "terrain_tile" and width and height:
        hints["tile"] = {"size": [width, height], "seamless": seamless}
    return hints


def publish(
    config: Config, run_dir: Path, *, allow_unreviewed: bool = False
) -> PackResult:
    run = _read_run(run_dir)
    accepted = [job for job in run.get("jobs", []) if job.get("status") == "accepted"]
    if not accepted:
        raise SdgaError(
            f"run {run.get('run_id')} has no accepted jobs",
            remedy="fix the failing assets, then run again",
        )

    if config.pack.require_review and not allow_unreviewed:
        unapproved = [
            job for job in accepted if (job.get("review") or {}).get("status") != "approved"
        ]
        if unapproved:
            raise SdgaError(
                f"{len(unapproved)} accepted asset(s) have no review decision",
                remedy=(
                    "the review command arrives in phase P3; until then publish with "
                    "--allow-unreviewed, which records the override in pack.json"
                ),
            )

    pack_id = next_pack_id(config)
    pack_dir = _packs_dir(config) / pack_id
    pack_dir.mkdir(parents=True, exist_ok=False)

    assets: list[dict[str, Any]] = []
    for job in sorted(accepted, key=lambda entry: entry["asset_id"]):
        asset_id = job["asset_id"]
        post = (job.get("post") or [None])[0]
        if not post:
            raise SdgaError(
                f"{asset_id}: accepted job has no postprocessed file",
                remedy="re-run the asset; the run directory is incomplete",
            )
        source = config.root / post["path"]
        if not source.is_file():
            raise SdgaError(
                f"{asset_id}: missing artifact {post['path']}",
                remedy="the run directory has been modified; re-run the asset",
            )
        target_rel = f"assets/{asset_id}.png"
        target = pack_dir / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

        checks = job.get("gates", [])
        files = [
            {
                "path": target_rel,
                "role": "albedo",
                "sha256": hash_file(target),
                "width": post.get("width"),
                "height": post.get("height"),
                "format": "png",
                "bytes": target.stat().st_size,
            }
        ]
        engine = _engine_hints({"kind": job.get("kind"), "files": files}, checks)
        entry: dict[str, Any] = {
            "id": asset_id,
            "kind": job.get("kind"),
            "files": files,
            "checks": checks,
            "provenance": {
                "run_id": run.get("run_id"),
                "request_hash": job.get("request_hash"),
                "seed": job.get("seed"),
                "recipe": job.get("recipe"),
                "created": run.get("finished"),
            },
        }
        if engine:
            entry["engine"] = engine
        assets.append(entry)

    style = run.get("style", {})
    manifest = {
        "schema": SCHEMA,
        "pack_id": pack_id,
        "created": _utc_now(),
        "style": {
            "name": style.get("name"),
            "contract_hash": style.get("contract_hash"),
            "grid": style.get("grid"),
            "palette": style.get("palette"),
        },
        "generator": {
            "tool": run.get("tool", {}).get("name"),
            "version": run.get("tool", {}).get("version"),
            "backend": run.get("profile", {}).get("kind"),
            "profile_hash": run.get("profile", {}).get("profile_hash"),
        },
        "assets": assets,
    }
    if config.pack.require_review and allow_unreviewed:
        manifest["review_override"] = "published without review (see docs/06 phase P3)"
    (pack_dir / "pack.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    _write_manifest(pack_dir)
    _write_licenses(pack_dir, config, run)
    return PackResult(pack_id=pack_id, path=pack_dir, asset_ids=tuple(a["id"] for a in assets))


def _write_manifest(pack_dir: Path) -> None:
    lines = []
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.sha256":
            continue
        digest = hash_file(path).split(":", 1)[1]
        lines.append(f"{digest}  {path.relative_to(pack_dir).as_posix()}")
    (pack_dir / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_licenses(pack_dir: Path, config: Config, run: Mapping[str, Any]) -> None:
    style = config.style
    palette = style.palette
    lines = [
        "# Licences and provenance",
        "",
        f"Pack produced by sdga {run.get('tool', {}).get('version')} "
        f"from run {run.get('run_id')}.",
        "",
        "## Palette",
        f"- `{palette.path}` ({palette.colors} colours, {palette.sha256})",
        "- Record the palette's own licence before distributing this pack.",
        "",
        "## Models",
        f"- checkpoint: `{style.checkpoint}`",
    ]
    lines.extend(f"- lora: `{lora.name}` ({lora.strength_model:g})" for lora in style.loras)
    lines.extend(
        [
            "",
            "Model weights are not distributed with this pack, and their licences are not",
            "granted by it. Check each model's terms before shipping.",
            "",
            "## Generated content",
        ]
    )
    lines.extend(
        f"- `assets/{asset['id']}.png` (seed {asset['provenance']['seed']})"
        for asset in run.get("pack_assets", [])  # unused; kept for future overrides
    )
    lines.append("- Every file above was generated by the run named at the top of this file.")
    (pack_dir / "LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


__all__ = ["PackResult", "next_pack_id", "publish"]
