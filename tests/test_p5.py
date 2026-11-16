"""Phase P5: the Godot adapter (docs/06-implementation-plan.md, T36-T38).

The adapter is pure data: a pack in, JSON out, no Godot process. These tests pin the four
artifacts and the properties that make the output usable: filtering off for pixel art, four
ninepatch edges from two margins, every sprite frame listed, loop points in both seconds and
frames, and byte-identical output across runs.

The full pipeline path (fake backend -> pack -> adapter) is exercised by the P5 CI gate; these
tests use a hand-built pack so a broken hint is easy to reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _project import TOML as BASE_TOML
from _project import make_project

from sdga.adapters import adapt_godot, build_godot_bundle
from sdga.canonical import hash_file, pretty_json
from sdga.cli import main
from sdga.errors import EXIT_FAILURE, SdgaError

PACK_ID = "demo-2026-01-01-01"
YAML_HEADER = "schema: 1\nassets:\n"


def _write(root: Path, rel: str, data: bytes) -> dict[str, object]:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": rel, "sha256": hash_file(target), "bytes": len(data)}


def _fixture_pack(tmp_path: Path) -> Path:
    root = tmp_path / "pack"
    terrain = _write(root, "assets/terrain/moss_stone.png", b"png-terrain")
    sprite = _write(root, "assets/char/hero_walk.png", b"png-sprite")
    ui = _write(root, "assets/ui/button_normal.png", b"png-ui")
    concept = _write(root, "assets/concept/hero.png", b"png-concept")
    music = _write(root, "assets/music/title.wav", b"wav-music")
    sfx = _write(root, "assets/sfx/click.wav", b"wav-sfx")

    manifest = {
        "schema": 1,
        "pack_id": PACK_ID,
        "created": "2026-01-01T00:00:00Z",
        "style": {"name": "demo"},
        "generator": {"tool": "sdga", "version": "0.1.0"},
        "assets": [
            {
                "id": "terrain/moss_stone",
                "kind": "terrain_tile",
                "files": [terrain],
                "engine": {"tile": {"size": [32, 32], "seamless": True}},
            },
            {
                "id": "char/hero_walk",
                "kind": "sprite_sheet",
                "files": [sprite],
                "engine": {"sprite": {"frame_size": [32, 32], "cols": 4, "rows": 1, "frames": 4}},
            },
            {
                "id": "ui/button_normal",
                "kind": "ui_element",
                "files": [ui],
                "engine": {"ui": {"margins": [2, 3], "ninepatch": True}},
            },
            {"id": "concept/hero", "kind": "concept", "files": [concept], "engine": {}},
            {
                "id": "music/title",
                "kind": "music_track",
                "files": [{**music, "sample_rate": 8000, "duration_s": 2.0}],
                "engine": {
                    "music": {"loop": {"start_s": 0.0, "end_s": 2.0, "crossfade_s": 0.25}},
                    "audio": {"bus": "Music", "sample_rate": 8000},
                },
            },
            {
                "id": "sfx/click",
                "kind": "sfx",
                "files": [{**sfx, "sample_rate": 8000, "duration_s": 0.3}],
                "engine": {"sfx": {"duration_s": 0.3, "one_shot": True}, "audio": {"bus": "SFX"}},
            },
        ],
    }
    (root / "pack.json").write_text(pretty_json(manifest), encoding="utf-8")
    return root


def _read(out: Path, name: str) -> dict:
    return json.loads((out / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- T36


def test_import_hints_disable_filtering_and_compress_by_kind(tmp_path: Path):
    out = tmp_path / "out"
    adapt_godot(_fixture_pack(tmp_path), out)

    hints = _read(out, "godot_import.json")["files"]
    terrain = hints["assets/terrain/moss_stone.png"]
    assert terrain == {
        "importer": "texture",
        "filter": False,
        "mipmaps": False,
        "compression": "lossless",
    }
    assert hints["assets/concept/hero.png"]["compression"] == "vram_compressed"
    assert hints["assets/char/hero_walk.png"]["compression"] == "lossless"


def test_ninepatch_turns_two_margins_into_four_edges(tmp_path: Path):
    out = tmp_path / "out"
    adapt_godot(_fixture_pack(tmp_path), out)

    assets = _read(out, "ninepatch.json")["assets"]
    button = assets["ui/button_normal"]
    assert button["margins"] == {"left": 2, "top": 3, "right": 2, "bottom": 3}
    assert button["path"] == "assets/ui/button_normal.png"
    # A terrain tile is not a ninepatch, even though it is an image.
    assert "terrain/moss_stone" not in assets


def test_sprite_frames_lists_every_frame_at_the_adapter_fps(tmp_path: Path):
    out = tmp_path / "out"
    adapt_godot(_fixture_pack(tmp_path), out, fps=12)

    document = _read(out, "sprite_frames.json")
    assert document["fps"] == 12
    sprite = document["sprites"]["char/hero_walk"]
    assert sprite["frame_size"] == [32, 32]
    assert (sprite["cols"], sprite["rows"], sprite["frames"]) == (4, 1, 4)
    animation = sprite["animations"]["default"]
    assert animation["frames"] == [0, 1, 2, 3]
    assert animation["speed"] == 12
    assert animation["loop"] is True


def test_audio_imports_carry_loop_points_in_seconds_and_frames(tmp_path: Path):
    out = tmp_path / "out"
    adapt_godot(_fixture_pack(tmp_path), out)

    hints = _read(out, "godot_import.json")["files"]
    music = hints["assets/music/title.wav"]
    assert music["importer"] == "wav"
    assert music["loop_mode"] == 1
    assert music["loop_begin_frame"] == 0
    assert music["loop_end_frame"] == 2 * 8000
    assert hints["assets/sfx/click.wav"]["loop_mode"] == 0


def test_audio_buses_name_each_asset_and_expose_the_loop(tmp_path: Path):
    out = tmp_path / "out"
    adapt_godot(_fixture_pack(tmp_path), out)

    document = _read(out, "audio_buses.json")
    assert document["buses"] == [
        {"name": "Music", "volume_db": 0.0, "send": "Master"},
        {"name": "SFX", "volume_db": 0.0, "send": "Master"},
    ]
    assert document["assets"]["music/title"] == {
        "path": "assets/music/title.wav",
        "bus": "Music",
        "loop": {"begin_s": 0.0, "end_s": 2.0},
    }
    assert document["assets"]["sfx/click"]["one_shot"] is True


def test_the_bundle_validates_its_own_output(tmp_path: Path):
    pack = json.loads((_fixture_pack(tmp_path) / "pack.json").read_text(encoding="utf-8"))
    assert set(build_godot_bundle(pack)) == {
        "godot_import.json",
        "ninepatch.json",
        "sprite_frames.json",
        "audio_buses.json",
    }

    broken = json.loads(json.dumps(pack))
    broken["assets"][1]["engine"]["sprite"]["cols"] = 2  # 2x1 cannot hold 4 frames
    with pytest.raises(SdgaError, match="cannot hold"):
        build_godot_bundle(broken)


def test_adapter_output_is_deterministic_and_does_not_touch_the_pack(tmp_path: Path):
    pack = _fixture_pack(tmp_path)
    before = {
        path.relative_to(pack).as_posix(): hash_file(path)
        for path in pack.rglob("*")
        if path.is_file()
    }

    first, second = tmp_path / "a", tmp_path / "b"
    adapt_godot(pack, first)
    adapt_godot(pack, second)

    for name in sorted(path.name for path in first.iterdir()):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    after = {
        path.relative_to(pack).as_posix(): hash_file(path)
        for path in pack.rglob("*")
        if path.is_file()
    }
    assert after == before

    manifest = _read(first, "manifest.json")
    assert manifest["pack_id"] == PACK_ID
    assert set(manifest["files"]) == {
        "audio_buses.json",
        "godot_import.json",
        "ninepatch.json",
        "sprite_frames.json",
    }
    for name, digest in manifest["files"].items():
        assert digest == hash_file(first / name)


def test_a_malformed_hint_is_an_error_not_a_guess(tmp_path: Path):
    pack = _fixture_pack(tmp_path)
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    manifest["assets"][2]["engine"]["ui"]["margins"] = [4]
    (pack / "pack.json").write_text(pretty_json(manifest), encoding="utf-8")

    with pytest.raises(SdgaError, match="ui.margins"):
        adapt_godot(pack, tmp_path / "out")


# --------------------------------------------------------------------------- CLI


def _project(tmp_path: Path) -> Path:
    return make_project(
        tmp_path / "project",
        toml=BASE_TOML,
        assets={
            "assets/terrain.yaml": YAML_HEADER
            + "  - id: terrain/moss_stone\n"
            + "    kind: terrain_tile\n"
            + "    prompt: mossy stone\n"
            + "    size: [32, 32]\n"
        },
        with_recipes=False,
    )


def test_cli_adapts_a_pack_to_the_default_directory(tmp_path: Path, capsys):
    project = _project(tmp_path)
    pack = _fixture_pack(tmp_path)

    code = main(["adapt", "--project", str(project), "--pack", str(pack)])

    assert code == 0
    target = project / "adapters" / PACK_ID / "godot"
    assert (target / "manifest.json").is_file()
    assert (target / "sprite_frames.json").is_file()
    assert "adapted demo-2026-01-01-01 for godot: 5 file(s)" in capsys.readouterr().out


def test_cli_reports_a_missing_pack_without_a_traceback(tmp_path: Path, capsys):
    project = _project(tmp_path)
    code = main(["adapt", "--project", str(project), "--pack", str(tmp_path / "absent")])

    assert code == EXIT_FAILURE
    assert "no pack.json" in capsys.readouterr().err


def test_cli_rejects_an_unknown_engine(tmp_path: Path):
    project = _project(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["adapt", "--project", str(project), "--engine", "unity"])
    assert caught.value.code == 2
