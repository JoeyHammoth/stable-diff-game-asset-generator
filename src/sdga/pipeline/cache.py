"""Stage 2: resolve — the artifact cache (docs/04-pipeline-stages.md §2).

The key is `request_hash` *and* `profile_hash`: a driver, model, or ComfyUI change invalidates
rather than silently mixing outputs from two machines. Only the **raw** backend artifact is
cached. Postprocess and gates are cheap, deterministic, and may since have changed (a new op,
a new gate, a new spec threshold), so they always re-run over the cached pixels — that is what
makes a cache hit identical to a fresh generation rather than merely similar.

Everything here is defensive on purpose. The cache is a speedup, never a correctness
dependency: a missing index, an unreadable entry, a deleted file, or bytes that no longer match
their recorded hash is a *miss*, never an error. `rm -rf .sdga/cache` is always safe.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canonical import hash_file

CACHE_SCHEMA = 1
INDEX_NAME = "index.json"


@dataclass(frozen=True)
class CacheEntry:
    """One cached raw artifact. `file` is relative to the cache root."""

    request_hash: str
    profile_hash: str
    file: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "profile_hash": self.profile_hash,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


def _filename(request_hash: str) -> str:
    """`request_hash` carries a `sha256:` prefix; a colon is not a legal filename on Windows."""
    return request_hash.split(":", 1)[-1] + ".png"


class ArtifactCache:
    """A flat directory of raw artifacts plus one JSON index.

    `read=False` implements `--force` (regenerate, but still fill the cache back up);
    `write=False` implements `--no-cache` (touch nothing at all).
    """

    def __init__(self, root: Path, *, read: bool = True, write: bool = True) -> None:
        self.root = Path(root)
        self.reading = read
        self.writing = write
        self._entries: dict[str, CacheEntry] = self._load()

    # ------------------------------------------------------------------ index

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def _load(self) -> dict[str, CacheEntry]:
        path = self.index_path
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt index is a cold cache, not a broken run.
            return {}
        if not isinstance(raw, dict) or raw.get("schema") != CACHE_SCHEMA:
            return {}
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return {}

        loaded: dict[str, CacheEntry] = {}
        for key, value in entries.items():
            if not isinstance(value, dict):
                continue
            try:
                loaded[str(key)] = CacheEntry(
                    request_hash=str(key),
                    profile_hash=str(value["profile_hash"]),
                    file=str(value["file"]),
                    sha256=str(value["sha256"]),
                    bytes=int(value.get("bytes") or 0),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return loaded

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        body = {
            "schema": CACHE_SCHEMA,
            "entries": {key: entry.to_dict() for key, entry in sorted(self._entries.items())},
        }
        temporary = self.root / (INDEX_NAME + ".tmp")
        temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.index_path)

    # ------------------------------------------------------------------ public

    def lookup(self, request_hash: str, profile_hash: str) -> CacheEntry | None:
        """A hit needs a matching profile and bytes that are still what the index recorded."""
        if not self.reading:
            return None
        entry = self._entries.get(request_hash)
        if entry is None or entry.profile_hash != profile_hash:
            return None
        path = self.root / entry.file
        if not path.is_file() or hash_file(path) != entry.sha256:
            return None
        return entry

    def store(self, request_hash: str, profile_hash: str, source: Path) -> CacheEntry | None:
        """Copy a freshly generated raw artifact into the cache and index it."""
        if not self.writing:
            return None
        source = Path(source)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / _filename(request_hash)
        shutil.copyfile(source, target)
        entry = CacheEntry(
            request_hash=request_hash,
            profile_hash=profile_hash,
            file=target.name,
            sha256=hash_file(target),
            bytes=target.stat().st_size,
        )
        self._entries[request_hash] = entry
        self._save()
        return entry

    def link(self, entry: CacheEntry, dest: Path) -> Path:
        """Materialise a hit in the run directory, sharing bytes where the filesystem allows."""
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = self.root / entry.file
        try:
            os.link(source, target)
        except OSError:
            # Another volume, or a filesystem without hard links. A copy is still correct,
            # so this is a disk-space decision, not a failure.
            shutil.copyfile(source, target)
        return target

    @property
    def size(self) -> int:
        return len(self._entries)

    def __contains__(self, request_hash: object) -> bool:
        return request_hash in self._entries


__all__ = ["CACHE_SCHEMA", "INDEX_NAME", "ArtifactCache", "CacheEntry"]
