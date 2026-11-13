from __future__ import annotations

import pytest
from PIL import Image

from sdga.postprocess import (
    OpContext,
    alpha_hard,
    apply_chain,
    downscale_box,
    downscale_nearest,
    pad_to_grid,
    snap_to_palette,
)

PALETTE = ((0, 0, 0), (255, 255, 255), (255, 0, 0))


def _image(size: tuple[int, int], pixels: list[tuple[int, ...]]) -> Image.Image:
    image = Image.new("RGBA", size)
    image.putdata(pixels)
    return image


def _solid(size: tuple[int, int], colour: tuple[int, int, int, int] = (10, 10, 10, 255)):
    return Image.new("RGBA", size, colour)


def _pixels(image: Image.Image) -> list[tuple[int, ...]]:
    """RGBA tuples in scan order, read from the raw buffer (getdata() is deprecated)."""
    raw = image.convert("RGBA").tobytes()
    return [tuple(raw[offset : offset + 4]) for offset in range(0, len(raw), 4)]


def test_downscale_box_lands_on_the_target_size():
    assert downscale_box(_solid((512, 512)), OpContext(size=(32, 32))).size == (32, 32)


def test_downscale_nearest_keeps_hard_edges():
    image = Image.new("RGB", (8, 8), (0, 0, 0))
    for x in range(4, 8):
        for y in range(8):
            image.putpixel((x, y), (255, 255, 255))
    out = downscale_nearest(image, OpContext(size=(2, 2)))
    assert {out.convert("RGB").getpixel((0, 0)), out.convert("RGB").getpixel((1, 1))} == {
        (0, 0, 0),
        (255, 255, 255),
    }


def test_palette_snap_emits_only_palette_colours():
    out = snap_to_palette(_image((2, 1), [(10, 10, 10, 255), (240, 10, 10, 255)]), PALETTE)
    tinted = {pixel[:3] for pixel in _pixels(out)}
    assert tinted <= set(PALETTE)


def test_palette_snap_is_idempotent():
    source = _image(
        (4, 1), [(10, 10, 10, 255), (240, 10, 10, 255), (5, 200, 5, 255), (255, 255, 255, 255)]
    )
    once = snap_to_palette(source, PALETTE)
    twice = snap_to_palette(once, PALETTE)
    assert _pixels(once) == _pixels(twice)


def test_palette_snap_preserves_alpha():
    out = snap_to_palette(_image((2, 1), [(10, 10, 10, 0), (10, 10, 10, 255)]), PALETTE)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((1, 0))[3] == 255


def test_palette_snap_leaves_transparent_pixels_colourless():
    out = snap_to_palette(_image((1, 1), [(200, 0, 0, 0)]), PALETTE)
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)


def test_alpha_hard_thresholds_at_128():
    out = alpha_hard(
        _image((3, 1), [(0, 0, 0, 127), (0, 0, 0, 128), (0, 0, 0, 200)]), OpContext(size=(3, 1))
    )
    assert [pixel[3] for pixel in _pixels(out)] == [0, 255, 255]


def test_pad_to_grid_pads_with_transparency():
    out = pad_to_grid(_solid((33, 32)), OpContext(size=(33, 32), grid=32))
    assert out.size == (64, 32)
    assert out.getpixel((40, 0))[3] == 0


def test_pad_to_grid_is_a_no_op_when_already_aligned():
    out = pad_to_grid(_solid((32, 32)), OpContext(size=(32, 32), grid=32))
    assert out.size == (32, 32)


def test_a_chain_runs_in_declared_order():
    image = Image.new("RGB", (512, 512), (10, 10, 10))
    context = OpContext(size=(32, 32), palette=PALETTE, grid=32)
    out = apply_chain(
        image, ["downscale_box", "palette_snap", "alpha_hard", "pad_to_grid"], context
    )
    assert out.size == (32, 32)
    assert {pixel[:3] for pixel in _pixels(out)} <= set(PALETTE)


def test_chain_order_is_observable():
    """Downscaling after snapping leaves a blended, off-palette pixel.

    This is exactly why the recipe declares [downscale_box, palette_snap] in that order:
    averaging happens first, so the snap has the final word on colour.
    """
    image = Image.new("RGB", (4, 4))
    image.putdata([(0, 0, 0) if x < 2 else (255, 255, 255) for y in range(4) for x in range(4)])
    context = OpContext(size=(1, 1), palette=((0, 0, 0), (255, 255, 255)), grid=1)

    snapped_last = apply_chain(image, ["downscale_box", "palette_snap"], context)
    snapped_first = apply_chain(image, ["palette_snap", "downscale_box"], context)

    assert snapped_last.getpixel((0, 0))[:3] in {(0, 0, 0), (255, 255, 255)}
    assert snapped_first.getpixel((0, 0))[:3] not in {(0, 0, 0), (255, 255, 255)}


def test_an_unknown_op_is_an_error():
    with pytest.raises(KeyError):
        apply_chain(_solid((1, 1)), ["sharpen"], OpContext(size=(1, 1)))
