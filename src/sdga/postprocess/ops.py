"""Postprocess ops (docs/04-pipeline-stages.md §4).

Each op is a pure function of (image, context) -> image. That shape is deliberate: ops are
independently testable with a fixture and a golden output, and a chain is just a list of
names resolved through `OPS`, so the order a recipe declares is the order that runs.

Gates measure; ops change. Nothing here writes to disk.

Frame-aware ops (sheets) work per cell and paste back into the same sheet, so a chain can
mix whole-image ops (`palette_snap`) with per-frame ops (`center_anchor`) without any of
them having to know about the others.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PIL import Image, ImageFilter

from .palette import RGB, snap_to_palette

RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class OpContext:
    """Everything an op may need, resolved once per asset.

    `size` is the *final image* size: the whole sheet for `sprite_sheet`, the cell for every
    other kind. `frames`/`layout` are what turn that into cells.
    """

    size: tuple[int, int]
    palette: tuple[RGB, ...] = ()
    grid: int = 1
    frames: int = 1
    layout: tuple[int, int] = (1, 1)
    anchor: str = "feet"  # feet | center
    strength: float = 2.0  # depth_to_normal
    flip_g: bool = False  # depth_to_normal, for Godot's 2D convention
    min_area: int = 2  # despeckle
    tolerance: int = 24  # bg_remove

    @property
    def columns(self) -> int:
        return max(1, self.layout[0])

    @property
    def rows(self) -> int:
        return max(1, self.layout[1])

    @property
    def cell(self) -> tuple[int, int]:
        """Cell size. The sheet is `columns * cell_w` by `rows * cell_h`."""
        if self.frames <= 1 and self.layout == (1, 1):
            return self.size
        return (self.size[0] // self.columns, self.size[1] // self.rows)


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


# --------------------------------------------------------------------- frames


def cell_boxes(ctx: OpContext) -> list[tuple[int, int, int, int]]:
    """The `(left, upper, right, lower)` box of every frame, in reading order."""
    cell_w, cell_h = ctx.cell
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(max(1, ctx.frames)):
        x = (index % ctx.columns) * cell_w
        y = (index // ctx.columns) * cell_h
        boxes.append((x, y, x + cell_w, y + cell_h))
    return boxes


def frame_grid(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Normalise the sheet to exactly `columns * cell` by `rows * cell`.

    The backend renders the whole sheet at generation resolution, so this is where a sheet
    is averaged down to its final size — once, for the whole sheet, so every frame gets the
    same treatment. Without this an 8-frame sheet would be cut into 8 unequal pieces.
    """
    source = image.convert("RGBA")
    expected = (ctx.cell[0] * ctx.columns, ctx.cell[1] * ctx.rows)
    if source.size == expected:
        return source
    return source.resize(expected, Image.Resampling.BOX)


def _each_frame(
    image: Image.Image, ctx: OpContext, fn: Callable[[Image.Image, int], Image.Image]
) -> Image.Image:
    """Apply `fn` to every cell and paste the result back at the same offset."""
    source = image.convert("RGBA")
    result = Image.new("RGBA", source.size, (0, 0, 0, 0))
    for index, box in enumerate(cell_boxes(ctx)):
        cell = source.crop(box)
        placed = fn(cell, index)
        result.paste(placed, (box[0], box[1]))
    return result


def _bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    box = image.getchannel("A").getbbox()
    return None if box is None else (box[0], box[1], box[2], box[3])


def alpha_trim(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Move each frame's visible content to its cell origin, dropping transparent margin.

    Trimming is a repositioning, never a resize: a cell that shrank would break the sheet
    grid, so the content keeps its own pixels and only its offset changes.
    """

    def trim(cell: Image.Image, _index: int) -> Image.Image:
        box = _bbox(cell)
        if box is None:
            return cell
        cropped = cell.crop(box)
        placed = Image.new("RGBA", cell.size, (0, 0, 0, 0))
        placed.paste(cropped, (0, 0))
        return placed

    return _each_frame(image, ctx, trim)


def center_anchor(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Anchor each frame: `feet` on the bottom centre line, or `center` for icons.

    Feet anchoring rather than bbox centring is what stops a walk cycle bobbing: the bbox
    grows when the legs are apart, so its midpoint moves even though the character did not
    (docs/04 §4.2). An empty frame is an error, never a silent skip.
    """
    cell_w, cell_h = ctx.cell

    def anchor(cell: Image.Image, index: int) -> Image.Image:
        box = _bbox(cell)
        if box is None:
            raise ValueError(f"frame {index} is empty: nothing to anchor")
        content = cell.crop(box)
        placed = Image.new("RGBA", cell.size, (0, 0, 0, 0))
        target_x = (cell_w - content.width) // 2
        target_y = (
            cell_h - content.height if ctx.anchor == "feet" else (cell_h - content.height) // 2
        )
        placed.paste(content, (max(0, target_x), max(0, target_y)))
        return placed

    return _each_frame(image, ctx, anchor)


def ninepatch_mirror(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Mirror the left half onto the right and the top half onto the bottom.

    Bitwise symmetry is the only kind a gate can check, and a symmetric border is what makes
    a 9-slice frame stretch without drifting.
    """

    def mirror(cell: Image.Image, _index: int) -> Image.Image:
        width, height = cell.size
        half_w, half_h = width // 2, height // 2
        result = cell.copy()
        left = cell.crop((0, 0, half_w, height))
        result.paste(left.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (width - half_w, 0))
        top = result.crop((0, 0, width, half_h))
        result.paste(top.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, height - half_h))
        return result

    return _each_frame(image, ctx, mirror)


def ninepatch_margins(image: Image.Image) -> tuple[int, int]:
    """The uniform border size, in pixels: how many rows/columns every edge repeats.

    A row is part of the margin when it is identical to the outermost row on that side, which
    is exactly the region a 9-slice stretch may repeat without a visible seam.
    """
    source = image.convert("RGBA")
    raw = source.tobytes()
    width, height = source.size

    stride = width * 4

    def row(y: int) -> bytes:
        return raw[y * stride : (y + 1) * stride]

    def column(x: int) -> bytes:
        return b"".join(
            raw[offset + x * 4 : offset + (x + 1) * 4] for offset in range(0, len(raw), stride)
        )

    # Capped at (edge - 1) // 2 so a uniform image reports the largest legal margin instead
    # of a margin that leaves no stretchable centre (the 9-slice geometric rule).
    vertical_cap = (height - 1) // 2
    horizontal_cap = (width - 1) // 2

    vertical = 0
    while vertical < vertical_cap and row(vertical) == row(0):
        vertical += 1
    horizontal = 0
    while horizontal < horizontal_cap and column(horizontal) == column(0):
        horizontal += 1
    return horizontal, vertical


# --------------------------------------------------------------------- texture


def tile_mirror(image: Image.Image, ctx: OpContext) -> Image.Image:
    """2x2 mirror mosaic, then average back down: always seamless, always symmetric."""
    source = image.convert("RGBA")
    width, height = source.size
    mosaic = Image.new("RGBA", (width * 2, height * 2))
    mosaic.paste(source, (0, 0))
    mosaic.paste(source.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (width, 0))
    mosaic.paste(source.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, height))
    mosaic.paste(source.transpose(Image.Transpose.ROTATE_180), (width, height))
    return mosaic.resize((width, height), Image.Resampling.BOX)


def tile_offset_blend(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Roll by half a tile, then crossfade a narrow band over the new seam.

    Alternative to circular sampling: no wraparound filter, just a roll and a linear fade
    across `grid` pixels of the seam.
    """
    source = image.convert("RGBA")
    width, height = source.size
    rolled = Image.new("RGBA", source.size)
    rolled.paste(source.crop((width // 2, 0, width, height)), (0, 0))
    rolled.paste(source.crop((0, 0, width // 2, height)), (width - width // 2, 0))

    band = max(1, min(ctx.grid, width // 2, height // 2))
    result = rolled.copy()
    for offset in range(band):
        alpha = (band - offset) / (band + 1)
        for x in (width // 2 - band // 2 + offset,):
            strip = Image.blend(
                result.crop((x, 0, x + 1, height)),
                result.crop((x - width // 2, 0, x - width // 2 + 1, height)),
                alpha,
            )
            result.paste(strip, (x, 0))
    return result


# --------------------------------------------------------------------- normal maps


def _luma(image: Image.Image) -> list[float]:
    raw = image.convert("L").tobytes()
    return [value / 255.0 for value in raw]


def _sobel(field: list[float], width: int, height: int) -> tuple[list[float], list[float]]:
    """3x3 Sobel with clamped edges, so a flat field yields exactly zero gradient."""

    def at(x: int, y: int) -> float:
        return field[min(height - 1, max(0, y)) * width + min(width - 1, max(0, x))]

    grad_x: list[float] = []
    grad_y: list[float] = []
    for y in range(height):
        for x in range(width):
            gx = (
                at(x + 1, y - 1)
                + 2 * at(x + 1, y)
                + at(x + 1, y + 1)
                - at(x - 1, y - 1)
                - 2 * at(x - 1, y)
                - at(x - 1, y + 1)
            )
            gy = (
                at(x - 1, y + 1)
                + 2 * at(x, y + 1)
                + at(x + 1, y + 1)
                - at(x - 1, y - 1)
                - 2 * at(x, y - 1)
                - at(x + 1, y - 1)
            )
            grad_x.append(gx / 8.0)
            grad_y.append(gy / 8.0)
    return grad_x, grad_y


def depth_to_normal(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Height field -> tangent-space normal map (docs/04 §4.3).

    Encoding a depth map directly as a normal texture makes every pixel face the camera, so
    lighting comes out flat. Taking the gradient and re-encoding is what makes the texture
    mean "surface direction".
    """
    source = image.convert("RGBA")
    width, height = source.size
    blurred = source.convert("L").filter(ImageFilter.GaussianBlur(radius=1))
    grad_x, grad_y = _sobel(_luma(blurred), width, height)

    result = Image.new("RGBA", (width, height), (128, 128, 255, 255))
    pixels: list[RGBA] = []
    for index in range(width * height):
        nx = -grad_x[index] * ctx.strength
        ny = -grad_y[index] * ctx.strength
        if ctx.flip_g:
            ny = -ny
        length = (nx * nx + ny * ny + 1.0) ** 0.5
        nx, ny, nz = nx / length, ny / length, 1.0 / length
        alpha = source.getchannel("A").tobytes()[index]
        pixels.append(
            (
                int(round((nx * 0.5 + 0.5) * 255)),
                int(round((ny * 0.5 + 0.5) * 255)),
                int(round((nz * 0.5 + 0.5) * 255)),
                alpha,
            )
        )
    result.putdata(pixels)
    return result


# --------------------------------------------------------------------- cleanup


def despeckle(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Drop islands of visible pixels smaller than `min_area`, keeping everything else.

    AI renders leave single-pixel crumbs around the silhouette; in pixel art one stray pixel
    is a visible wart. Deterministic flood fill, 4-neighbour, scan order.
    """
    source = image.convert("RGBA")
    width, height = source.size
    raw = source.tobytes()
    visible = [raw[offset + 3] > 0 for offset in range(0, len(raw), 4)]
    seen = [False] * (width * height)
    keep = list(visible)

    for start in range(width * height):
        if not visible[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = True
        island: list[int] = []
        while stack:
            index = stack.pop()
            island.append(index)
            x, y = index % width, index // width
            for neighbour in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                nx, ny = neighbour
                if 0 <= nx < width and 0 <= ny < height:
                    candidate = ny * width + nx
                    if visible[candidate] and not seen[candidate]:
                        seen[candidate] = True
                        stack.append(candidate)
        if len(island) < max(1, ctx.min_area):
            for index in island:
                keep[index] = False

    if keep == visible:
        return source
    pixels: list[RGBA] = []
    for index in range(width * height):
        offset = index * 4
        if keep[index]:
            pixels.append((raw[offset], raw[offset + 1], raw[offset + 2], raw[offset + 3]))
        else:
            pixels.append((0, 0, 0, 0))
    result = Image.new("RGBA", (width, height))
    result.putdata(pixels)
    return result


def _border_colour(image: Image.Image) -> RGB | None:
    """The most common visible colour on the outermost ring, if there is one."""
    source = image.convert("RGBA")
    width, height = source.size
    raw = source.tobytes()
    counts: dict[RGB, int] = {}

    def sample(x: int, y: int) -> None:
        offset = (y * width + x) * 4
        if raw[offset + 3]:
            colour = (raw[offset], raw[offset + 1], raw[offset + 2])
            counts[colour] = counts.get(colour, 0) + 1

    for x in range(width):
        sample(x, 0)
        sample(x, height - 1)
    for y in range(1, height - 1):
        sample(0, y)
        sample(width - 1, y)

    if not counts:
        return None
    return max(counts, key=lambda colour: (counts[colour], colour))


def bg_remove(image: Image.Image, ctx: OpContext) -> Image.Image:
    """Flood-fill the border colour away from the edges: an optional authoring cleanup.

    Optional by design: a rendered sprite usually already has alpha, and cutting a background
    out of a *generated* asset would hide the fact that the prompt asked for transparency.
    """
    source = image.convert("RGBA")
    width, height = source.size
    background = _border_colour(source)
    if background is None:
        return source

    raw = source.tobytes()
    removed = [False] * (width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        stack.extend(((0, y), (width - 1, y)))

    def matches(x: int, y: int) -> bool:
        offset = (y * width + x) * 4
        if raw[offset + 3] == 0:
            return False
        return all(
            abs(raw[offset + channel] - background[channel]) <= ctx.tolerance
            for channel in range(3)
        )

    while stack:
        x, y = stack.pop()
        index = y * width + x
        if removed[index] or not matches(x, y):
            continue
        removed[index] = True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                stack.append((nx, ny))

    if not any(removed):
        return source
    pixels: list[RGBA] = []
    for index in range(width * height):
        offset = index * 4
        if removed[index]:
            pixels.append((0, 0, 0, 0))
        else:
            pixels.append((raw[offset], raw[offset + 1], raw[offset + 2], raw[offset + 3]))
    result = Image.new("RGBA", (width, height))
    result.putdata(pixels)
    return result


OPS: Mapping[str, Op] = {
    "downscale_box": downscale_box,
    "downscale_nearest": downscale_nearest,
    "palette_snap": palette_snap,
    "alpha_hard": alpha_hard,
    "alpha_trim": alpha_trim,
    "center_anchor": center_anchor,
    "frame_grid": frame_grid,
    "ninepatch_mirror": ninepatch_mirror,
    "pad_to_grid": pad_to_grid,
    "tile_mirror": tile_mirror,
    "tile_offset_blend": tile_offset_blend,
    "depth_to_normal": depth_to_normal,
    "despeckle": despeckle,
    "bg_remove": bg_remove,
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
    "alpha_trim",
    "apply_chain",
    "bg_remove",
    "cell_boxes",
    "center_anchor",
    "depth_to_normal",
    "despeckle",
    "downscale_box",
    "downscale_nearest",
    "frame_grid",
    "ninepatch_margins",
    "ninepatch_mirror",
    "pad_to_grid",
    "palette_snap",
    "tile_mirror",
    "tile_offset_blend",
]
