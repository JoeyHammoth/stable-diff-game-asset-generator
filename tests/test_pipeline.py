from __future__ import annotations

import json
from pathlib import Path

import pytest
from _project import TOML, make_project
from PIL import Image

from sdga.backends.comfyui import load_recipes
from sdga.cli import main, make_backend
from sdga.config import load_config
from sdga.errors import SdgaError, SpecError
from sdga.pack import publish
from sdga.pipeline import execute_run, verify_pack, verify_run


def _run_one(config, assets=("terrain/moss_stone",)):
    return execute_run(config, make_backend(config), assets=list(assets))


def _record(outcome):
    return json.loads((outcome.run_dir / "run.json").read_text(encoding="utf-8"))


def test_a_run_generates_postprocesses_and_gates(project: Path):
    config = load_config(project)
    outcome = _run_one(config)

    assert outcome.status == "complete"
    assert (outcome.accepted, outcome.rejected, outcome.failed) == (1, 0, 0)

    record = _record(outcome)
    assert record["schema"] == 1
    assert record["recipes"]["terrain_tile"] == "3"
    assert record["style"]["contract_hash"].startswith("sha256:")

    job = record["jobs"][0]
    assert job["status"] == "accepted"
    assert job["recipe"] == "terrain_tile@3"
    assert job["postprocess"] == [
        "downscale_box",
        "palette_snap",
        "alpha_hard",
        "pad_to_grid",
    ]
    assert job["raw"][0]["sha256"].startswith("sha256:")
    assert job["post"][0]["sha256"].startswith("sha256:")

    with Image.open(config.root / job["post"][0]["path"]) as image:
        assert image.size == (32, 32)


def test_every_declared_gate_passes_on_the_output(project: Path):
    config = load_config(project)
    job = _record(_run_one(config))["jobs"][0]
    statuses = {gate["gate"]: gate["status"] for gate in job["gates"]}
    assert statuses == {
        "dimensions_exact": "pass",
        "grid_divisible": "pass",
        "palette_conformance": "pass",
        "max_unique_colors": "pass",
        "seamless_tile": "pass",
    }


def test_a_kind_without_a_recipe_is_refused_at_run_time(tmp_path: Path):
    make_project(tmp_path, with_recipes=False)
    config = load_config(tmp_path)
    with pytest.raises(SpecError) as caught:
        execute_run(config, make_backend(config))
    error = caught.value
    assert "no recipe for kind" in str(error)
    # The remedy must name the file to create, for the kind that is actually missing.
    assert ".yaml" in (error.remedy or "")
    assert "terrain/moss_stone" in str(error)


def test_a_failing_gate_rejects_the_asset(tmp_path: Path):
    make_project(tmp_path, toml=TOML.replace("max_unique_colors = 16", "max_unique_colors = 0"))
    config = load_config(tmp_path)
    outcome = _run_one(config)

    assert outcome.status == "failed"
    job = _record(outcome)["jobs"][0]
    assert job["status"] == "rejected"
    gate = next(item for item in job["gates"] if item["gate"] == "max_unique_colors")
    assert gate["status"] == "fail"
    assert gate["threshold"] == 0


def test_publishing_writes_an_immutable_engine_neutral_pack(project: Path):
    config = load_config(project)
    outcome = _run_one(config)

    first = publish(config, outcome.run_dir, allow_unreviewed=True)
    assert first.path.is_dir()
    assert (first.path / "assets" / "terrain" / "moss_stone.png").is_file()
    assert (first.path / "MANIFEST.sha256").is_file()
    assert (first.path / "LICENSES.md").is_file()

    manifest = json.loads((first.path / "pack.json").read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    assert asset["id"] == "terrain/moss_stone"
    assert asset["files"][0]["sha256"].startswith("sha256:")
    assert asset["files"][0]["width"] == 32
    assert asset["provenance"]["run_id"] == outcome.run_id
    assert asset["engine"]["tile"]["seamless"] is True

    second = publish(config, outcome.run_dir, allow_unreviewed=True)
    assert second.pack_id != first.pack_id
    assert first.path.is_dir()  # immutability: the old pack is untouched


def test_publishing_without_review_is_refused_by_default(project: Path):
    config = load_config(project)  # require_review = true
    outcome = _run_one(config)
    with pytest.raises(SdgaError) as caught:
        publish(config, outcome.run_dir)
    assert "review" in str(caught.value)


def test_publishing_a_run_with_no_accepted_jobs_is_refused(tmp_path: Path):
    make_project(tmp_path, toml=TOML.replace("max_unique_colors = 16", "max_unique_colors = 0"))
    config = load_config(tmp_path)
    outcome = _run_one(config)
    with pytest.raises(SdgaError) as caught:
        publish(config, outcome.run_dir, allow_unreviewed=True)
    assert "no accepted jobs" in str(caught.value)


def test_validate_re_checks_a_pack_with_no_backend(project: Path):
    config = load_config(project)
    outcome = _run_one(config)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)

    ok, rows = verify_pack(config, result.path, load_recipes(config))
    assert ok
    assert {row["gate"] for row in rows} >= {"seamless_tile", "palette_conformance"}

    target = result.path / "assets" / "terrain" / "moss_stone.png"
    with Image.open(target) as opened:
        image = opened.convert("RGBA")
    image.putpixel((0, 0), (255, 0, 255, 255))
    image.save(target)

    ok_after, rows_after = verify_pack(config, result.path, load_recipes(config))
    assert not ok_after
    assert any(
        row["gate"] == "palette_conformance" and row["status"] == "fail" for row in rows_after
    )


def test_validate_can_read_a_run_instead_of_a_pack(project: Path):
    config = load_config(project)
    outcome = _run_one(config)
    ok, rows = verify_run(config, outcome.run_dir, load_recipes(config))
    assert ok
    assert len(rows) == 5


def test_a_pack_that_lost_a_file_fails_validation(project: Path):
    config = load_config(project)
    outcome = _run_one(config)
    result = publish(config, outcome.run_dir, allow_unreviewed=True)
    (result.path / "assets" / "terrain" / "moss_stone.png").unlink()

    ok, rows = verify_pack(config, result.path, load_recipes(config))
    assert not ok
    assert rows[0]["gate"] == "file"


# --------------------------------------------------------------------- CLI


def test_cli_run_publish_validate_round_trip(project: Path, capsys):
    assert main(["run", "--project", str(project), "--asset", "terrain/moss_stone"]) == 0
    assert "complete" in capsys.readouterr().out

    assert main(["publish", "--project", str(project), "--allow-unreviewed"]) == 0
    assert "published" in capsys.readouterr().out

    pack = next((project / "packs").iterdir())
    assert main(["validate", "--project", str(project), str(pack)]) == 0
    out = capsys.readouterr().out
    assert "seamless_tile" in out
    assert out.strip().endswith("ok")


def test_cli_run_exits_one_when_a_gate_rejects(tmp_path: Path, capsys):
    make_project(tmp_path, toml=TOML.replace("max_unique_colors = 16", "max_unique_colors = 0"))
    assert main(["run", "--project", str(tmp_path), "--asset", "terrain/moss_stone"]) == 1
    assert "rejected" in capsys.readouterr().out


def test_cli_publish_refuses_unreviewed_assets(project: Path, capsys):
    assert main(["run", "--project", str(project), "--asset", "terrain/moss_stone"]) == 0
    assert main(["publish", "--project", str(project)]) == 1
    assert "review" in capsys.readouterr().err


def test_cli_run_dry_run_prints_the_bound_graph(project: Path, capsys):
    assert (
        main(["run", "--project", str(project), "--asset", "terrain/moss_stone", "--dry-run"]) == 0
    )
    out = capsys.readouterr().out
    assert '"graph"' in out
    assert '"KSampler"' in out
    assert not (project / "runs").exists()


def test_cli_validate_needs_a_target(project: Path, capsys):
    assert main(["validate", "--project", str(project)]) == 2
    assert "pack path" in capsys.readouterr().err


def test_cli_validate_reports_a_tampered_pack(project: Path, capsys):
    assert main(["run", "--project", str(project), "--asset", "terrain/moss_stone"]) == 0
    assert main(["publish", "--project", str(project), "--allow-unreviewed"]) == 0
    pack = next((project / "packs").iterdir())
    target = pack / "assets" / "terrain" / "moss_stone.png"
    with Image.open(target) as opened:
        image = opened.convert("RGBA")
    image.putpixel((0, 0), (255, 0, 255, 255))
    image.save(target)

    capsys.readouterr()
    assert main(["validate", "--project", str(project), str(pack)]) == 1
    assert "FAILED" in capsys.readouterr().out
