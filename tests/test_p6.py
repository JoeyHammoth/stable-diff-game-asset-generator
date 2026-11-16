"""P6 · release readiness: retention, pack integrity, and resumed-pack equality.

P5 ended at the engine adapter. P6 closes the operating promises in docs/07 and the
remaining definition-of-done gaps: pruning must never delete a published run's provenance,
validation must check bytes rather than only pixels, and a run interrupted mid-flight must
publish the same assets as one that was never interrupted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _project import PALETTE_COLORS, make_project
from PIL import Image

from sdga.backends.comfyui import load_recipes
from sdga.canonical import hash_file
from sdga.cli import main, make_backend
from sdga.config import load_config
from sdga.pack import publish
from sdga.pipeline import execute_run, verify_pack, verify_run
from sdga.retention import collect_garbage

TILE = "terrain/moss_stone"

KILL_DRIVER = """
import os, sys
from sdga.backends import FakeBackend
from sdga.config import load_config
from sdga.pipeline import execute_run


class KillAfter(FakeBackend):
    def __init__(self):
        super().__init__()
        self.count = 0

    def submit(self, request):
        self.count += 1
        if self.count == 2:
            os._exit(9)
        return super().submit(request)


execute_run(load_config(sys.argv[1]), KillAfter())
"""


def _run(config, assets=(TILE,)):
    return execute_run(config, make_backend(config), assets=list(assets))


def _write_record(run_dir: Path, record: dict) -> None:
    (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def _assets(pack: Path) -> dict[str, dict]:
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    return {asset["id"]: asset for asset in manifest["assets"]}


def _change_one_pixel(path: Path) -> None:
    """Change a visible pixel to another palette colour, so gates can still pass."""
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    current = image.getpixel((min(16, image.width - 1), min(16, image.height - 1)))
    replacement = next(colour for colour in PALETTE_COLORS if colour != current[:3])
    image.putpixel(
        (min(16, image.width - 1), min(16, image.height - 1)),
        (*replacement, 255),
    )
    image.save(path, format="PNG")


# ------------------------------------------------------------------ T39 retention


def test_gc_dry_run_reports_targets_but_deletes_nothing(project: Path):
    config = load_config(project)
    published = _run(config)
    pack = publish(config, published.run_dir, allow_unreviewed=True)
    later = _run(config)
    interrupted = _run(config, assets=["ui/button_normal"])
    record = json.loads((interrupted.run_dir / "run.json").read_text(encoding="utf-8"))
    record["status"] = "running"
    _write_record(interrupted.run_dir, record)

    result = collect_garbage(config, keep_runs=0, dry_run=True)

    target_names = {target.name for target in result.targets}
    assert later.run_id in target_names
    assert published.run_id not in target_names
    assert interrupted.run_id not in target_names
    assert result.deleted == ()
    assert published.run_dir.is_dir()
    assert later.run_dir.is_dir()
    assert interrupted.run_dir.is_dir()
    assert pack.path.is_dir()
    assert {target.reason for target in result.protected} >= {
        f"published by {pack.pack_id}",
        "interrupted; resumable",
    }


def test_gc_deletes_old_runs_but_never_a_published_run(project: Path):
    config = load_config(project)
    published = _run(config)
    pack = publish(config, published.run_dir, allow_unreviewed=True)
    later = _run(config)

    result = collect_garbage(config, keep_runs=0)

    assert [target.name for target in result.deleted] == [later.run_id]
    assert not later.run_dir.exists()
    assert published.run_dir.is_dir()
    assert pack.path.is_dir()
    assert next(published.run_dir.glob("raw/*.png"), None) is not None


def test_gc_prunes_old_packs_and_leaves_unreadable_ones(project: Path):
    config = load_config(project)
    outcome = _run(config)
    packs = [publish(config, outcome.run_dir, allow_unreviewed=True).path for _ in range(3)]
    broken = project / "packs" / "broken"
    broken.mkdir()
    (broken / "pack.json").write_text("{ not json", encoding="utf-8")

    result = collect_garbage(config, keep_runs=10, keep_packs=1)

    remaining = {path.name for path in (project / "packs").iterdir()}
    assert packs[-1].name in remaining
    assert packs[0].name not in remaining
    assert broken.name in remaining
    assert any(
        target.kind == "packs"
        and target.name == "broken"
        and target.reason == "unreadable pack.json"
        for target in result.protected
    )


def test_gc_opt_ins_remove_stale_runs_and_unreadable_packs(project: Path):
    config = load_config(project)
    stale = project / "runs" / "20260101-000000-stale"
    stale.mkdir(parents=True)
    (stale / "raw").mkdir()
    (stale / "raw" / "partial.png").write_bytes(b"partial")
    stale_pack = project / "packs" / "20260101-000000-stale"
    stale_pack.mkdir(parents=True)
    (stale_pack / "assets").mkdir()
    broken = project / "packs" / "broken"
    broken.mkdir(parents=True)
    (broken / "pack.json").write_text("{ not json", encoding="utf-8")

    result = collect_garbage(
        config, keep_runs=10, keep_packs=10, prune_stale=True, force_unreadable=True
    )

    assert {target.name for target in result.deleted} == {
        stale.name,
        stale_pack.name,
        broken.name,
    }
    assert not stale.exists()
    assert not stale_pack.exists()
    assert not broken.exists()


def test_gc_opt_ins_are_required_to_remove_unreadable_artifacts(project: Path):
    config = load_config(project)
    stale = project / "runs" / "20260101-000000-stale"
    stale.mkdir(parents=True)
    stale_pack = project / "packs" / "20260101-000000-stale"
    stale_pack.mkdir(parents=True)
    broken = project / "packs" / "broken"
    broken.mkdir(parents=True)
    (broken / "pack.json").write_text("{ not json", encoding="utf-8")

    result = collect_garbage(config, keep_runs=10, keep_packs=10)

    assert result.deleted == ()
    assert stale.exists() and stale_pack.exists() and broken.exists()
    reasons = {target.reason for target in result.protected}
    assert "stale; pass --prune-stale to remove" in reasons
    assert "unreadable pack.json" in reasons


def test_gc_cli_exposes_the_opt_in_flags(project: Path, capsys):
    stale = project / "runs" / "20260101-000000-stale"
    stale.mkdir(parents=True)
    broken = project / "packs" / "broken"
    broken.mkdir(parents=True)
    (broken / "pack.json").write_text("{ not json", encoding="utf-8")

    assert (
        main(
            [
                "gc",
                "--project",
                str(project),
                "--keep-runs",
                "10",
                "--keep-packs",
                "10",
                "--prune-stale",
                "--force-unreadable",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert {target["name"] for target in payload["targets"]} == {stale.name, broken.name}
    assert payload["deleted"] == []
    assert stale.exists() and broken.exists()


def test_gc_cli_json_reports_the_plan(project: Path, capsys):
    config = load_config(project)
    _run(config)
    _run(config)

    assert main(["gc", "--project", str(project), "--keep-runs", "1", "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == 1
    assert payload["dry_run"] is True
    assert len(payload["targets"]) == 1
    assert payload["deleted"] == []


def test_gc_cli_rejects_a_bad_retention_value(project: Path):
    with pytest.raises(SystemExit) as caught:
        main(["gc", "--project", str(project), "--keep-packs", "many"])
    assert caught.value.code == 2

    with pytest.raises(SystemExit) as caught:
        main(["gc", "--project", str(project), "--keep-runs", "-1"])
    assert caught.value.code == 2


# --------------------------------------------------------------- T40 integrity


def test_validate_detects_a_tampered_pack_even_when_gates_still_pass(project: Path):
    config = load_config(project)
    outcome = _run(config)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)
    target = result.path / "assets" / "terrain" / "moss_stone.png"
    before = hash_file(target)

    _change_one_pixel(target)
    assert hash_file(target) != before

    ok, rows = verify_pack(config, result.path, load_recipes(config))

    assert not ok
    assert any(
        row["status"] == "fail" and row["gate"] in {"manifest", "asset_file"} for row in rows
    ), rows


def test_validate_detects_a_tampered_run_artifact(project: Path):
    config = load_config(project)
    outcome = _run(config)
    record = json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))
    target = config.root / record["jobs"][0]["post"][0]["path"]
    _change_one_pixel(target)

    ok, rows = verify_run(config, outcome.run_dir, load_recipes(config))

    assert not ok
    assert any(row["gate"] == "artifact" and row["status"] == "fail" for row in rows), rows


def test_validate_rejects_an_extra_file_and_a_missing_file(project: Path):
    config = load_config(project)
    outcome = _run(config)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)
    recipes = load_recipes(config)

    (result.path / "unexpected.txt").write_text("not in the manifest", encoding="utf-8")
    ok, rows = verify_pack(config, result.path, recipes)
    assert not ok
    assert any("not listed" in (row.get("detail") or "") for row in rows), rows

    (result.path / "unexpected.txt").unlink()
    (result.path / "assets" / "terrain" / "moss_stone.png").unlink()
    ok, rows = verify_pack(config, result.path, recipes)
    assert not ok
    assert any(row["gate"] in {"manifest", "asset_file"} for row in rows), rows


def test_validate_requires_provenance_on_each_asset(project: Path):
    config = load_config(project)
    outcome = _run(config)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)
    manifest = json.loads((result.path / "pack.json").read_text(encoding="utf-8"))
    del manifest["assets"][0]["provenance"]
    (result.path / "pack.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    ok, rows = verify_pack(config, result.path, load_recipes(config))

    assert not ok
    assert any(row["gate"] == "provenance" for row in rows), rows


# ------------------------------------------------------- T41 resumed-pack equality


def test_a_resumed_run_publishes_the_same_assets_as_an_uninterrupted_run(tmp_path: Path):
    steady = make_project(tmp_path / "steady")
    interrupted = make_project(tmp_path / "interrupted")

    steady_config = load_config(steady)
    steady_outcome = execute_run(steady_config, make_backend(steady_config))
    steady_pack = publish(steady_config, steady_outcome.run_dir, allow_unreviewed=True)

    driver = tmp_path / "kill_mid_run.py"
    driver.write_text(KILL_DRIVER, encoding="utf-8")
    killed = subprocess.run(
        [sys.executable, str(driver), str(interrupted)], capture_output=True, text=True
    )
    assert killed.returncode == 9, killed.stderr

    interrupted_config = load_config(interrupted)
    resumed = execute_run(interrupted_config, make_backend(interrupted_config), resume="latest")
    resumed_pack = publish(interrupted_config, resumed.run_dir, allow_unreviewed=True)

    assert resumed.status == "complete"
    steady_assets = _assets(steady_pack.path)
    resumed_assets = _assets(resumed_pack.path)
    assert set(resumed_assets) == set(steady_assets)
    for asset_id, steady_asset in steady_assets.items():
        resumed_asset = resumed_assets[asset_id]
        assert resumed_asset["files"][0]["sha256"] == steady_asset["files"][0]["sha256"]
        assert resumed_asset["kind"] == steady_asset["kind"]
        assert resumed_asset.get("engine") == steady_asset.get("engine")
        assert resumed_asset["checks"] == steady_asset["checks"]
