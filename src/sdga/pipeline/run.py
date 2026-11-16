"""Stages 2-5: resolve, submit/collect, postprocess, gate (docs/04-pipeline-stages.md §2-§5).

One run is one `run.json` plus the raw and postprocessed artifacts it describes. The record
is the unit of reproducibility: given it, the graph and the model files, a run can be
replayed exactly.

The record is written incrementally — at the start, and after every completed job — because a
process can be killed. A run that leaves no trace is a run that has to be redone from zero; a
record with nine of ten jobs is a run that finishes in one job.

Nothing here retries blindly. The seam declares which failures are retryable
(`errors.BACKEND_KINDS`), and "CUDA out of memory" is special-cased to exactly one retry with a
printed remedy, because a second OOM at the same size is predicted, not unlucky.
"""

from __future__ import annotations

import copy
import json
import platform
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .. import __version__
from ..audio import (
    Audio,
    AudioBackend,
    AudioGateContext,
    BedBackend,
    BedRequest,
    build_audio_backend,
    build_bed_backend,
    detect_key,
    evaluate_audio,
    fade_edges,
    loop_crossfade,
    loudness_normalize,
    mix,
    read_midi,
    read_wav,
    render_sfx,
    tile_to_length,
    transform,
    write_midi,
    write_wav,
)
from ..backends.base import GenerationBackend, JobHandle, JobReport, PollState
from ..backends.comfyui.recipe import Recipe, RecipeRegistry, load_recipes
from ..canonical import hash_file, hash_obj, pretty_json
from ..config import Config, read_palette
from ..errors import BackendError, SdgaError
from ..model import SCHEMA, AssetKind, AssetSpec, GenerationRequest
from ..planning.plan import build_plan, final_size, grid_quantum
from ..postprocess import OpContext, apply_chain, ninepatch_margins
from ..review import write_contact_sheet
from ..specs import load_specs
from ..validate import DEFAULT_GATES, GateContext, evaluate, failed, severity
from .cache import ArtifactCache

# Icons have no feet: their content is centred rather than grounded.
CENTERED_KINDS = frozenset({AssetKind.ICON})
MARGIN_KINDS = frozenset({AssetKind.UI_ELEMENT, AssetKind.ICON})
AUDIO_KINDS = frozenset({AssetKind.SFX, AssetKind.MUSIC_TRACK})

# A one-shot must start and end at silence or it clicks; 5 ms is short enough to be inaudible
# and long enough to actually reach zero at 32 kHz.
SFX_FADE_S = 0.005

ACCEPTED = "accepted"
REJECTED = "rejected"
FAILED = "failed"
SUPERSEDED = "superseded"

# A job in one of these states has a postprocessed artifact on disk, so a resume can carry it
# over instead of generating it again.
RESUMABLE_STATUSES = frozenset({ACCEPTED, REJECTED, SUPERSEDED})

OOM_MARKERS = ("out of memory", "cuda oom", "allocation on device")


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
    cached: int = 0
    generated: int = 0


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
    size = final_size(spec)
    if size is None:
        raise ValueError(f"{spec.id}: image gates do not apply to audio assets")
    return GateContext(
        size=size,
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
    size = final_size(spec)
    if size is None:
        raise ValueError(f"{spec.id}: image ops do not apply to audio assets")
    return OpContext(
        size=size,
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


def audio_gate_context(
    config: Config, spec: AssetSpec, params: Mapping[str, Any]
) -> AudioGateContext:
    """The tempo grid and peak target an audio gate measures against, resolved once."""
    target_peak = float(config.gates.thresholds.get("audio_peak_dbfs", -3.0))
    thresholds = config.gates.thresholds
    if spec.kind is AssetKind.MUSIC_TRACK:
        music = params.get("music") or {}
        return AudioGateContext(
            expected_duration_s=float(music.get("target_s") or 0.0),
            target_peak_dbfs=target_peak,
            bpm=float(music.get("bpm") or 0.0),
            bars=int(music.get("bars") or 0),
            beats_per_bar=int(music.get("beats_per_bar") or 0),
            thresholds=thresholds,
        )
    return AudioGateContext(
        expected_duration_s=float(params.get("duration_s") or 0.0),
        target_peak_dbfs=target_peak,
        thresholds=thresholds,
    )


def _melody_midi(
    config: Config, request: GenerationRequest, run_dir: Path, name: str
) -> tuple[Path, dict[str, Any]]:
    """Derive this track's phrase from the leitmotif and write the bound MIDI to disk.

    Written rather than kept in memory because it is the proof of derivation: the pack's
    provenance points at a MIDI whose notes are auditable against the source phrase.
    """
    music = request.params["music"]
    phrase = read_midi(config.root / str(music["leitmotif"]))
    key = detect_key(phrase)
    derived = transform(
        phrase,
        key=key,
        degrees=int(music["transpose"]),
        tempo_scale=float(music["tempo_scale"]),
        fragment=int(music["fragment"]),
        fragment_bars=int(music["fragment_bars"]),
    )
    length_beats = float(music["render_s"]) * float(music["bpm"]) / 60.0
    tiled = tile_to_length(derived, length_beats)
    target = run_dir / "raw" / f"{name}.mid"
    write_midi(target, tiled)
    return target, {
        "path": _relative(target, config.root),
        "sha256": hash_file(target),
        "key": key.to_dict(),
        "notes": len(tiled.notes),
    }


def _fit_length(audio: Audio, seconds: float) -> Audio:
    """Cut or pad to an exact number of frames, so the crossfade lands on the bar line."""
    frames = int(round(seconds * audio.sample_rate))
    fitted = audio.slice_samples(0, frames)
    if fitted.frame_count == frames:
        return fitted
    padding = frames - fitted.frame_count
    return Audio(
        channels=tuple(channel + (0.0,) * padding for channel in fitted.channels),
        sample_rate=audio.sample_rate,
    )


def _audio_post(
    config: Config,
    spec: AssetSpec,
    raw_path: Path,
    params: Mapping[str, Any],
    bed_path: Path | None = None,
) -> Audio:
    """The audio chain. Music loops; a one-shot fades and is normalised.

    The bed is fitted to the same render length as the melody and mixed at the configured
    gain. It is never allowed to change the melody's timing: both are cut/padded to
    `render_s` before the sum, and the loop crossfade happens after.

    `trim_silence` is deliberately absent from the one-shot chain: trimming shortens the file,
    which would fail the same asset's `duration_exact` gate.
    """
    audio = read_wav(raw_path)
    target_peak = float(config.gates.thresholds.get("audio_peak_dbfs", -3.0))
    if spec.kind is AssetKind.MUSIC_TRACK:
        music = params["music"]
        render_s = float(music["render_s"])
        fitted = _fit_length(audio, render_s)
        bed: Audio | None = None
        if bed_path is not None:
            bed_audio = read_wav(bed_path)
            if bed_audio.sample_rate != fitted.sample_rate:
                raise ValueError(
                    f"bed is {bed_audio.sample_rate} Hz but the melody is {fitted.sample_rate} Hz"
                )
            bed = _fit_length(bed_audio, render_s)
        mixed = mix(fitted, bed, melody_gain_db=float(music.get("melody_gain_db") or 0.0))
        looped = loop_crossfade(mixed, float(music["crossfade_s"]))
        return loudness_normalize(looped, target_peak)
    return loudness_normalize(fade_edges(audio, SFX_FADE_S), target_peak)


def execute_audio_job(
    config: Config,
    audio_backend: AudioBackend,
    bed_backend: BedBackend | None,
    request: GenerationRequest,
    spec: AssetSpec,
    run_dir: Path,
    *,
    cache: ArtifactCache | None = None,
    profile_hash: str = "",
    emit: Callable[[str], None] = print,
) -> dict[str, Any]:
    """One audio asset: derive the phrase, render, loop or fade, then gate.

    Same record shape as an image job, because `publish`, `verify` and `status` should not
    need to know which half of the pipeline produced a file.
    """
    music = request.params.get("music") or {}
    record: dict[str, Any] = {
        "asset_id": request.asset_id,
        "kind": request.kind.value,
        "candidate": request.candidate,
        "recipe": None,
        "request_hash": request.request_hash,
        "seed": request.seed,
        "params": dict(request.params),
        "refs": [],
        "status": FAILED,
        "cached": False,
        "source": "generated",
    }
    started = time.monotonic()
    name = spec.slug if max(1, spec.candidates) == 1 else f"{spec.slug}__c{request.candidate}"
    raw_dest = run_dir / "raw" / f"{name}.wav"

    try:
        midi_path: Path | None = None
        if spec.kind is AssetKind.MUSIC_TRACK:
            midi_path, midi_record = _melody_midi(config, request, run_dir, name)
            record["midi"] = midi_record

        bed_spec = music.get("bed") or {}
        bed_kind = str(bed_spec.get("kind") or "none")
        wants_bed = spec.kind is AssetKind.MUSIC_TRACK and bed_kind != "none"
        entry = None
        if cache is not None:
            entry = cache.lookup(request.request_hash, profile_hash)

        bed_path: Path | None = None
        raw_path: Path
        if wants_bed:
            # The bed is the cached artifact when there is one: it is the expensive, model-
            # produced part. The melody is deterministic and local, so a hit re-renders it
            # and re-mixes rather than storing a mixed file that would hide a chain change.
            if bed_backend is None:
                raise BackendError(
                    "missing_capability",
                    f"{request.asset_id}: bed {bed_kind!r} is configured but not available",
                    remedy="set [audio] bed = 'none', 'texture' or 'musicgen' and check doctor",
                )
            bed_dest = run_dir / "raw" / f"{name}.bed.wav"
            if entry is not None and cache is not None:
                bed_path = cache.link(entry, bed_dest)
                record["cached"] = True
                record["source"] = "cache"
            else:
                bed_path = bed_backend.generate(
                    BedRequest(
                        prompt=request.positive,
                        negative=request.negative,
                        duration_s=float(music["render_s"]),
                        seed=request.seed,
                        sample_rate=config.audio.sample_rate,
                    ),
                    bed_dest,
                )
                if cache is not None and profile_hash:
                    cache.store(request.request_hash, profile_hash, bed_path)
            record["bed"] = {
                "path": _relative(bed_path, config.root),
                "sha256": hash_file(bed_path),
                "kind": bed_kind,
                "gain_db": float(bed_spec.get("gain_db") or 0.0),
            }
            if midi_path is None:  # pragma: no cover - music implies a melody
                raise ValueError(f"{request.asset_id}: no melody to render")
            raw_path = audio_backend.render_melody(midi_path, raw_dest, timbre=str(music["timbre"]))
        elif spec.kind is AssetKind.MUSIC_TRACK:
            if entry is not None and cache is not None:
                raw_path = cache.link(entry, raw_dest)
                record["cached"] = True
                record["source"] = "cache"
            else:
                if midi_path is None:  # pragma: no cover - set just above
                    raise ValueError(f"{request.asset_id}: no melody to render")
                raw_path = audio_backend.render_melody(
                    midi_path, raw_dest, timbre=str(music["timbre"])
                )
                if cache is not None and profile_hash:
                    cache.store(request.request_hash, profile_hash, raw_path)
        else:
            if entry is not None and cache is not None:
                raw_path = cache.link(entry, raw_dest)
                record["cached"] = True
                record["source"] = "cache"
            else:
                generated = render_sfx(
                    seed=request.seed,
                    duration_s=float(request.params["duration_s"]),
                    sample_rate=config.audio.sample_rate,
                )
                raw_path = write_wav(raw_dest, generated)
                if cache is not None and profile_hash:
                    cache.store(request.request_hash, profile_hash, raw_path)

        record["retries"] = []
        record["raw"] = [{"path": _relative(raw_path, config.root), "sha256": hash_file(raw_path)}]
        if bed_path is not None:
            record["raw"].append(
                {"path": _relative(bed_path, config.root), "sha256": hash_file(bed_path)}
            )

        processed = _audio_post(config, spec, raw_path, request.params, bed_path)
        post_path = run_dir / "post" / f"{name}.wav"
        write_wav(post_path, processed)
        record["post"] = [
            {
                "path": _relative(post_path, config.root),
                "sha256": hash_file(post_path),
                "sample_rate": processed.sample_rate,
                "channels": processed.channel_count,
                "duration_s": round(processed.duration_s, 6),
                "peak_dbfs": round(processed.peak_dbfs(), 3),
            }
        ]
        if spec.kind is AssetKind.MUSIC_TRACK:
            prefix = ["mix"] if bed_path is not None else []
            record["postprocess"] = [*prefix, "loop_crossfade", "loudness_normalize"]
        else:
            record["postprocess"] = ["fade_edges", "loudness_normalize"]
        if spec.kind is AssetKind.MUSIC_TRACK:
            record["loop"] = {
                "start_s": 0.0,
                "end_s": round(float(music["target_s"]), 6),
                "crossfade_s": float(music["crossfade_s"]),
                "bpm": float(music["bpm"]),
                "bars": int(music["bars"]),
                "beats_per_bar": int(music["beats_per_bar"]),
            }

        results = evaluate_audio(
            gate_names(None, spec),
            processed,
            audio_gate_context(config, spec, request.params),
        )
        record["gates"] = [result.to_dict() for result in results]
        record["status"] = REJECTED if failed(results, spec.gates) else ACCEPTED

    except BackendError as exc:
        record["error"] = {"kind": exc.kind, "detail": exc.detail, "payload": exc.payload}
        record["retries"] = []
        record["status"] = FAILED
    except (OSError, ValueError) as exc:
        record["error"] = {"kind": "bad_output", "detail": f"audio failed: {exc}"}
        record["status"] = FAILED

    record["timings"] = {"total_s": round(time.monotonic() - started, 3)}
    return record


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


def _is_out_of_memory(exc: BackendError) -> bool:
    text = exc.detail.lower()
    return any(marker in text for marker in OOM_MARKERS)


def _generate(
    config: Config,
    backend: GenerationBackend,
    request: GenerationRequest,
    *,
    emit: Callable[[str], None],
    retries: list[dict[str, Any]],
) -> JobReport:
    """Submit, wait, and retry only what the error taxonomy says is worth retrying.

    `retries` is the caller's list, appended in place: a run that ends in failure must still
    record the attempts that were abandoned, or the OOM evidence dies with the exception.
    """
    while True:
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
                raise BackendError(
                    "bad_output", f"{request.asset_id}: backend returned no artifact"
                )
            return report
        except BackendError as exc:
            out_of_memory = _is_out_of_memory(exc)
            # One retry for OOM, whatever the configured allowance: the second failure is
            # predicted by the first, so a third attempt just burns VRAM again.
            allowance = 1 if out_of_memory else config.backend.retry_attempts
            if not exc.retryable or len(retries) >= allowance:
                raise
            retries.append(
                {"kind": exc.kind, "detail": exc.detail[:300], "out_of_memory": out_of_memory}
            )
            if out_of_memory:
                emit(
                    f"{request.asset_id}: CUDA out of memory - retrying once at concurrency 1. "
                    "If it recurs, start ComfyUI with --lowvram or lower "
                    "[style] generation_size."
                )
            if config.backend.retry_backoff_s > 0:
                time.sleep(config.backend.retry_backoff_s)


def _already_generated(backend: GenerationBackend, request: GenerationRequest) -> JobReport | None:
    """Ask the backend whether this prompt finished before we were interrupted."""
    try:
        report = backend.lookup(request)
    except BackendError:
        # An unreachable server means "unknown", never "failed": falling through to a submit
        # is the honest response, and the submit will report its own error if there is one.
        return None
    if report is not None and report.state is PollState.SUCCEEDED and report.artifacts:
        return report
    return None


def execute_job(
    config: Config,
    backend: GenerationBackend,
    request: GenerationRequest,
    spec: AssetSpec,
    recipe: Recipe | None,
    run_dir: Path,
    palette: tuple[tuple[int, int, int], ...],
    *,
    cache: ArtifactCache | None = None,
    profile_hash: str = "",
    resume_lookup: bool = False,
    emit: Callable[[str], None] = print,
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
        # Playback metadata, not generation input: it changes the pack, never the request hash.
        "animations": [
            {"name": name, "start": start, "count": count}
            for name, (start, count) in sorted(
                spec.animations.items(), key=lambda item: (item[1][0], item[0])
            )
        ]
        or None,
        "params": dict(request.params),
        "refs": [{"role": ref.role.value, "path": ref.path} for ref in request.refs],
        "status": FAILED,
        "cached": False,
        "source": "generated",
    }
    started = time.monotonic()
    retries: list[dict[str, Any]] = []
    name = spec.slug if max(1, spec.candidates) == 1 else f"{spec.slug}__c{request.candidate}"
    raw_dest = run_dir / "raw" / f"{name}.png"

    try:
        entry = cache.lookup(request.request_hash, profile_hash) if cache is not None else None
        if cache is not None and entry is not None:
            raw_path = cache.link(entry, raw_dest)
            record["cached"] = True
            record["source"] = "cache"
        else:
            report = _already_generated(backend, request) if resume_lookup else None
            if report is not None:
                record["source"] = "backend"
                raw_path = backend.fetch(report.artifacts[0], raw_dest)
            else:
                report = _generate(config, backend, request, emit=emit, retries=retries)
                raw_path = backend.fetch(report.artifacts[0], raw_dest)
            if cache is not None and profile_hash:
                cache.store(request.request_hash, profile_hash, raw_path)

        record["retries"] = retries
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
        record["retries"] = retries
        record["status"] = FAILED
    except (OSError, ValueError) as exc:
        # A decode failure or an op that cannot apply (an empty frame, say) is a bad
        # artifact for this asset, never a crash that takes the whole run down.
        record["error"] = {"kind": "bad_output", "detail": f"postprocess failed: {exc}"}
        record["status"] = FAILED

    record["timings"] = {"total_s": round(time.monotonic() - started, 3)}
    return record


def recorded_status(job: dict[str, Any], spec: AssetSpec) -> str:
    """Re-derive a carried-over job's status from its gates, so promotion stays honest."""
    for gate in job.get("gates") or []:
        if gate.get("status") == "fail" and severity(str(gate.get("gate")), spec.gates) == "error":
            return REJECTED
    return ACCEPTED


def _post_intact(config: Config, job: dict[str, Any]) -> bool:
    """A carried-over job counts only if its artifact is still the one it recorded."""
    post = (job.get("post") or [{}])[0]
    path = config.root / str(post.get("path") or "")
    if not post.get("path") or not path.is_file():
        return False
    return hash_file(path) == str(post.get("sha256") or "")


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


def _counts(jobs: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {ACCEPTED: 0, REJECTED: 0, FAILED: 0, SUPERSEDED: 0}
    for job in jobs:
        status = str(job.get("status"))
        if status in counts:
            counts[status] += 1
    return counts


def _status_for(counts: dict[str, int], *, planned: int, completed: int) -> str:
    if completed < planned:
        return "running"
    if counts[ACCEPTED] >= 1 and counts[REJECTED] == 0 and counts[FAILED] == 0:
        return "complete"
    if counts[ACCEPTED] == 0:
        return "failed"
    return "partial"


def _write_record(run_dir: Path, record: dict[str, Any]) -> None:
    (run_dir / "run.json").write_text(pretty_json(record), encoding="utf-8")


def execute_run(
    config: Config,
    backend: GenerationBackend,
    *,
    audio: AudioBackend | None = None,
    bed: BedBackend | None = None,
    assets: Sequence[str] | None = None,
    recipes: RecipeRegistry | None = None,
    dry_run: bool = False,
    resume: str | None = None,
    force: bool = False,
    use_cache: bool = True,
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
    wants_audio = any(request.kind in AUDIO_KINDS for request in plan.requests)
    audio_backend: AudioBackend = audio or build_audio_backend(
        config.audio.kind,
        sample_rate=config.audio.sample_rate,
        soundfont=config.audio.soundfont,
        root=config.root,
    )
    wants_bed = any(
        ((request.params.get("music") or {}).get("bed") or {}).get("kind", "none") != "none"
        for request in plan.requests
    )
    bed_backend: BedBackend = bed or build_bed_backend(
        config.audio.bed,
        url=config.audio.bed_url,
        sample_rate=config.audio.sample_rate,
        timeout_s=config.audio.bed_timeout_s,
    )
    bed_profile = bed_backend.probe() if wants_bed else None
    audio_profile = audio_backend.probe() if wants_audio else None
    # One cache key covers both halves: switching instrument or bed invalidates, while moving
    # a service to another host does not.
    audio_cache_hash = hash_obj(
        {
            "instrument": "" if audio_profile is None else audio_profile.profile_hash,
            "bed": "" if bed_profile is None else bed_profile.profile_hash,
        }
    )
    palette = palette_for(config)
    cache = ArtifactCache(
        config.root / config.project.cache_dir,
        read=use_cache and not force,
        write=use_cache,
    )

    previous: dict[str, Any] = {}
    if resume is not None:
        run_dir = run_dir_for(config, None if resume in {"", "latest"} else resume)
        previous = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        run_id = str(previous.get("run_id") or run_dir.name)
        (run_dir / "raw").mkdir(parents=True, exist_ok=True)
        (run_dir / "post").mkdir(parents=True, exist_ok=True)
    else:
        run_id = new_run_id()
        run_dir = runs_root(config) / run_id
        (run_dir / "raw").mkdir(parents=True, exist_ok=False)
        (run_dir / "post").mkdir(parents=True, exist_ok=True)

    carried: dict[str, dict[str, Any]] = {}
    if resume is not None:
        for job in previous.get("jobs", []):
            request_hash = str(job.get("request_hash") or "")
            if (
                job.get("status") in RESUMABLE_STATUSES
                and request_hash
                and _post_intact(config, job)
            ):
                carried[request_hash] = job

    def work(request: GenerationRequest) -> dict[str, Any]:
        spec = by_id[request.asset_id]
        reusable = carried.get(request.request_hash)
        if reusable is not None:
            # Already generated, postprocessed and gated in the interrupted run. Re-running
            # it would either cost a GPU minute or, worse, produce a different image.
            job = copy.deepcopy(reusable)
            job["status"] = recorded_status(job, spec)
            job["cached"] = True
            job["source"] = "resume"
            job["timings"] = {"total_s": 0.0}
            return job
        if request.kind in AUDIO_KINDS:
            assert audio_profile is not None, "an audio request implies an audio profile"
            return execute_audio_job(
                config,
                audio_backend,
                bed_backend,
                request,
                spec,
                run_dir,
                cache=cache,
                profile_hash=audio_cache_hash,
                emit=emit,
            )
        return execute_job(
            config,
            backend,
            request,
            spec,
            registry.for_kind(request.kind),
            run_dir,
            palette,
            cache=cache,
            profile_hash=profile.profile_hash,
            resume_lookup=resume is not None,
            emit=emit,
        )

    style = config.style
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "started": str(previous.get("started") or utc_now()),
        "finished": None,
        "status": "running",
        "planned": len(plan.requests),
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
        "reviews": list(previous.get("reviews", [])),
        "jobs": [],
    }
    if audio_profile is not None:
        audio_record = audio_profile.to_dict()
        if bed_profile is not None:
            audio_record["bed"] = bed_profile.to_dict()
        record["audio"] = audio_record
    if resume is not None:
        record["resumed"] = True
    # From here on a kill leaves a resumable record rather than an anonymous directory.
    _write_record(run_dir, record)

    jobs: list[dict[str, Any]] = []
    workers = max(1, config.backend.max_concurrency)
    if workers == 1 or len(plan.requests) < 2:
        for request in plan.requests:
            jobs.append(work(request))
            record["jobs"] = jobs
            _write_record(run_dir, record)
    else:
        # The pool size *is* the limiter: no more than `workers` jobs can be between submit
        # and fetch at once, and the records still land in plan order.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, request) for request in plan.requests]
            for future in futures:
                jobs.append(future.result())
                record["jobs"] = jobs
                _write_record(run_dir, record)

    promote(jobs)
    counts = _counts(jobs)
    record["jobs"] = jobs
    record["finished"] = utc_now()
    record["status"] = _status_for(counts, planned=len(plan.requests), completed=len(jobs))
    _write_record(run_dir, record)
    write_contact_sheet(config, run_dir, record)

    return RunOutcome(
        run_id,
        run_dir,
        str(record["status"]),
        counts[ACCEPTED],
        counts[REJECTED],
        counts[FAILED],
        counts[SUPERSEDED],
        cached=sum(1 for job in jobs if job.get("source") in {"cache", "resume"}),
        generated=sum(1 for job in jobs if job.get("source") == "generated"),
    )


__all__ = [
    "ACCEPTED",
    "AUDIO_KINDS",
    "FAILED",
    "REJECTED",
    "RESUMABLE_STATUSES",
    "SUPERSEDED",
    "RunOutcome",
    "audio_gate_context",
    "execute_audio_job",
    "execute_job",
    "execute_run",
    "gate_context",
    "gate_names",
    "new_run_id",
    "op_context",
    "palette_for",
    "promote",
    "recorded_status",
    "run_dir_for",
    "runs_root",
    "utc_now",
]
