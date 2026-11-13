"""Postprocess: deterministic, testable, backend-independent pixel fixes."""

from __future__ import annotations

from .ops import (
    OPS,
    Op,
    OpContext,
    alpha_hard,
    alpha_trim,
    apply_chain,
    bg_remove,
    cell_boxes,
    center_anchor,
    depth_to_normal,
    despeckle,
    downscale_box,
    downscale_nearest,
    frame_grid,
    ninepatch_margins,
    ninepatch_mirror,
    pad_to_grid,
    palette_snap,
    tile_mirror,
    tile_offset_blend,
)
from .palette import extract_colours, nearest_palette_index, rgb_to_oklab, snap_to_palette

__all__ = [
    "OPS",
    "Op",
    "OpContext",
    "alpha_hard",
    "alpha_trim",
    "apply_chain",
    "bg_remove",
    "cell_boxes",
    "center_anchor",
    "depth_to_normal",
    "despeckle",
    "downscale_box",
    "downscale_nearest",
    "extract_colours",
    "frame_grid",
    "nearest_palette_index",
    "ninepatch_margins",
    "ninepatch_mirror",
    "pad_to_grid",
    "palette_snap",
    "rgb_to_oklab",
    "snap_to_palette",
    "tile_mirror",
    "tile_offset_blend",
]
