"""Gates (docs/04-pipeline-stages.md §5).

A gate is a named, deterministic check with a threshold that returns `pass`, `fail` or
`skipped` plus the measured value. Two rules make them trustworthy:

* a gate never mutates the artifact it measures;
* a gate that cannot apply records `skipped`, never `pass` (invariant 8).

The measured value is printed on failure, because "seamless_tile failed" is useless and
"seamless_tile 4.31 > 1.5" is a diagnosis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from PIL import Image

from ..model import AssetKind
from ..postprocess.ops import ninepatch_margins
from ..postprocess.palette import RGB

PASS = "pass"
FAIL = "fail"
SKIPPED = "skipped"

SEVERITIES = ("error", "warn", "off")


@dataclass(frozen=True)
class GateContext:
    size: tuple[int, int]
    quantum: int = 1
    palette: tuple[RGB, ...] = ()
    thresholds: Mapping[str, Any] = field(default_factory=dict)
    kind: AssetKind | None = None
    frames: int = 1
    layout: tuple[int, int] = (1, 1)

    def threshold(self, name: str, default: float) -> float:
        value = self.thresholds.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @property
    def columns(self) -> int:
        return max(1, self.layout[0])

    @property
    def rows(self) -> int:
        return max(1, self.layout[1])

    @property
    def cell(self) -> tuple[int, int]:
        if self.frames <= 1 and self.layout == (1, 1):
            return self.size
        return (self.size[0] // self.columns, self.size[1] // self.rows)


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str
    value: Any = None
    threshold: Any = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"gate": self.gate, "status": self.status, "value": self.value}
        if self.threshold is not None:
            body["threshold"] = self.threshold
        if self.detail:
            body["detail"] = self.detail
        return body


Gate = Callable[[Image.Image, GateContext], GateResult]


def _visible_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    raw = image.convert("RGBA").tobytes()
    return [
        (raw[index], raw[index + 1], raw[index + 2])
        for index in range(0, len(raw), 4)
        if raw[index + 3] > 0
    ]


def dimensions_exact(image: Image.Image, ctx: GateContext) -> GateResult:
    size = list(image.size)
    return GateResult(
        "dimensions_exact",
        PASS if tuple(image.size) == tuple(ctx.size) else FAIL,
        value=size,
        threshold=list(ctx.size),
    )


def grid_divisible(image: Image.Image, ctx: GateContext) -> GateResult:
    quantum = max(1, ctx.quantum)
    remainders = [image.size[0] % quantum, image.size[1] % quantum]
    return GateResult(
        "grid_divisible",
        PASS if remainders == [0, 0] else FAIL,
        value=remainders,
        threshold=quantum,
    )


def frame_count(image: Image.Image, ctx: GateContext) -> GateResult:
    """The sheet must hold exactly `frames` cells, laid out as declared.

    Counting cells from the declared layout is the point: inferring columns from the width
    is what makes an 8-frame sheet look like a 4-frame one after a bad resize.
    """
    count = ctx.columns * ctx.rows
    expected = (ctx.cell[0] * ctx.columns, ctx.cell[1] * ctx.rows)
    ok = count == max(1, ctx.frames) and tuple(image.size) == expected
    return GateResult(
        "frame_count",
        PASS if ok else FAIL,
        value=[count, list(ctx.layout)],
        threshold=max(1, ctx.frames),
        detail=f"image {list(image.size)}, expected {list(expected)}",
    )


def frame_bottom_rows(image: Image.Image, ctx: GateContext) -> list[int | None]:
    """The lowest visible row of each frame, in reading order. `None` means an empty frame."""
    source = image.convert("RGBA")
    cell_w, cell_h = ctx.cell
    bottoms: list[int | None] = []
    for index in range(max(1, ctx.frames)):
        x = (index % ctx.columns) * cell_w
        y = (index // ctx.columns) * cell_h
        box = source.getchannel("A").crop((x, y, x + cell_w, y + cell_h)).getbbox()
        bottoms.append(None if box is None else box[3] - 1)
    return bottoms


def frames_aligned(image: Image.Image, ctx: GateContext) -> GateResult:
    """All frames must touch the same ground line within ±1 px.

    The feet anchor is what keeps a walk cycle from bobbing; this gate is the proof that the
    anchoring actually happened, and an empty frame fails because it would silently hold the
    previous pose (docs/04 §4.2).
    """
    bottoms = frame_bottom_rows(image, ctx)
    if any(bottom is None for bottom in bottoms):
        empty = [index for index, bottom in enumerate(bottoms) if bottom is None]
        return GateResult(
            "frames_aligned",
            FAIL,
            value=bottoms,
            detail=f"empty frame(s): {', '.join(str(index) for index in empty)}",
        )
    rows = [bottom for bottom in bottoms if bottom is not None]
    spread = max(rows) - min(rows)
    return GateResult(
        "frames_aligned",
        PASS if spread <= 1 else FAIL,
        value=spread,
        threshold=1,
        detail=f"bottom rows {rows}",
    )


def palette_conformance(image: Image.Image, ctx: GateContext) -> GateResult:
    if not ctx.palette:
        return GateResult("palette_conformance", SKIPPED, detail="no palette configured")
    allowed = set(ctx.palette)
    visible = _visible_pixels(image)
    off_palette = sum(1 for pixel in visible if pixel not in allowed)
    return GateResult(
        "palette_conformance",
        PASS if off_palette == 0 else FAIL,
        value=off_palette,
        threshold=0,
        detail=f"{len(set(visible))} distinct colour(s), {len(visible)} visible pixel(s)",
    )


def max_unique_colors(image: Image.Image, ctx: GateContext) -> GateResult:
    limit = int(ctx.threshold("max_unique_colors", 32))
    distinct = len(set(_visible_pixels(image)))
    return GateResult(
        "max_unique_colors",
        PASS if distinct <= limit else FAIL,
        value=distinct,
        threshold=limit,
    )


def alpha_required(image: Image.Image, ctx: GateContext) -> GateResult:
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    return GateResult("alpha_required", PASS if has_alpha else FAIL, value=image.mode)


def binary_alpha(image: Image.Image, ctx: GateContext) -> GateResult:
    if image.mode not in ("RGBA", "LA"):
        return GateResult("binary_alpha", SKIPPED, detail="no alpha channel")
    alpha = image.convert("RGBA").getchannel("A").tobytes()
    partial = sum(1 for value in alpha if value not in (0, 255))
    return GateResult("binary_alpha", PASS if partial == 0 else FAIL, value=partial)


def symmetry_9patch(image: Image.Image, ctx: GateContext) -> GateResult:
    """Bitwise mirror symmetry plus 9-slice margins that cannot overlap.

    `2 * max(margin) < edge` is the geometric requirement: margins wider than half the edge
    leave no stretchable centre, so the slice degenerates when an engine resizes it.
    """
    source = image.convert("RGBA")
    width, height = source.size
    mirrored = source.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    left_right = source.tobytes() == mirrored.tobytes()
    top_bottom = source.tobytes() == source.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    symmetric = left_right and top_bottom

    horizontal, vertical = ninepatch_margins(source)
    edge = min(width, height)
    roomy = 2 * max(horizontal, vertical) < edge
    return GateResult(
        "symmetry_9patch",
        PASS if symmetric and roomy else FAIL,
        value=[horizontal, vertical],
        threshold={"max_margin": (edge - 1) // 2, "symmetric": symmetric},
        detail="mirror-exact" if symmetric else "not mirror-symmetric",
    )


def _channel_difference(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return (abs(left[0] - right[0]) + abs(left[1] - right[1]) + abs(left[2] - right[2])) / 3.0


def seam_ratio(image: Image.Image) -> float:
    """How much harder the wrap seam is than a typical interior edge.

    The seam pairs the last column with the first (and the last row with the first) — the
    edges a tile repeats against. Dividing by the median interior difference makes the
    result scale-free: ~1.0 means the seam is indistinguishable from the interior, and a
    discontinuity shows up as a large ratio instead of a subjective "looks wrong".
    """
    source = image.convert("RGB")
    width, height = source.size
    raw = source.tobytes()

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 3
        return raw[offset], raw[offset + 1], raw[offset + 2]

    seam_vertical = (
        sum(_channel_difference(pixel(width - 1, y), pixel(0, y)) for y in range(height)) / height
    )
    seam_horizontal = (
        sum(_channel_difference(pixel(x, height - 1), pixel(x, 0)) for x in range(width)) / width
    )
    seam = max(seam_vertical, seam_horizontal)

    horizontal_steps = [
        sum(_channel_difference(pixel(x, y), pixel(x + 1, y)) for y in range(height)) / height
        for x in range(width - 1)
    ]
    vertical_steps = [
        sum(_channel_difference(pixel(x, y), pixel(x, y + 1)) for x in range(width)) / width
        for y in range(height - 1)
    ]
    interior = median(horizontal_steps + vertical_steps)
    if interior <= 1e-9:
        # A perfectly flat tile is seamless by definition; guard the division. A finite
        # sentinel keeps run.json serialisable (no Infinity, which is not valid JSON).
        return 0.0 if seam <= 1e-9 else 999.0
    return seam / interior


def seamless_tile(image: Image.Image, ctx: GateContext) -> GateResult:
    limit = ctx.threshold("seam_edge_ratio", 1.5)
    ratio = seam_ratio(image)
    return GateResult(
        "seamless_tile",
        PASS if ratio <= limit else FAIL,
        value=round(ratio, 3),
        threshold=limit,
    )


def normal_map_valid(image: Image.Image, ctx: GateContext) -> GateResult:
    """A normal map, not a depth map: unit vectors, mostly facing the camera.

    Encoding depth directly gives vectors whose length is far from 1 and whose z collapses,
    which is exactly the failure this gate exists to catch (docs/04 §4.3).
    """
    raw = image.convert("RGBA").tobytes()
    total = 0
    unit = 0
    z_sum = 0.0
    zero = 0
    for offset in range(0, len(raw), 4):
        if raw[offset + 3] == 0:
            continue
        total += 1
        if raw[offset] == 0 and raw[offset + 1] == 0 and raw[offset + 2] == 0:
            zero += 1
        nx = raw[offset] / 255.0 * 2.0 - 1.0
        ny = raw[offset + 1] / 255.0 * 2.0 - 1.0
        nz = raw[offset + 2] / 255.0 * 2.0 - 1.0
        length = (nx * nx + ny * ny + nz * nz) ** 0.5
        if abs(length - 1.0) < 0.05:
            unit += 1
        z_sum += nz

    if not total:
        return GateResult("normal_map_valid", SKIPPED, detail="no visible pixels")
    unit_fraction = unit / total
    mean_z = z_sum / total
    ok = zero == 0 and mean_z > 0.5 and unit_fraction > 0.99
    return GateResult(
        "normal_map_valid",
        PASS if ok else FAIL,
        value={"mean_z": round(mean_z, 3), "unit_fraction": round(unit_fraction, 4), "zero": zero},
        threshold={"mean_z": 0.5, "unit_fraction": 0.99},
    )


def aa_suspect(image: Image.Image, ctx: GateContext) -> GateResult:
    """Fraction of near-identical neighbour pairs: a hint that a render was anti-aliased."""
    limit = ctx.threshold("aa_fraction", 0.15)
    source = image.convert("RGB")
    width, height = source.size
    raw = source.tobytes()

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 3
        return raw[offset], raw[offset + 1], raw[offset + 2]

    pairs = 0
    suspect = 0
    for y in range(height):
        for x in range(width):
            if x + 1 < width:
                pairs += 1
                delta = _channel_difference(pixel(x, y), pixel(x + 1, y))
                suspect += 1 if 0 < delta < 3 else 0
            if y + 1 < height:
                pairs += 1
                delta = _channel_difference(pixel(x, y), pixel(x, y + 1))
                suspect += 1 if 0 < delta < 3 else 0
    fraction = suspect / pairs if pairs else 0.0
    return GateResult(
        "aa_suspect",
        PASS if fraction <= limit else FAIL,
        value=round(fraction, 4),
        threshold=limit,
    )


GATES: Mapping[str, Gate] = {
    "dimensions_exact": dimensions_exact,
    "grid_divisible": grid_divisible,
    "frame_count": frame_count,
    "frames_aligned": frames_aligned,
    "palette_conformance": palette_conformance,
    "max_unique_colors": max_unique_colors,
    "alpha_required": alpha_required,
    "binary_alpha": binary_alpha,
    "seamless_tile": seamless_tile,
    "symmetry_9patch": symmetry_9patch,
    "normal_map_valid": normal_map_valid,
    "aa_suspect": aa_suspect,
}

# Applied when a recipe does not name gates. A spec can add, remove, or re-grade any of them.
DEFAULT_GATES: Mapping[AssetKind, tuple[str, ...]] = {
    AssetKind.TERRAIN_TILE: (
        "dimensions_exact",
        "grid_divisible",
        "palette_conformance",
        "max_unique_colors",
        "seamless_tile",
    ),
    AssetKind.CONCEPT: ("max_unique_colors",),
    AssetKind.SPRITE_SHEET: (
        "dimensions_exact",
        "frame_count",
        "frames_aligned",
        "palette_conformance",
        "max_unique_colors",
        "alpha_required",
        "binary_alpha",
    ),
    AssetKind.UI_ELEMENT: (
        "dimensions_exact",
        "palette_conformance",
        "alpha_required",
        "binary_alpha",
        "symmetry_9patch",
    ),
    AssetKind.ICON: (
        "dimensions_exact",
        "palette_conformance",
        "alpha_required",
        "binary_alpha",
    ),
    AssetKind.NORMAL_MAP: ("dimensions_exact", "grid_divisible", "normal_map_valid"),
}


def evaluate(gates: Sequence[str], image: Image.Image, ctx: GateContext) -> list[GateResult]:
    results: list[GateResult] = []
    for name in gates:
        try:
            gate = GATES[name]
        except KeyError:
            raise KeyError(
                f"unknown gate {name!r}; known gates: {', '.join(sorted(GATES))}"
            ) from None
        results.append(gate(image, ctx))
    return results


def severity(gate: str, overrides: Mapping[str, Any]) -> str:
    """`error` (default), `warn` (record but accept), or `off` (never run)."""
    raw = overrides.get(gate, "error")
    text = str(raw).strip().lower()
    return text if text in SEVERITIES else "error"


def failed(results: Sequence[GateResult], overrides: Mapping[str, Any]) -> list[GateResult]:
    return [
        result
        for result in results
        if result.status == FAIL and severity(result.gate, overrides) == "error"
    ]


__all__ = [
    "DEFAULT_GATES",
    "FAIL",
    "GATES",
    "PASS",
    "SEVERITIES",
    "SKIPPED",
    "GateContext",
    "GateResult",
    "aa_suspect",
    "binary_alpha",
    "dimensions_exact",
    "evaluate",
    "failed",
    "frame_bottom_rows",
    "frame_count",
    "frames_aligned",
    "grid_divisible",
    "max_unique_colors",
    "normal_map_valid",
    "palette_conformance",
    "seam_ratio",
    "seamless_tile",
    "severity",
    "symmetry_9patch",
]
