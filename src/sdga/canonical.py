"""Canonical serialisation and hashing.

Three contracts rest on this module:

* `request_hash` — the cache key. Canonical JSON means key order can never produce a
  spurious cache miss.
* style contract hash — cache invalidation. Two projects that differ only in, say,
  `max_concurrency` must hash equal.
* `plan.json` — byte-stable output, so a diff means something actually changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20


def _default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "__fspath__"):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"cannot canonicalise {type(value).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    """Sorted keys, no whitespace, UTF-8, no NaN. This is the only serialisation hashed."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_default,
    ).encode("utf-8")


def canonical_json(obj: Any) -> str:
    return canonical_bytes(obj).decode("utf-8")


def pretty_json(obj: Any) -> str:
    """Human-facing JSON for files people review (plan.json). Still deterministic."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_tagged(data: bytes) -> str:
    """Stored hashes carry their algorithm, so a future migration is unambiguous."""
    return "sha256:" + sha256_bytes(data)


def hash_obj(obj: Any) -> str:
    return sha256_tagged(canonical_bytes(obj))


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def fold32(text: str) -> int:
    """Fold a string to a 32-bit integer (seed derivation, docs/04 §1 step 4)."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")
