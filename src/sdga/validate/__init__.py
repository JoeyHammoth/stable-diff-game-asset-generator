"""Gates: deterministic acceptance checks over produced artifacts."""

from __future__ import annotations

from .gates import (
    DEFAULT_GATES,
    FAIL,
    GATES,
    PASS,
    SKIPPED,
    GateContext,
    GateResult,
    evaluate,
    failed,
    frame_bottom_rows,
    seam_ratio,
    severity,
)

__all__ = [
    "DEFAULT_GATES",
    "FAIL",
    "GATES",
    "PASS",
    "SKIPPED",
    "GateContext",
    "GateResult",
    "evaluate",
    "failed",
    "frame_bottom_rows",
    "seam_ratio",
    "severity",
]
