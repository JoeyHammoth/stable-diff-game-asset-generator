from __future__ import annotations

import json
from pathlib import Path

import pytest
from _project import TOML, make_project

from sdga.cli import main


def test_plan_writes_plan_json_and_exits_zero(project: Path, capsys):
    assert main(["plan", "--project", str(project)]) == 0

    payload = json.loads((project / "plan.json").read_text(encoding="utf-8"))
    assert len(payload["requests"]) == 4
    assert payload["schema"] == 1
    assert "planned 4 request(s)" in capsys.readouterr().out


def test_plan_output_is_reproducible(project: Path):
    assert main(["plan", "--project", str(project)]) == 0
    first = (project / "plan.json").read_bytes()
    assert main(["plan", "--project", str(project)]) == 0
    assert (project / "plan.json").read_bytes() == first


def test_plan_dry_run_prints_the_first_request(project: Path, capsys):
    assert main(["plan", "--project", str(project), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"asset_id"' in out
    assert "char/ranger_walk" in out  # first by sorted id


def test_plan_out_flag_writes_elsewhere(project: Path, tmp_path: Path):
    target = tmp_path / "elsewhere" / "plan.json"
    assert main(["plan", "--project", str(project), "--out", str(target)]) == 0
    assert target.is_file()


def test_plan_asset_filter(project: Path):
    assert main(["plan", "--project", str(project), "--asset", "ui/button_normal"]) == 0
    payload = json.loads((project / "plan.json").read_text(encoding="utf-8"))
    assert [request["asset_id"] for request in payload["requests"]] == ["ui/button_normal"]


def test_doctor_succeeds_on_the_fake_backend(project: Path, capsys):
    assert main(["doctor", "--project", str(project)]) == 0
    assert "CHECK" in capsys.readouterr().out


def test_doctor_json_is_machine_readable(project: Path, capsys):
    assert main(["doctor", "--project", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["profile"]["kind"] == "fake"


def test_missing_config_exits_with_a_schema_error(tmp_path: Path, capsys):
    assert main(["doctor", "--project", str(tmp_path)]) == 4
    assert "sdga.toml" in capsys.readouterr().err


def test_invalid_spec_exits_with_a_schema_error(project: Path, capsys):
    (project / "assets" / "bad.yaml").write_text(
        "schema: 1\nassets:\n  - id: nope\n", encoding="utf-8"
    )
    assert main(["plan", "--project", str(project)]) == 4
    assert "invalid asset id" in capsys.readouterr().err


def test_a_comfyui_backend_that_is_not_running_exits_as_unavailable(tmp_path: Path, capsys):
    # Port 9 is the discard service: reliably refused, so this cannot flake on a dev box
    # that happens to have ComfyUI listening on 8188.
    toml = TOML.replace('kind = "fake"', 'kind = "comfyui"\nurl = "http://127.0.0.1:9"')
    make_project(tmp_path, toml=toml)
    assert main(["doctor", "--project", str(tmp_path)]) == 3
    out = capsys.readouterr().out
    assert "backend" in out
    assert "unreachable" in out


def test_unimplemented_command_exits_as_usage_error(project: Path, capsys):
    assert main(["review", "--project", str(project)]) == 2
    assert "phase P3" in capsys.readouterr().err


def test_unknown_command_exits_two():
    with pytest.raises(SystemExit) as caught:
        main(["nonsense"])
    assert caught.value.code == 2


def test_version_exits_zero():
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
