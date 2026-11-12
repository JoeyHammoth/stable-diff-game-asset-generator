"""Postprocess ops (docs/04-pipeline-stages.md §4).

Each op is a pure function of (image, context) -> image. That shape is deliberate: ops are
independently testable with a fixture and a golden output, and a chain is just a list of
names resolved through `OPS`, so the order a recipe declares is the order that runs.

Gates measure; ops change. Nothing here writes to disk.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PIL import Image

from .palette import RGB, snap_to_palette


@dataclass(frozen=True)
class OpContext:
    """Everything an op may need, resolved once per asset."""

    size: tuple[int, int]
    palette: tuple[RGB, ...] = ()
    grid: int = 1


Op = Callable[[Image.Image, OpContext], Image.Image]


def downscale_box(image: Image.Image, ctx: OpContext) -> Image.Image:
    """The default. Averages the render before snapping, preserving structure."""
    return image.convert("RGBA").resize(ctx.size, Image.Resampling.BOX)


def downscale_nearest(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Only when the render is already grid-aligned and hard-edged."""
    return image.convert("RGBA").resize(ctx.size, Image.Resampling.NEAREST)


def palette_snap(image: Image.Image, ctx: OpContext) -> Image.Image:
    return snap_to_palette(image, ctx.palette)


def alpha_hard(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Pixel art has binary alpha. This removes the anti-aliased fringe AI renders leave."""
    source = image.convert("RGBA")
    thresholded = source.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    result = source.copy()
    result.putalpha(thresholded)
    return result


def pad_to_grid(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Extend to a whole number of grid cells with transparent pixels."""
    source = image.convert("RGBA")
    step = max(1, ctx.grid)
    width, height = source.size
    padded = (
        ((width + step - 1) // step) * step,
        ((height + step - 1) // step) * step,
    )
    if padded == (width, height):
        return source
    result = Image.new("RGBA", padded, (0, 0, 0, 0))
    result.paste(source, (0, 0))
    return result


OPS: Mapping[str, Op] = {
    "downscale_box": downscale_box,
    "downscale_nearest": downscale_nearest,
    "palette_snap": palette_snap,
    "alpha_hard": alpha_hard,
    "pad_to_grid": pad_to_grid,
}


def apply_chain(image: Image.Image, chain: Sequence[str], ctx: OpContext) -> Image.Image:
    """Run ops in declared order. An unknown name is a recipe bug, not a runtime fallback."""
    result = image
    for name in chain:
        try:
            op = OPS[name]
        except KeyError:
            raise KeyError(
                f"unknown postprocess op {name!r}; known ops: {', '.join(sorted(OPS))}"
            ) from None
        result = op(result, ctx)
    return result


__all__ = [
    "OPS",
    "Op",
    "OpContext",
    "alpha_hard",
    "apply_chain",
    "downscale_box",
    "downscale_nearest",
    "pad_to_grid",
    "palette_snap",
]
