"""Retention: prune old runs and packs without breaking provenance (docs/07 §6.2).

The audit trail is the reason this command is conservative. A run referenced by any
published pack is never deleted, even when it is older than ``--keep-runs``: its raw
artifacts are what lets a shipped asset be traced back to the generation that produced it.
An interrupted run is protected too, because deleting it would silently discard the work
``sdga run --resume`` exists to finish.

Packs are immutable, so pruning one is a deliberate removal of a published artifact. A
pack that cannot be parsed is left untouched and reported rather than guessed at.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .config import Config
from .errors import SdgaError

KeepPacks = int | Literal["all"]


@dataclass(frozen=True)
class GcTarget:
    """One directory selected for deletion, with the reason it was selected."""

    kind: str
    name: str
    path: Path
    display: str
    bytes: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "path": self.display,
            "bytes": self.bytes,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GcResult:
    dry_run: bool
    targets: tuple[GcTarget, ...]
    deleted: tuple[GcTarget, ...]
    protected: tuple[GcTarget, ...]
    kept_runs: int
    kept_packs: int

    @property
    def freed_bytes(self) -> int:
        return sum(target.bytes for target in self.deleted)

    @property
    def would_free_bytes(self) -> int:
        return sum(target.bytes for target in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "dry_run": self.dry_run,
            "targets": [target.to_dict() for target in self.targets],
            "deleted": [target.to_dict() for target in self.deleted],
            "protected": [target.to_dict() for target in self.protected],
            "kept_runs": self.kept_runs,
            "kept_packs": self.kept_packs,
            "would_free_bytes": self.would_free_bytes,
            "freed_bytes": self.freed_bytes,
        }

    def render(self) -> str:
        lines: list[str] = []
        if not self.targets:
            lines.append(
                f"nothing to delete; {self.kept_runs} run(s), {self.kept_packs} pack(s) kept"
            )
        else:
            verb = "would delete" if self.dry_run else "deleted"
            for target in self.targets:
                lines.append(f"{verb} {target.kind}/{target.name} ({_size(target.bytes)})")
            if self.dry_run:
                lines.append(f"dry run: nothing deleted; would free {_size(self.would_free_bytes)}")
            else:
                lines.append(f"freed {_size(self.freed_bytes)}")
        if self.protected:
            for target in self.protected:
                lines.append(f"protected {target.kind}/{target.name} ({target.reason})")
        return "\n".join(lines)


def _size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                # A file we cannot stat is not a reason to refuse pruning; its size is
                # simply absent from the report.
                continue
    return total


def _run_dirs(config: Config) -> list[Path]:
    root = config.root / config.project.runs_dir
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "run.json").is_file()),
        key=lambda path: path.name,
        reverse=True,
    )


def _pack_dirs(config: Config) -> list[Path]:
    root = config.root / config.project.packs_dir
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "pack.json").is_file()),
        key=lambda path: path.name,
        reverse=True,
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _published_runs(pack_dirs: list[Path]) -> tuple[dict[str, str], list[Path]]:
    """Map run id -> pack id for every readable pack, and return the readable packs."""
    published: dict[str, str] = {}
    readable: list[Path] = []
    for pack_dir in pack_dirs:
        manifest = _read_json(pack_dir / "pack.json")
        if manifest is None:
            continue
        readable.append(pack_dir)
        for asset in manifest.get("assets", []):
            if not isinstance(asset, dict):
                continue
            provenance = asset.get("provenance") or {}
            run_id = provenance.get("run_id") if isinstance(provenance, dict) else None
            if run_id:
                published[str(run_id)] = pack_dir.name
    return published, readable


def _run_status(run_dir: Path) -> str | None:
    record = _read_json(run_dir / "run.json")
    if record is None:
        return None
    return str(record.get("status") or "")


def _target(config: Config, kind: str, path: Path, reason: str) -> GcTarget:
    try:
        display = path.resolve().relative_to(config.root).as_posix()
    except ValueError:
        display = path.as_posix()
    return GcTarget(
        kind=kind,
        name=path.name,
        path=path,
        display=display,
        bytes=_dir_size(path),
        reason=reason,
    )


def collect_garbage(
    config: Config,
    *,
    keep_runs: int = 20,
    keep_packs: KeepPacks = "all",
    dry_run: bool = False,
) -> GcResult:
    """Select and optionally remove old runs/packs.

    ``keep_runs`` counts the newest runs regardless of publication; published and
    interrupted runs beyond that count are still protected. ``keep_packs`` is either
    ``"all"`` or a count of the newest readable packs. Unreadable packs are never deleted.
    """
    if keep_runs < 0:
        raise SdgaError("--keep-runs must be >= 0", remedy="pass a non-negative count")
    if keep_packs != "all" and keep_packs < 0:
        raise SdgaError("--keep-packs must be 'all' or >= 0", remedy="pass all or a count")

    run_dirs = _run_dirs(config)
    pack_dirs = _pack_dirs(config)
    published, readable_packs = _published_runs(pack_dirs)

    targets: list[GcTarget] = []
    protected: list[GcTarget] = []

    for index, run_dir in enumerate(run_dirs):
        if index < keep_runs:
            continue
        if run_dir.name in published:
            protected.append(
                _target(config, "runs", run_dir, f"published by {published[run_dir.name]}")
            )
            continue
        status = _run_status(run_dir)
        if status is None:
            protected.append(_target(config, "runs", run_dir, "unreadable run.json"))
            continue
        if status == "running":
            protected.append(_target(config, "runs", run_dir, "interrupted; resumable"))
            continue
        targets.append(_target(config, "runs", run_dir, "older than --keep-runs"))

    readable_names = {path.name for path in readable_packs}
    for pack_dir in pack_dirs:
        if pack_dir.name not in readable_names:
            protected.append(_target(config, "packs", pack_dir, "unreadable pack.json"))
    if keep_packs != "all":
        for index, pack_dir in enumerate(readable_packs):
            if index >= keep_packs:
                targets.append(_target(config, "packs", pack_dir, "older than --keep-packs"))

    targets.sort(key=lambda target: (target.kind, target.name))
    protected.sort(key=lambda target: (target.kind, target.name))

    deleted: list[GcTarget] = []
    if not dry_run:
        for target in targets:
            try:
                shutil.rmtree(target.path)
            except OSError as exc:
                raise SdgaError(
                    f"could not delete {target.display}: {exc}",
                    remedy="check permissions, then run `sdga gc --dry-run` to see what remains",
                ) from None
            deleted.append(target)

    return GcResult(
        dry_run=dry_run,
        targets=tuple(targets),
        deleted=tuple(deleted),
        protected=tuple(protected),
        kept_runs=len(run_dirs) - sum(1 for target in targets if target.kind == "runs"),
        kept_packs=len(pack_dirs) - sum(1 for target in targets if target.kind == "packs"),
    )


__all__ = ["GcResult", "GcTarget", "KeepPacks", "collect_garbage"]
