"""Gates (docs/04-pipeline-stages.md §5).

A gate is a named, deterministic check with a threshold that returns `pass`, `fail` or
`skipped` plus the measured value. Two rules make them trustworthy:

* a gate never mutates the artifact it measures;
* a gate that cannot apply records `skipped`, never `pass` (invariant 8).

The measured value is printed on failure, because "seamless_tile failed" is useless and
"seamless_tile 4.31 > 1.5" is a diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from PIL import Image

from ..model import AssetKind
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
    thresholds: Mapping[str, Any] = None  # type: ignore[assignment]
    kind: AssetKind | None = None

    def __post_init__(self) -> None:
        if self.thresholds is None:
            object.__setattr__(self, "thresholds", {})

    def threshold(self, name: str, default: float) -> float:
        value = self.thresholds.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


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
    source = image.convert("RGBA")
    return [
        (r, g, b) for r, g, b, a in source.getdata() if a > 0
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
    return GateResult(
        "alpha_required", PASS if has_alpha else FAIL, value=image.mode
    )


def binary_alpha(image: Image.Image, ctx: GateContext) -> GateResult:
    if image.mode not in ("RGBA", "LA"):
        return GateResult("binary_alpha", SKIPPED, detail="no alpha channel")
    alpha = image.convert("RGBA").getchannel("A")
    partial = sum(1 for value in alpha.getdata() if value not in (0, 255))
    return GateResult("binary_alpha", PASS if partial == 0 else FAIL, value=partial)


def _channel_difference(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return (
        abs(left[0] - right[0]) + abs(left[1] - right[1]) + abs(left[2] - right[2])
    ) / 3.0


def seam_ratio(image: Image.Image) -> float:
    """How much harder the wrap seam is than a typical interior edge.

    The seam pairs the last column with the first (and the last row with the first) — the
    edges a tile repeats against. Dividing by the median interior difference makes the
    result scale-free: ~1.0 means the seam is indistinguishable from the interior, and a
    discontinuity shows up as a large ratio instead of a subjective "looks wrong".
    """
    source = image.convert("RGB")
    width, height = source.size
    pixels = source.load()

    seam_vertical = sum(
        _channel_difference(pixels[width - 1, y], pixels[0, y]) for y in range(height)
    ) / height
    seam_horizontal = sum(
        _channel_difference(pixels[x, height - 1], pixels[x, 0]) for x in range(width)
    ) / width
    seam = max(seam_vertical, seam_horizontal)

    horizontal_steps = [
        sum(_channel_difference(pixels[x, y], pixels[x + 1, y]) for y in range(height))
        / height
        for x in range(width - 1)
    ]
    vertical_steps = [
        sum(_channel_difference(pixels[x, y], pixels[x, y + 1]) for x in range(width))
        / width
        for y in range(height - 1)
    ]
    interior = median(horizontal_steps + vertical_steps)
    if interior <= 1e-9:
        # A perfectly flat tile is seamless by definition; guard the division.
        return 0.0 if seam <= 1e-9 else float("inf")
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


GATES: Mapping[str, Gate] = {
    "dimensions_exact": dimensions_exact,
    "grid_divisible": grid_divisible,
    "palette_conformance": palette_conformance,
    "max_unique_colors": max_unique_colors,
    "alpha_required": alpha_required,
    "binary_alpha": binary_alpha,
    "seamless_tile": seamless_tile,
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
        "palette_conformance",
        "alpha_required",
        "binary_alpha",
    ),
    AssetKind.UI_ELEMENT: (
        "dimensions_exact",
        "palette_conformance",
        "alpha_required",
        "binary_alpha",
    ),
    AssetKind.ICON: (
        "dimensions_exact",
        "palette_conformance",
        "alpha_required",
        "binary_alpha",
    ),
    AssetKind.NORMAL_MAP: ("dimensions_exact", "grid_divisible"),
}


def evaluate(
    gates: Sequence[str], image: Image.Image, ctx: GateContext
) -> list[GateResult]:
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
    "binary_alpha",
    "dimensions_exact",
    "evaluate",
    "failed",
    "grid_divisible",
    "max_unique_colors",
    "palette_conformance",
    "seam_ratio",
    "seamless_tile",
    "severity",
]
