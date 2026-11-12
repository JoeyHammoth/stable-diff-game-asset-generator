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
from typing import Sequence

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
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _distance(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> float:
    return (
        (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2
    )


def nearest_palette_index(
    rgb: RGB, palette_lab: Sequence[tuple[float, float, float]]
) -> int:
    """Lowest index wins ties, so the mapping is stable across runs and platforms."""
    target = rgb_to_oklab(rgb)
    best_index = 0
    best_distance = float("inf")
    for index, candidate in enumerate(palette_lab):
        distance = _distance(target, candidate)
        if distance < best_distance:
            best_index = index
            best_distance = distance
    return best_index


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
    output: list[tuple[int, int, int, int]] = []

    for r, g, b, a in source.getdata():
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


__all__ = ["RGB", "nearest_palette_index", "rgb_to_oklab", "snap_to_palette"]
