"""Builders for throwaway projects used by the test suite.

Every test gets a real directory tree on disk rather than mocks: the loaders are the thing
under test, and they only mean anything against real files.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]

PALETTE_COLORS: tuple[tuple[int, int, int], ...] = (
    (31, 34, 41),
    (45, 52, 60),
    (58, 99, 64),
    (74, 124, 74),
    (120, 164, 96),
    (198, 214, 163),
    (138, 96, 64),
    (176, 132, 88),
    (214, 180, 128),
    (96, 64, 96),
    (148, 104, 148),
    (200, 152, 200),
    (64, 96, 148),
    (96, 140, 200),
    (200, 72, 72),
    (240, 168, 72),
)

PALETTE_GPL = "GIMP Palette\nName: Test 16\nColumns: 8\n#\n" + "".join(
    f"{r:3d} {g:3d} {b:3d}\tcolor{index}\n" for index, (r, g, b) in enumerate(PALETTE_COLORS)
)

TOML = """\
schema = 1

[project]
name = "testgame"
root = "."
asset_globs = ["assets/**/*.yaml"]
runs_dir = "runs"
packs_dir = "packs"
cache_dir = ".sdga/cache"

[style]
name = "testgame"
trigger_token = "TestGameStyle"
grid = 32
generation_size = [512, 512]
palette = "palettes/test.gpl"
palette_colors = 16
checkpoint = "sd_v1-5.safetensors"
seed_policy = "derived"
positive_anchors = ["TestGameStyle", "flat colours", "clean pixel art"]
negative_anchors = ["photorealistic", "blurry", "gradient"]

[[style.loras]]
name = "testgame_style.safetensors"
strength_model = 0.85
strength_clip = 0.85

[backend]
kind = "fake"

[pack]
id_template = "{project}-{date}-{seq}"
require_review = true
include_raw = false

[gates]
on_fail = "reject"

[gates.thresholds]
max_unique_colors = 16
"""

DEFAULT_ASSETS = """\
schema: 1
defaults:
  params: { steps: 25, cfg: 7.0, sampler: euler_ancestral, scheduler: karras }

assets:
  - id: terrain/moss_stone
    kind: terrain_tile
    prompt: seamless mossy cobblestone floor, top-down tile
    size: [32, 32]
    references:
      style_anchor: concepts/cleaned/floor.png
    params: { denoise: 1.0 }

  - id: char/ranger_walk
    kind: sprite_sheet
    prompt: forest ranger walking cycle, side view, transparent background
    size: [32, 32]
    frames: 8
    layout: { cols: 8, rows: 1 }
    references:
      style_anchor: concepts/cleaned/ranger.png
      pose: style/skeletons/walk_8.png
    params: { steps: 28, cfg: 7.5, controlnet: controlnet_openpose.safetensors, controlnet_strength: 0.8 }

  - id: ui/button_normal
    kind: ui_element
    prompt: rounded stone button, empty centre, no text
    size: [64, 16]
    references:
      wireframe: style/wireframes/button.png

  - id: terrain/moss_stone_normal
    kind: normal_map
    depends_on: [terrain/moss_stone]
    size: [32, 32]
    params: { height_strength: 2.0, flip_g: false }
"""

REFS: dict[str, tuple[tuple[int, int], tuple[tuple[int, int, int, int], ...]]] = {
    "concepts/cleaned/floor.png": ((64, 64), ((31, 34, 41, 255), (58, 99, 64, 255))),
    "concepts/cleaned/ranger.png": ((64, 64), ((31, 34, 41, 255), (198, 214, 163, 255))),
    "style/skeletons/walk_8.png": ((256, 32), ((255, 255, 255, 255), (0, 0, 0, 0))),
    "style/wireframes/button.png": ((64, 16), ((255, 255, 255, 255), (0, 0, 0, 255))),
}


def write_png(path: Path, size: tuple[int, int], colors: tuple[tuple[int, ...], ...]) -> None:
    width, height = size
    image = Image.new("RGBA", size)
    image.putdata(
        [colors[((x // 4) + (y // 4)) % len(colors)] for y in range(height) for x in range(width)]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def install_recipes(root: Path) -> None:
    """Copy the repository's real recipes in, so tests exercise the shipped data."""
    source = REPO_ROOT / "recipes"
    if not source.is_dir():
        return
    for path in sorted(source.glob("*.yaml")):
        graph = path.parent / path.stem / "graph"
        target = root / "recipes" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        referenced = path.parent / _graph_name(path)
        if referenced.is_file():
            (root / "recipes" / referenced.name).write_text(
                referenced.read_text(encoding="utf-8"), encoding="utf-8"
            )
    del graph


def _graph_name(recipe_path: Path) -> str:
    for line in recipe_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("graph:"):
            return line.split(":", 1)[1].strip()
    return ""


def make_project(
    root: Path,
    *,
    toml: str | None = None,
    assets: dict[str, str] | None = None,
    with_recipes: bool = True,
) -> Path:
    root = Path(root)
    (root / "palettes").mkdir(parents=True, exist_ok=True)
    (root / "palettes" / "test.gpl").write_text(PALETTE_GPL, encoding="utf-8")

    if with_recipes:
        install_recipes(root)

    for relative, (size, colors) in REFS.items():
        write_png(root / relative, size, colors)

    (root / "sdga.toml").write_text(toml if toml is not None else TOML, encoding="utf-8")

    files = assets if assets is not None else {"assets/default.yaml": DEFAULT_ASSETS}
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root
