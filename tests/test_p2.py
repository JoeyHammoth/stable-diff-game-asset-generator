"""Phase P2: sprite sheets, UI, references, normals, candidates, review.

Each test corresponds to a ticket in docs/06-implementation-plan.md, so a regression here
names the acceptance criterion it broke.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from sdga.backends.comfyui import ComfyUIBackend, load_recipes
from sdga.backends.comfyui.client import ComfyUIClient
from sdga.cli import main, make_backend
from sdga.config import load_config
from sdga.errors import SpecError
from sdga.model import AssetKind
from sdga.pipeline import execute_run
from sdga.planning import build_plan
from sdga.postprocess import (
    OpContext,
    alpha_trim,
    bg_remove,
    cell_boxes,
    center_anchor,
    depth_to_normal,
    despeckle,
    frame_grid,
    ninepatch_margins,
    ninepatch_mirror,
)
from sdga.specs import load_specs
from sdga.validate import GateContext, normal_map_valid, symmetry_9patch
from sdga.validate.gates import frame_bottom_rows, frame_count, frames_aligned

SHEET = OpContext(size=(64, 32), frames=2, layout=(2, 1))


def _sheet(pixels: dict[tuple[int, int], tuple[int, int, int, int]]) -> Image.Image:
    image = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    for position, colour in pixels.items():
        image.putpixel(position, colour)
    return image


def _block(
    image: Image.Image, box: tuple[int, int, int, int], colour: tuple[int, int, int, int]
) -> None:
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            image.putpixel((x, y), colour)


# ------------------------------------------------------------------ T18 sprite sheets


def test_frame_grid_brings_the_render_to_the_declared_grid():
    render = Image.new("RGBA", (512, 64), (255, 0, 0, 255))  # 8 cells of 32, doubled
    grid = OpContext(size=(256, 32), frames=8, layout=(8, 1))

    assert frame_grid(render, grid).size == (256, 32)
    assert len(cell_boxes(grid)) == 8


def test_alpha_trim_moves_content_to_the_cell_origin():
    sheet = _sheet({(9, 9): (1, 2, 3, 255)})
    trimmed = alpha_trim(sheet, SHEET)
    assert trimmed.getpixel((0, 0))[3] == 255
    assert trimmed.getpixel((9, 9))[3] == 0


def test_feet_anchoring_puts_both_frames_on_one_ground_line():
    sheet = _sheet({})
    _block(sheet, (10, 4, 14, 20), (255, 0, 0, 255))  # frame 0: bbox ends at y=19
    _block(sheet, (40, 10, 44, 30), (0, 255, 0, 255))  # frame 1: taller, ends at y=29

    anchored = center_anchor(sheet, SHEET)
    bottoms = frame_bottom_rows(anchored, GateContext(size=(64, 32), frames=2, layout=(2, 1)))

    assert bottoms == [31, 31]
    assert frames_aligned(anchored, GateContext(size=(64, 32), frames=2, layout=(2, 1))).status == (
        "pass"
    )


def test_an_empty_frame_is_an_error_not_a_skip():
    sheet = _sheet({})
    _block(sheet, (2, 2, 6, 6), (255, 0, 0, 255))  # only frame 0 has content

    with pytest.raises(ValueError, match="frame 1 is empty"):
        center_anchor(sheet, SHEET)


def test_frames_aligned_fails_when_one_frame_floats():
    sheet = _sheet({})
    _block(sheet, (10, 4, 14, 20), (255, 0, 0, 255))
    _block(sheet, (40, 4, 44, 12), (0, 255, 0, 255))

    result = frames_aligned(sheet, GateContext(size=(64, 32), frames=2, layout=(2, 1)))
    assert result.status == "fail"
    assert result.value == 8  # bottom rows 19 and 11


def test_frame_count_rejects_a_sheet_that_does_not_match_its_layout():
    good = frame_count(
        Image.new("RGBA", (64, 32)), GateContext(size=(64, 32), frames=2, layout=(2, 1))
    )
    assert good.status == "pass"
    wrong = frame_count(
        Image.new("RGBA", (32, 32)), GateContext(size=(64, 32), frames=2, layout=(2, 1))
    )
    assert wrong.status == "fail"


def test_a_sprite_sheet_run_produces_one_promoted_candidate(project: Path):
    config = load_config(project)
    outcome = execute_run(config, make_backend(config), assets=["char/ranger_walk"])
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    jobs = record["jobs"]

    assert len(jobs) == 4
    assert sum(1 for job in jobs if job["promoted"]) == 1
    assert outcome.superseded == 3
    assert outcome.status == "complete"
    assert {job["candidate"] for job in jobs} == {0, 1, 2, 3}
    assert len({job["seed"] for job in jobs}) == 4

    winner = next(job for job in jobs if job["promoted"])
    assert winner["status"] == "accepted"
    assert winner["post"][0]["width"] == 256  # the whole 8x1 sheet
    assert winner["post"][0]["height"] == 32


# ------------------------------------------------------------------ T19 pose recipes


def test_both_pose_paths_bind_from_the_same_specs(project: Path):
    config = load_config(project)
    registry = load_recipes(config)
    specs = load_specs(config)

    authored = build_plan(config, specs, recipes=registry)
    img2img = build_plan(
        config, specs, recipes=registry, recipe_ids={"sprite_sheet": "sprite_sheet_img2img"}
    )

    sheet = next(r for r in authored.requests if r.asset_id == "char/ranger_walk")
    variant = next(r for r in img2img.requests if r.asset_id == "char/ranger_walk")

    assert sheet.recipe == "sprite_sheet@1"
    assert variant.recipe == "sprite_sheet_img2img@1"
    assert sheet.seed == variant.seed  # same spec, same seed, different mechanism
    assert sheet.graph != variant.graph
    # Both bind the authored pose sheet by role, through the content-addressed handle.
    assert any(
        isinstance(node["inputs"].get("image"), str) and node["inputs"]["image"].startswith("sdga_")
        for node in (sheet.graph or {}).values()
    )
    assert any(
        isinstance(node["inputs"].get("image"), str) and node["inputs"]["image"].startswith("sdga_")
        for node in (variant.graph or {}).values()
    )


def test_an_unknown_recipe_override_names_the_kind(project: Path):
    config = load_config(project)
    with pytest.raises(SpecError, match="no recipe"):
        build_plan(
            config,
            load_specs(config),
            recipes=load_recipes(config),
            recipe_ids={"sprite_sheet": "sprite_sheet_bogus"},
        )


# ------------------------------------------------------------------ T17 references


class _CountingClient(ComfyUIClient):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:9")
        self.uploads: list[str] = []
        self.submitted: list[str] = []

    def upload_image(self, path: Path, name: str | None = None):  # type: ignore[override]
        self.uploads.append(str(name))
        return {"name": name}

    def submit(self, graph, *, prompt_id: str, client_id: str):  # type: ignore[override]
        self.submitted.append(prompt_id)
        return {"prompt_id": prompt_id}


def test_two_assets_sharing_a_reference_upload_it_once(project: Path):
    config = load_config(project)
    plan = build_plan(
        config,
        load_specs(config),
        assets=["terrain/moss_stone"],
        recipes=load_recipes(config),
    )
    request = plan.requests[0]
    duplicate = replace(request, asset_id="terrain/moss_stone_copy", seed=request.seed + 1)

    client = _CountingClient()
    backend = ComfyUIBackend(
        config.backend,
        client=client,
        project_root=config.root,
        tracker_factory=lambda prompt_id: None,
    )
    backend.submit(request)
    backend.submit(duplicate)

    assert client.uploads == [request.refs[0].backend_handle]
    assert len(client.submitted) == 2


def test_upload_handles_are_content_addressed_and_never_hashed(project: Path):
    config = load_config(project)
    request = build_plan(config, load_specs(config)).requests[0]
    handle = request.refs[0].backend_handle

    assert handle is not None and handle.startswith("sdga_")
    assert replace(request, refs=()).request_hash != request.request_hash


# ------------------------------------------------------------------ T20 UI 9-slice


def test_ninepatch_mirror_is_bitwise_symmetric():
    # A block inset by 4px leaves a uniform border, so the margins stay under half the edge.
    image = Image.new("RGBA", (64, 16), (31, 34, 41, 255))
    _block(image, (4, 4, 12, 12), (200, 72, 72, 255))

    mirrored = ninepatch_mirror(image, OpContext(size=(64, 16)))
    horizontal, vertical = ninepatch_margins(mirrored)
    result = symmetry_9patch(mirrored, GateContext(size=(64, 16), kind=AssetKind.UI_ELEMENT))

    assert result.status == "pass", result.to_dict()
    assert horizontal >= 4 and vertical >= 4
    assert 2 * max(horizontal, vertical) < 16


def test_an_asymmetric_button_fails_the_gate():
    image = Image.new("RGBA", (64, 16))
    _block(image, (0, 0, 10, 16), (200, 72, 72, 255))

    assert symmetry_9patch(image, GateContext(size=(64, 16))).status == "fail"


def test_ui_margins_reach_the_pack(project: Path):
    config = load_config(project)
    outcome = execute_run(config, make_backend(config), assets=["ui/button_normal"])
    assert main(["publish", "--project", str(project), "--allow-unreviewed"]) == 0

    pack = sorted((project / "packs").iterdir())[-1]
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    asset = manifest["assets"][0]

    assert asset["engine"]["ui"]["ninepatch"] is True
    assert len(asset["engine"]["ui"]["margins"]) == 2
    assert outcome.accepted == 1


# ------------------------------------------------------------------ T22 normal maps


def _depth_sphere(size: int = 64) -> Image.Image:
    """A hemisphere depth field: bright in the middle, dark at the rim."""
    image = Image.new("RGB", (size, size))
    centre = (size - 1) / 2
    pixels = []
    for y in range(size):
        for x in range(size):
            distance = (((x - centre) ** 2 + (y - centre) ** 2) ** 0.5) / centre
            height = 1.0 if distance >= 1 else (1 - distance * distance) ** 0.5
            pixels.append((int(height * 255),) * 3)
    image.putdata(pixels)
    return image


def test_depth_to_normal_produces_unit_vectors_facing_the_camera():
    normal = depth_to_normal(_depth_sphere(), OpContext(size=(64, 64), strength=2.0))
    result = normal_map_valid(normal, GateContext(size=(64, 64)))

    assert result.status == "pass", result.to_dict()
    assert result.value["mean_z"] > 0.5


def test_a_depth_map_passed_off_as_a_normal_map_fails_the_gate():
    # The regression guard: this is what the source guide's workflow shipped.
    depth = _depth_sphere().convert("RGBA")
    assert normal_map_valid(depth, GateContext(size=(64, 64))).status == "fail"


def test_flip_g_inverts_the_green_channel():
    depth = _depth_sphere()
    flipped = depth_to_normal(depth, OpContext(size=(64, 64), flip_g=True))
    straight = depth_to_normal(depth, OpContext(size=(64, 64), flip_g=False))

    assert straight.tobytes() != flipped.tobytes()
    assert normal_map_valid(flipped, GateContext(size=(64, 64))).status == "pass"


def test_a_normal_map_run_passes_its_gate(project: Path):
    config = load_config(project)
    outcome = execute_run(config, make_backend(config), assets=["terrain/moss_stone_normal"])
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    statuses = {gate["gate"]: gate["status"] for gate in record["jobs"][0]["gates"]}

    assert statuses["normal_map_valid"] == "pass"
    assert outcome.accepted == 1


# ------------------------------------------------------------------ T21 cleanup ops


def test_despeckle_removes_a_one_pixel_island():
    image = Image.new("RGBA", (16, 16))
    _block(image, (2, 2, 10, 10), (255, 0, 0, 255))
    image.putpixel((14, 14), (0, 255, 0, 255))

    cleaned = despeckle(image, OpContext(size=(16, 16), min_area=2))
    assert cleaned.getpixel((14, 14))[3] == 0
    assert cleaned.getpixel((3, 3))[3] == 255


def test_bg_remove_clears_only_the_border_colour():
    image = Image.new("RGBA", (16, 16), (10, 10, 10, 255))
    _block(image, (5, 5, 11, 11), (255, 0, 0, 255))

    cleaned = bg_remove(image, OpContext(size=(16, 16)))
    assert cleaned.getpixel((0, 0))[3] == 0
    assert cleaned.getpixel((6, 6))[:3] == (255, 0, 0)


# ------------------------------------------------------------------ T23 review


def test_review_then_publish_needs_no_override(project: Path):
    config = load_config(project)
    outcome = execute_run(config, make_backend(config), assets=["terrain/moss_stone"])

    assert main(["review", "--project", str(project), "--approve", "--note", "looks right"]) == 0
    assert main(["publish", "--project", str(project)]) == 0

    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    assert record["reviews"][0]["status"] == "approved"
    assert record["reviews"][0]["note"] == "looks right"
    assert record["jobs"][0]["review"]["status"] == "approved"


def test_review_writes_a_contact_sheet_with_reference_and_result(project: Path):
    config = load_config(project)
    outcome = execute_run(config, make_backend(config), assets=["terrain/moss_stone"])
    config_fields = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))

    sheet = (outcome.run_dir / "review.html").read_text(encoding="utf-8")
    assert "terrain/moss_stone" in sheet
    assert "reference" in sheet.lower()
    assert "../../concepts/cleaned/floor.png" in sheet
    assert "../../" in sheet and "post/terrain__moss_stone.png" in sheet
    assert config_fields["reviews"] == []


def test_review_refuses_an_asset_that_is_not_in_the_run(project: Path, capsys):
    config = load_config(project)
    execute_run(config, make_backend(config), assets=["terrain/moss_stone"])

    assert main(["review", "--project", str(project), "--reject", "--asset", "terrain/nope"]) == 1
    assert "not in run" in capsys.readouterr().err


def test_review_decision_needs_exactly_one_of_approve_or_reject(project: Path):
    with pytest.raises(SystemExit) as caught:
        main(["review", "--project", str(project)])
    assert caught.value.code == 2


def test_a_rejected_asset_stays_out_of_the_pack(project: Path, capsys):
    config = load_config(project)
    execute_run(config, make_backend(config), assets=["terrain/moss_stone", "ui/button_normal"])
    assert (
        main(["review", "--project", str(project), "--reject", "--asset", "terrain/moss_stone"])
        == 0
    )

    assert main(["publish", "--project", str(project), "--allow-unreviewed"]) == 0
    assert "1 asset(s)" in capsys.readouterr().out

    pack = sorted((project / "packs").iterdir())[-1]
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert [asset["id"] for asset in manifest["assets"]] == ["ui/button_normal"]
