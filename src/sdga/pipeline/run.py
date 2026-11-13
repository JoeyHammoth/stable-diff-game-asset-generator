"""Stages 3-5: submit, postprocess, gate (docs/04-pipeline-stages.md §3-§5).

One run is one `run.json` plus the raw and postprocessed artifacts it describes. The record
is the unit of reproducibility: given it, the graph and the model files, a run can be
replayed exactly.
"""

from __future__ import annotations

import json
import platform
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .. import __version__
from ..backends.base import GenerationBackend, JobHandle, JobReport, PollState
from ..backends.comfyui.recipe import Recipe, RecipeRegistry, load_recipes
from ..canonical import hash_file, pretty_json
from ..config import Config, read_palette
from ..errors import BackendError, SdgaError
from ..model import SCHEMA, AssetKind, AssetSpec, GenerationRequest
from ..planning.plan import build_plan, final_size, grid_quantum
from ..postprocess import OpContext, apply_chain, ninepatch_margins
from ..review import write_contact_sheet
from ..specs import load_specs
from ..validate import DEFAULT_GATES, GateContext, evaluate, failed, severity

# Icons have no feet: their content is centred rather than grounded.
CENTERED_KINDS = frozenset({AssetKind.ICON})
MARGIN_KINDS = frozenset({AssetKind.UI_ELEMENT, AssetKind.ICON})

ACCEPTED = "accepted"
REJECTED = "rejected"
FAILED = "failed"
SUPERSEDED = "superseded"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(2)}"


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    run_dir: Path
    status: str
    accepted: int
    rejected: int
    failed: int
    superseded: int = 0


def gate_names(recipe: Recipe | None, spec: AssetSpec) -> list[str]:
    """Recipe-declared gates, plus any a spec adds; `off` removes one entirely."""
    names = (
        list(recipe.gates)
        if recipe is not None and recipe.gates
        else list(DEFAULT_GATES.get(spec.kind, ()))
    )
    for name in spec.gates:
        if name not in names:
            names.append(str(name))
    return [name for name in names if severity(name, spec.gates) != "off"]


def gate_context(
    config: Config, spec: AssetSpec, palette: tuple[tuple[int, int, int], ...]
) -> GateContext:
    return GateContext(
        size=final_size(spec),
        quantum=grid_quantum(spec.kind, config.style.grid),
        palette=palette,
        thresholds=config.gates.thresholds,
        kind=spec.kind,
        frames=spec.frames or 1,
        layout=spec.layout or (1, 1),
    )


def op_context(
    config: Config, spec: AssetSpec, palette: tuple[tuple[int, int, int], ...]
) -> OpContext:
    """One resolved context per asset: ops never guess a size, anchor, or strength."""
    return OpContext(
        size=final_size(spec),
        palette=palette,
        grid=grid_quantum(spec.kind, config.style.grid),
        frames=spec.frames or 1,
        layout=spec.layout or (1, 1),
        anchor="center" if spec.kind in CENTERED_KINDS else "feet",
        strength=float(spec.params.get("height_strength", 2.0)),
        flip_g=bool(spec.params.get("flip_g", False)),
        min_area=int(spec.params.get("min_area", 2)),
        tolerance=int(spec.params.get("bg_tolerance", 24)),
    )


def palette_for(config: Config) -> tuple[tuple[int, int, int], ...]:
    return read_palette(config.root / config.style.palette.path, str(config.path))


def runs_root(config: Config) -> Path:
    return config.root / config.project.runs_dir


def run_dir_for(config: Config, run_id: str | None = None) -> Path:
    root = runs_root(config)
    if run_id:
        candidate = root / run_id
        if not (candidate / "run.json").is_file():
            raise SdgaError(
                f"no run {run_id!r}",
                remedy=f"available runs: {_available_runs(root)}",
            )
        return candidate
    candidates = (
        sorted(
            (path for path in root.glob("*") if (path / "run.json").is_file()),
            key=lambda path: path.name,
            reverse=True,
        )
        if root.is_dir()
        else []
    )
    if not candidates:
        raise SdgaError("no runs yet", remedy="run `sdga run` first")
    return candidates[0]


def _available_runs(root: Path) -> str:
    if not root.is_dir():
        return "none"
    names = sorted(path.name for path in root.glob("*") if (path / "run.json").is_file())
    return ", ".join(names) if names else "none"


def _wait(backend: GenerationBackend, handle: JobHandle, config: Config) -> JobReport:
    deadline = time.monotonic() + config.backend.timeout_s
    while True:
        report = backend.poll(handle)
        if report.state in (PollState.SUCCEEDED, PollState.FAILED):
            return report
        if time.monotonic() > deadline:
            raise BackendError(
                "timeout",
                f"{handle.asset_id}: no terminal state within {config.backend.timeout_s}s",
                remedy="raise [backend] timeout_s, or check the backend console",
            )
        time.sleep(max(0.0, config.backend.poll_interval_s))


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def execute_job(
    config: Config,
    backend: GenerationBackend,
    request: GenerationRequest,
    spec: AssetSpec,
    recipe: Recipe | None,
    run_dir: Path,
    palette: tuple[tuple[int, int, int], ...],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "asset_id": request.asset_id,
        "kind": request.kind.value,
        "candidate": request.candidate,
        "recipe": request.recipe,
        "request_hash": request.request_hash,
        "seed": request.seed,
        "frames": spec.frames or 1,
        "layout": list(spec.layout) if spec.layout else None,
        "params": dict(request.params),
        "refs": [{"role": ref.role.value, "path": ref.path} for ref in request.refs],
        "status": FAILED,
    }
    started = time.monotonic()

    try:
        handle = backend.submit(request)
        report = _wait(backend, handle, config)
        if report.state is PollState.FAILED:
            raise BackendError(
                "execution_error",
                report.message or "job failed",
                payload=dict(report.error or {}),
            )
        if not report.artifacts:
            raise BackendError("bad_output", f"{request.asset_id}: backend returned no artifact")

        name = spec.slug if max(1, spec.candidates) == 1 else f"{spec.slug}__c{request.candidate}"
        raw_path = backend.fetch(report.artifacts[0], run_dir / "raw" / f"{name}.png")
        record["raw"] = [{"path": _relative(raw_path, config.root), "sha256": hash_file(raw_path)}]

        # Verify it is decodable before spending time on the chain: a corrupt fetch is a
        # bad artifact, not a postprocess bug.
        with Image.open(raw_path) as opened:
            opened.load()
            image = opened.convert("RGBA")

        chain = list(recipe.postprocess) if recipe is not None else []
        processed = apply_chain(image, chain, op_context(config, spec, palette))
        post_path = run_dir / "post" / f"{name}.png"
        processed.save(post_path, format="PNG")

        record["post"] = [
            {
                "path": _relative(post_path, config.root),
                "sha256": hash_file(post_path),
                "width": processed.size[0],
                "height": processed.size[1],
            }
        ]
        record["postprocess"] = chain
        if spec.kind in MARGIN_KINDS:
            # Recorded, not guessed: the pack and the gate both read these margins.
            record["ui"] = {"margins": list(ninepatch_margins(processed))}

        results = evaluate(gate_names(recipe, spec), processed, gate_context(config, spec, palette))
        record["gates"] = [result.to_dict() for result in results]
        record["status"] = REJECTED if failed(results, spec.gates) else ACCEPTED

    except BackendError as exc:
        record["error"] = {
            "kind": exc.kind,
            "detail": exc.detail,
            "payload": exc.payload,
        }
        record["status"] = FAILED
    except (OSError, ValueError) as exc:
        # A decode failure or an op that cannot apply (an empty frame, say) is a bad
        # artifact for this asset, never a crash that takes the whole run down.
        record["error"] = {"kind": "bad_output", "detail": f"postprocess failed: {exc}"}
        record["status"] = FAILED

    record["timings"] = {"total_s": round(time.monotonic() - started, 3)}
    return record


def promote(jobs: list[dict[str, Any]]) -> None:
    """Keep exactly one accepted candidate per asset; the rest are `superseded`.

    Deterministic: the lowest candidate index wins, because "best" is a human judgement that
    review exists for, not something a gate can rank.
    """
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        by_asset.setdefault(str(job["asset_id"]), []).append(job)

    for group in by_asset.values():
        if len(group) < 2:
            for job in group:
                job["promoted"] = job["status"] == ACCEPTED
            continue
        accepted = [job for job in group if job["status"] == ACCEPTED]
        winner = min(accepted, key=lambda job: int(job.get("candidate", 0))) if accepted else None
        for job in group:
            if job is winner:
                job["promoted"] = True
            else:
                job["promoted"] = False
                if job["status"] == ACCEPTED:
                    job["status"] = SUPERSEDED


def execute_run(
    config: Config,
    backend: GenerationBackend,
    *,
    assets: Sequence[str] | None = None,
    recipes: RecipeRegistry | None = None,
    dry_run: bool = False,
    emit: Callable[[str], None] = print,
) -> RunOutcome:
    registry = recipes if recipes is not None else load_recipes(config)
    specs = load_specs(config)
    by_id = {spec.id: spec for spec in specs}
    plan = build_plan(config, specs, assets=assets, recipes=registry, require_recipes=True)

    if dry_run:
        for request in plan.requests:
            emit(json.dumps(request.to_dict(), indent=2, sort_keys=True))
        return RunOutcome("", config.root, "dry-run", 0, 0, 0)

    profile = backend.probe()
    palette = palette_for(config)
    run_id = new_run_id()
    run_dir = runs_root(config) / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=False)
    (run_dir / "post").mkdir(parents=True, exist_ok=True)

    started = utc_now()
    jobs = [
        execute_job(
            config,
            backend,
            request,
            by_id[request.asset_id],
            registry.for_kind(request.kind),
            run_dir,
            palette,
        )
        for request in plan.requests
    ]
    promote(jobs)
    finished = utc_now()

    accepted = sum(1 for job in jobs if job["status"] == ACCEPTED)
    rejected = sum(1 for job in jobs if job["status"] == REJECTED)
    failed_count = sum(1 for job in jobs if job["status"] == FAILED)
    superseded = sum(1 for job in jobs if job["status"] == SUPERSEDED)
    if jobs and accepted >= 1 and rejected == 0 and failed_count == 0:
        status = "complete"
    elif accepted == 0:
        status = "failed"
    else:
        status = "partial"

    style = config.style
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "started": started,
        "finished": finished,
        "status": status,
        "tool": {
            "name": "sdga",
            "version": __version__,
            "python": platform.python_version(),
        },
        "style": {
            "name": style.name,
            "contract_hash": style.contract_hash,
            "grid": style.grid,
            "palette": style.palette.to_dict(),
        },
        "profile": profile.to_dict(),
        "recipes": registry.versions,
        "reviews": [],
        "jobs": jobs,
    }
    write_contact_sheet(config, run_dir, record)
    (run_dir / "run.json").write_text(pretty_json(record), encoding="utf-8")
    return RunOutcome(run_id, run_dir, status, accepted, rejected, failed_count, superseded)


__all__ = [
    "ACCEPTED",
    "FAILED",
    "REJECTED",
    "SUPERSEDED",
    "RunOutcome",
    "execute_job",
    "execute_run",
    "gate_context",
    "gate_names",
    "new_run_id",
    "op_context",
    "palette_for",
    "promote",
    "run_dir_for",
    "runs_root",
    "utc_now",
]
