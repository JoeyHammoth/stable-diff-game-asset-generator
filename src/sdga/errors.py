"""Error model and exit codes.

Both are contract (docs/03-contracts-and-schemas.md §7 and §8). Scripts branch on the exit
code, so a new error class must pick one of the four documented codes rather than inventing
a fifth.

    0 success · 1 gate/review/asset failure · 2 usage · 3 backend unavailable · 4 schema or config
"""

from __future__ import annotations

from typing import Any, Mapping

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_BACKEND = 3
EXIT_SCHEMA = 4

# kind -> (exit code, retryable)
BACKEND_KINDS: dict[str, tuple[int, bool]] = {
    "unreachable": (EXIT_BACKEND, True),
    "timeout": (EXIT_BACKEND, True),
    "missing_capability": (EXIT_BACKEND, False),
    "rejected_graph": (EXIT_FAILURE, False),
    "execution_error": (EXIT_FAILURE, True),
    "bad_output": (EXIT_FAILURE, False),
    "cancelled": (EXIT_FAILURE, False),
}


class SdgaError(Exception):
    """Base error. Every message names the problem and, where possible, the remedy."""

    exit_code = EXIT_FAILURE

    def __init__(
        self,
        message: str,
        *,
        remedy: str | None = None,
        location: str | None = None,
    ) -> None:
        self.message = message
        self.remedy = remedy
        self.location = location
        super().__init__(self.render())

    def render(self) -> str:
        head = f"{self.location}: {self.message}" if self.location else self.message
        return f"{head}\n  → {self.remedy}" if self.remedy else head


class UsageError(SdgaError):
    """The command line was wrong: unknown flag, missing argument, command not in this build."""

    exit_code = EXIT_USAGE


class ConfigError(SdgaError):
    """`sdga.toml` is unreadable, incomplete, or contains an unknown key."""

    exit_code = EXIT_SCHEMA


class SpecError(SdgaError):
    """An asset spec is invalid. Always carries file:line where a line is knowable."""

    exit_code = EXIT_SCHEMA


class SlotResolutionError(SdgaError):
    """A recipe slot could not be resolved. Hard error at plan time, never a null at submit."""

    exit_code = EXIT_SCHEMA


class GateFailure(SdgaError):
    """An asset was produced but did not meet its acceptance thresholds."""

    exit_code = EXIT_FAILURE


class BackendError(SdgaError):
    """A closed set of failures that may cross the backend seam."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        remedy: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        if kind not in BACKEND_KINDS:
            raise ValueError(f"unknown backend error kind {kind!r}; known: {sorted(BACKEND_KINDS)}")
        code, retryable = BACKEND_KINDS[kind]
        self.kind = kind
        self.retryable = retryable
        self.detail = detail
        self.payload = dict(payload or {})
        super().__init__(f"{kind}: {detail}", remedy=remedy)
        self.exit_code = code
