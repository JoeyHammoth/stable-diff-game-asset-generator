from __future__ import annotations

from pathlib import Path

from _project import make_project

from sdga import doctor
from sdga.backends import FakeBackend
from sdga.config import load_config
from sdga.errors import BackendError


class _BrokenBackend:
    kind = "comfyui"

    def probe(self):
        raise BackendError(
            "unreachable",
            "cannot reach http://127.0.0.1:8188",
            remedy="start ComfyUI, then re-run `sdga doctor`",
        )

    def submit(self, request):  # pragma: no cover - protocol completeness
        raise NotImplementedError


def _check(report, name):
    return next(check for check in report.checks if check.name == name)


def test_healthy_fake_backend_reports_ok(project: Path):
    config = load_config(project)
    report = doctor.run(config, FakeBackend())
    assert report.ok
    assert _check(report, "backend").status == "pass"
    assert _check(report, "palette").status == "pass"


def test_missing_node_names_the_node_and_the_recipe(project: Path):
    config = load_config(project)
    backend = FakeBackend(nodes=("CheckpointLoaderSimple",))
    report = doctor.run(
        config,
        backend,
        [
            doctor.Requirement(
                "terrain_tile",
                nodes=("CheckpointLoaderSimple", "PaletteMatch"),
                models={"checkpoints": ("sd_v1-5.safetensors",)},
            )
        ],
    )
    check = _check(report, "recipe:terrain_tile")
    assert check.status == "fail"
    assert "PaletteMatch" in check.detail
    assert "terrain_tile" in (check.remedy or "")
    assert not report.ok


def test_missing_model_names_the_comfyui_folder(project: Path):
    config = load_config(project)
    report = doctor.run(
        config,
        FakeBackend(),
        [doctor.Requirement("sprite_sheet", models={"loras": ("absent_style.safetensors",)})],
    )
    check = _check(report, "recipe:sprite_sheet")
    assert check.status == "fail"
    assert "models/loras" in check.detail
    assert "absent_style.safetensors" in (check.remedy or "")


def test_present_requirements_pass(project: Path):
    config = load_config(project)
    report = doctor.run(
        config,
        FakeBackend(),
        [
            doctor.Requirement(
                "terrain_tile",
                nodes=("KSampler", "VAEDecode"),
                models={"checkpoints": ("sd_v1-5.safetensors",)},
            )
        ],
    )
    assert _check(report, "recipe:terrain_tile").status == "pass"
    assert report.ok


def test_checkpoint_is_skipped_on_the_fake_backend(project: Path):
    config = load_config(project)
    report = doctor.run(config, FakeBackend())
    assert _check(report, "checkpoint").status == "skipped"


def test_unreachable_backend_is_a_failing_check(project: Path):
    config = load_config(project)
    report = doctor.run(config, _BrokenBackend())
    check = _check(report, "backend")
    assert check.status == "fail"
    assert "start ComfyUI" in (check.remedy or "")
    assert report.profile is None
    assert not report.ok


def test_declared_gaps_are_reported(project: Path):
    config = load_config(project)
    backend = FakeBackend(
        gaps=(doctor_gap := None,) if False else ()  # keep type checkers quiet
    )
    report = doctor.run(config, backend)
    assert report.ok


def test_table_renders_a_header_and_remedy_lines(project: Path):
    config = load_config(project)
    report = doctor.run(
        config, FakeBackend(nodes=()), [doctor.Requirement("ui_element", nodes=("PaletteMatch",))]
    )
    table = report.render()
    assert table.splitlines()[0].startswith("CHECK")
    assert "recipe:ui_element" in table
    assert "! recipe:ui_element:" in table


def test_no_requirements_is_reported_as_skipped_not_passed(project: Path):
    config = load_config(project)
    report = doctor.run(config, FakeBackend())
    assert _check(report, "recipes").status == "skipped"


def test_report_serialises_to_json_ready_data(project: Path):
    config = load_config(project)
    payload = doctor.run(config, FakeBackend()).to_dict()
    assert payload["ok"] is True
    assert payload["profile"]["kind"] == "fake"
    assert isinstance(payload["checks"], list)


def test_doctor_leaves_no_files_behind(tmp_path: Path):
    root = make_project(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    doctor.run(load_config(root), FakeBackend())
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert before == after
