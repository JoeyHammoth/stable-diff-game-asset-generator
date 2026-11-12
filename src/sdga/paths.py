"""Path rules: project-relative only (docs/01-architecture.md, rule 3).

A path that is absolute, drive-qualified, or escapes the project root can never be
reproduced on another machine, so it is rejected at load time rather than at generation
time when it is far more expensive to diagnose.
"""

from __future__ import annotations

import re

from .errors import ConfigError

_DRIVE = re.compile(r"^[A-Za-z]:")


def relative_path(value: str, where: str, key: str) -> str:
    """Normalise a configured path to forward slashes and reject anything non-portable."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty path", location=where)
    posix = value.strip().replace("\\", "/")
    if posix.startswith("/") or _DRIVE.match(posix):
        raise ConfigError(
            f"{key} must be relative to the project root, not absolute: {value!r}",
            location=where,
            remedy="paths resolve against [project] root; move the file inside the project",
        )
    parts = posix.split("/")
    if ".." in parts:
        raise ConfigError(
            f"{key} must not escape the project root: {value!r}",
            location=where,
            remedy="keep referenced files inside the project directory",
        )
    return posix


__all__ = ["relative_path"]
