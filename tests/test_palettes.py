from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from sdga.cli import main
from sdga.config import read_palette
from sdga.errors import ConfigError
from sdga.palettes import extract_palette, write_palette
from sdga.postprocess import extract_colours


def _image(size: tuple[int, int], pixels: list[tuple[int, ...]]) -> Image.Image:
    image = Image.new("RGBA", size)
    image.putdata(pixels)
    return image


def test_a_flat_image_keeps_its_colours_most_used_first():
    image = _image((3, 1), [(9, 9, 9, 255), (1, 2, 3, 255), (1, 2, 3, 255)])
    assert extract_colours(image, 16) == ((1, 2, 3), (9, 9, 9))


def test_extraction_respects_the_budget_and_invents_nothing():
    pixels = [((x * 7) % 256, (x * 13) % 256, (x * 29) % 256, 255) for x in range(40)]
    palette = extract_colours(_image((40, 1), pixels), 8)

    assert len(palette) == 8
    assert len(set(palette)) == 8
    assert set(palette) <= {pixel[:3] for pixel in pixels}


def test_transparent_pixels_are_not_colours():
    image = _image((3, 1), [(0, 0, 0, 0), (0, 0, 0, 0), (200, 1, 2, 255)])
    assert extract_colours(image, 16) == ((200, 1, 2),)


def test_an_image_with_no_visible_pixels_is_rejected():
    with pytest.raises(ValueError, match="no visible pixels"):
        extract_colours(Image.new("RGBA", (2, 2), (0, 0, 0, 0)), 16)


def test_extraction_does_not_depend_on_pixel_order():
    """Groups are weighted by pixel count, so a mirrored image must give the same palette."""
    pixels = [((x * 11) % 256, (x * 37) % 256, (x * 53) % 256, 255) for x in range(64)]
    forward = _image((64, 1), pixels)
    backward = _image((64, 1), list(reversed(pixels)))

    assert extract_colours(forward, 6) == extract_colours(backward, 6)


def test_extraction_is_repeatable():
    pixels = [((x * 5) % 256, (x * 17) % 256, (x * 23) % 256, 255) for x in range(48)]
    image = _image((48, 1), pixels)

    assert extract_colours(image, 5) == extract_colours(image, 5)


def test_a_written_gpl_reads_back_identically(tmp_path: Path):
    colours = ((1, 2, 3), (240, 168, 72), (0, 0, 0))
    path = write_palette(tmp_path / "p.gpl", colours, name="Sample", source="floor.png")

    assert path.is_file()
    assert read_palette(path, "[style]") == colours


def test_a_written_png_reads_back_identically(tmp_path: Path):
    colours = tuple((index * 16, 255 - index * 16, index) for index in range(16))
    path = write_palette(tmp_path / "p.png", colours, name="Sample", source="floor.png")

    with Image.open(path) as image:
        assert image.size == (8, 2)  # the 8x2 swatch grid the example project ships
        assert "sdga palette extract" in (image.info.get("Comment") or "")
    assert read_palette(path, "[style]") == colours


def test_an_unsupported_output_format_is_rejected(tmp_path: Path):
    with pytest.raises(ConfigError, match="unsupported palette format"):
        write_palette(tmp_path / "p.bmp", ((1, 2, 3),))


def test_an_empty_palette_is_refused(tmp_path: Path):
    with pytest.raises(ConfigError, match="empty palette"):
        write_palette(tmp_path / "p.gpl", ())


def test_palette_extract_writes_the_project_palette(project: Path, capsys):
    image = project / "concepts" / "cleaned" / "floor.png"
    assert main(["palette", "extract", str(image), "--project", str(project), "--force"]) == 0

    out = capsys.readouterr().out
    assert read_palette(project / "palettes" / "test.gpl", "[style]") == (
        (31, 34, 41),
        (58, 99, 64),
    )
    # The default colour count comes from the config, which declares more than this image has.
    assert "palette_colors is 16" in out
    assert "seeds change" in out


def test_palette_extract_refuses_to_clobber_a_palette(project: Path, capsys):
    image = project / "concepts" / "cleaned" / "floor.png"
    before = (project / "palettes" / "test.gpl").read_bytes()

    assert main(["palette", "extract", str(image), "--project", str(project)]) == 2

    assert "--force" in capsys.readouterr().err
    assert (project / "palettes" / "test.gpl").read_bytes() == before


def test_palette_extract_writes_png_when_asked(project: Path, tmp_path: Path):
    image = project / "concepts" / "cleaned" / "ranger.png"
    target = tmp_path / "out" / "ranger.png"

    assert (
        main(
            [
                "palette",
                "extract",
                str(image),
                "--project",
                str(project),
                "--out",
                str(target),
                "--colors",
                "2",
            ]
        )
        == 0
    )
    assert read_palette(target, "[style]") == ((31, 34, 41), (198, 214, 163))


def test_palette_extract_rejects_a_missing_image(project: Path, capsys):
    assert main(["palette", "extract", "nope.png", "--project", str(project)]) == 2
    assert "no image at nope.png" in capsys.readouterr().err


def test_extract_palette_reports_an_unreadable_image(tmp_path: Path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")

    with pytest.raises(ConfigError, match="cannot read image"):
        extract_palette(broken, 4)
