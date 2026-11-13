"""OKLab colour handling for palette locking.

Nearest-colour search happens in OKLab, not RGB, because RGB distance disagrees with
perceived difference: on a dark, desaturated palette (most pixel-art palettes) an RGB
nearest-neighbour collapses several distinct tones onto one. OKLab is the smallest change
that makes "snapped to the palette" also mean "still looks right".

Pure functions, no I/O. Everything here is deterministic: same input, same output, on any
machine, which is what lets `palette_conformance` be a gate rather than a hope.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PIL import Image

RGB = tuple[int, int, int]


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _cbrt(value: float) -> float:
    # math.copysign keeps the sign for the small negative values that a wide gamut produces.
    return math.copysign(abs(value) ** (1.0 / 3.0), value)


def rgb_to_oklab(rgb: RGB) -> tuple[float, float, float]:
    """sRGB 0-255 to OKLab (Björn Ottosson's matrices)."""
    r, g, b = (_srgb_to_linear(channel / 255.0) for channel in rgb)
    lms_l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    lms_m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    lms_s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    cube_l, cube_m, cube_s = _cbrt(lms_l), _cbrt(lms_m), _cbrt(lms_s)
    return (
        0.2104542553 * cube_l + 0.7936177850 * cube_m - 0.0040720468 * cube_s,
        1.9779984951 * cube_l - 2.4285922050 * cube_m + 0.4505937099 * cube_s,
        0.0259040371 * cube_l + 0.7827717662 * cube_m - 0.8086757660 * cube_s,
    )


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2


def _nearest_lab(
    target: tuple[float, float, float], palette_lab: Sequence[tuple[float, float, float]]
) -> int:
    """Lowest index wins ties, so the mapping is stable across runs and platforms."""
    best_index = 0
    best_distance = float("inf")
    for index, candidate in enumerate(palette_lab):
        distance = _distance(target, candidate)
        if distance < best_distance:
            best_index = index
            best_distance = distance
    return best_index


def nearest_palette_index(rgb: RGB, palette_lab: Sequence[tuple[float, float, float]]) -> int:
    return _nearest_lab(rgb_to_oklab(rgb), palette_lab)


def snap_to_palette(image: Image.Image, palette: Sequence[RGB]) -> Image.Image:
    """Map every visible pixel to its nearest palette colour, preserving alpha exactly.

    Fully transparent pixels become (0, 0, 0, 0) rather than a snapped colour: invisible
    pixels must not influence `max_unique_colors` or `palette_conformance`.
    """
    if not palette:
        raise ValueError("cannot snap to an empty palette")

    source = image.convert("RGBA")
    palette_lab = [rgb_to_oklab(colour) for colour in palette]
    cache: dict[RGB, RGB] = {}
    # Iterate the raw buffer rather than getdata(): it is typed, faster, and does not
    # depend on Pillow's serialisation API.
    raw = source.tobytes()
    output: list[tuple[int, int, int, int]] = []

    for offset in range(0, len(raw), 4):
        r, g, b, a = raw[offset], raw[offset + 1], raw[offset + 2], raw[offset + 3]
        if a == 0:
            output.append((0, 0, 0, 0))
            continue
        key = (r, g, b)
        mapped = cache.get(key)
        if mapped is None:
            mapped = palette[nearest_palette_index(key, palette_lab)]
            cache[key] = mapped
        output.append((mapped[0], mapped[1], mapped[2], a))

    result = Image.new("RGBA", source.size)
    result.putdata(output)
    return result


def _visible_counts(image: Image.Image) -> dict[RGB, int]:
    """Colour -> pixel count, ignoring fully transparent pixels: they are not visible art."""
    raw = image.convert("RGBA").tobytes()
    counts: dict[RGB, int] = {}
    for offset in range(0, len(raw), 4):
        if raw[offset + 3]:
            key = (raw[offset], raw[offset + 1], raw[offset + 2])
            counts[key] = counts.get(key, 0) + 1
    return counts


# Concept images can hold hundreds of thousands of unique colours; clustering every one of
# them is slow and pointless, since the tail is one-pixel noise. The cap is applied after the
# total order below, so which colours survive never depends on pixel order.
_MAX_CLUSTER_POINTS = 4096


def extract_colours(image: Image.Image, max_colours: int = 16) -> tuple[RGB, ...]:
    """Sample an authored image down to a palette of at most `max_colours` real colours.

    This is an authoring aid, not part of the asset chain: the pipeline always snaps to the
    palette file, so extraction runs once, by hand, when a look is chosen.

    Deterministic on any machine. Colours are weighted by pixel count and ordered by
    (count desc, RGB asc) rather than by scan order, then clustered in OKLab with Lloyd's
    algorithm seeded from the most frequent colours. Both the seed and the tie-breaks are
    total orders, so the same image always produces the same palette.

    Every returned colour is one that occurs in the image (each cluster is represented by
    its most frequent member), so extraction can never invent a colour the art lacks.
    """
    if max_colours < 1:
        raise ValueError("max_colours must be at least 1")

    counts = _visible_counts(image)
    if not counts:
        raise ValueError("cannot extract a palette from an image with no visible pixels")

    ordered = sorted(counts, key=lambda colour: (-counts[colour], colour))
    if len(ordered) <= max_colours:
        return tuple(ordered)

    limited = ordered[:_MAX_CLUSTER_POINTS]
    points = [(rgb_to_oklab(colour), counts[colour]) for colour in limited]
    centres = [lab for lab, _weight in points[:max_colours]]

    for _ in range(32):
        groups = _assign(points, centres)
        moved = _means(points, groups, centres)
        if moved == centres:
            break
        centres = moved

    # Points keep frequency order, so a group's first member is its most common colour.
    groups = _assign(points, centres)
    chosen: list[RGB] = []
    for members in groups:
        if members and limited[members[0]] not in chosen:
            chosen.append(limited[members[0]])

    # Rounding through real colours can merge two clusters; top up from the tail so a large
    # enough image still yields the number of colours the caller asked for.
    if len(chosen) < max_colours:
        for colour in ordered:
            if len(chosen) >= max_colours:
                break
            if colour not in chosen:
                chosen.append(colour)

    chosen.sort(key=lambda colour: (-counts[colour], colour))
    return tuple(chosen[:max_colours])


def _assign(
    points: Sequence[tuple[tuple[float, float, float], int]],
    centres: Sequence[tuple[float, float, float]],
) -> list[list[int]]:
    groups: list[list[int]] = [[] for _ in centres]
    for index, (lab, _weight) in enumerate(points):
        groups[_nearest_lab(lab, centres)].append(index)
    return groups


def _means(
    points: Sequence[tuple[tuple[float, float, float], int]],
    groups: Sequence[Sequence[int]],
    centres: Sequence[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Pixel-count-weighted mean of each group; an empty group keeps its old centre."""
    moved: list[tuple[float, float, float]] = []
    for group, centre in zip(groups, centres, strict=True):
        total = sum(points[index][1] for index in group)
        if not total:
            moved.append(centre)
            continue
        moved.append(
            (
                sum(points[index][0][0] * points[index][1] for index in group) / total,
                sum(points[index][0][1] * points[index][1] for index in group) / total,
                sum(points[index][0][2] * points[index][1] for index in group) / total,
            )
        )
    return moved


__all__ = [
    "RGB",
    "extract_colours",
    "nearest_palette_index",
    "rgb_to_oklab",
    "snap_to_palette",
]
