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
    aa_suspect,
    evaluate,
    failed,
    frame_bottom_rows,
    frame_count,
    frames_aligned,
    normal_map_valid,
    seam_ratio,
    severity,
    symmetry_9patch,
)

__all__ = [
    "DEFAULT_GATES",
    "FAIL",
    "GATES",
    "PASS",
    "SKIPPED",
    "GateContext",
    "GateResult",
    "aa_suspect",
    "evaluate",
    "failed",
    "frame_bottom_rows",
    "frame_count",
    "frames_aligned",
    "normal_map_valid",
    "seam_ratio",
    "severity",
    "symmetry_9patch",
]
