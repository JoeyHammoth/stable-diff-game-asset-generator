"""Postprocess: deterministic, testable, backend-independent pixel fixes."""

from __future__ import annotations

from .ops import (
    OPS,
    Op,
    OpContext,
    alpha_hard,
    apply_chain,
    downscale_box,
    downscale_nearest,
    pad_to_grid,
    palette_snap,
)
from .palette import extract_colours, nearest_palette_index, rgb_to_oklab, snap_to_palette

__all__ = [
    "OPS",
    "Op",
    "OpContext",
    "alpha_hard",
    "apply_chain",
    "downscale_box",
    "downscale_nearest",
    "extract_colours",
    "nearest_palette_index",
    "pad_to_grid",
    "palette_snap",
    "rgb_to_oklab",
    "snap_to_palette",
]
