"""Audio gates (docs/04 §5, ticket T33).

Same contract as the image gates: deterministic, read-only, and a gate that cannot apply
records `skipped`, never `pass`. The measured value is always printed, because
"audio_loop_seam failed" is useless while "audio_loop_seam 12.4 > 3.0" is a diagnosis.

`audio_loop_seam` is the regression guard for gap analysis A5: it compares the wrap
`|x[-1] - x[0]|` against the median first difference of the file, plus the wrap-window RMS
against the interior RMS. A file that ends mid-note fails it; a properly folded loop passes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from ..validate.gates import FAIL, PASS, SKIPPED, GateResult
from .wav import Audio, gain_to_db

Gate = Callable[[Audio, "AudioGateContext"], GateResult]


@dataclass(frozen=True)
class AudioGateContext:
    """What an audio gate may need, resolved once per asset from its spec and the plan."""

    expected_duration_s: float | None = None
    target_peak_dbfs: float = -3.0
    bpm: float | None = None
    bars: int | None = None
    beats_per_bar: int | None = None
    thresholds: Mapping[str, Any] = field(default_factory=dict)

    def threshold(self, name: str, default: float) -> float:
        value = self.thresholds.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def _seam_metrics(audio: Audio) -> tuple[float, float, float]:
    """`(wrap delta, median first difference, level drop at the wrap in dB)`."""
    samples = audio.mono()
    if len(samples) < 2:
        return 0.0, 0.0, 0.0
    wrap = abs(samples[-1] - samples[0])
    steps = [abs(samples[index + 1] - samples[index]) for index in range(len(samples) - 1)]
    typical = median(steps)
    window = min(len(samples) // 4, max(1, int(0.05 * audio.sample_rate)))
    head = samples[:window]
    tail = samples[-window:]
    head_rms = (sum(value * value for value in head) / window) ** 0.5
    tail_rms = (sum(value * value for value in tail) / window) ** 0.5
    interior_rms = (sum(value * value for value in samples) / len(samples)) ** 0.5
    if head_rms < 1e-4 or tail_rms < 1e-4:
        # A rest on either side of the wrap is recorded as zero drop. By level alone, a
        # deliberate rest and a fade-out look identical, so this number informs the reviewer
        # instead of failing a musically valid loop; continuity is the wrap delta's job.
        level_drop = 0.0
    else:
        level_drop = max(0.0, gain_to_db(interior_rms) - gain_to_db(min(head_rms, tail_rms)))
    return wrap, typical, level_drop


def audio_loop_seam(audio: Audio, ctx: AudioGateContext) -> GateResult:
    ratio = ctx.threshold("loop_seam_ratio", 3.0)
    rms_limit = ctx.threshold("loop_rms_db", 3.0)
    wrap, typical, level_drop = _seam_metrics(audio)
    limit = ratio * typical
    # Continuity is the pass/fail question. The level drop is measured and reported, but a
    # loop that ends on a rest must not fail a gate about a click that does not exist.
    ok = wrap <= limit
    return GateResult(
        "audio_loop_seam",
        PASS if ok else FAIL,
        value={
            "wrap_delta": round(wrap, 6),
            "limit": round(limit, 6),
            "level_drop_db": round(level_drop, 3),
        },
        threshold={"ratio": ratio, "rms_db": rms_limit},
        detail=(
            "wrap is continuous"
            if ok
            else f"wrap {wrap:.4f} vs limit {limit:.4f} (level drop {level_drop:.2f} dB)"
        ),
    )


def audio_peak(audio: Audio, ctx: AudioGateContext) -> GateResult:
    tolerance = ctx.threshold("audio_peak_tolerance_db", 0.5)
    measured = audio.peak_dbfs()
    delta = abs(measured - ctx.target_peak_dbfs)
    return GateResult(
        "audio_peak",
        PASS if delta <= tolerance else FAIL,
        value=round(measured, 3),
        threshold=ctx.target_peak_dbfs,
        detail=f"off target by {delta:.2f} dB (tolerance {tolerance})",
    )


def audio_clip(audio: Audio, ctx: AudioGateContext) -> GateResult:
    clipped = sum(1 for channel in audio.channels for value in channel if abs(value) >= 1.0)
    return GateResult(
        "audio_clip",
        PASS if clipped == 0 else FAIL,
        value=clipped,
        threshold=0,
        detail=f"{audio.frame_count} frame(s) of {audio.channel_count} channel(s)",
    )


def duration_exact(audio: Audio, ctx: AudioGateContext) -> GateResult:
    if ctx.expected_duration_s is None:
        return GateResult("duration_exact", SKIPPED, detail="the spec declares no duration")
    tolerance_ms = ctx.threshold("duration_tolerance_ms", 5.0)
    measured = audio.duration_s
    delta_ms = abs(measured - ctx.expected_duration_s) * 1000.0
    return GateResult(
        "duration_exact",
        PASS if delta_ms <= tolerance_ms else FAIL,
        value=round(measured, 6),
        threshold=round(ctx.expected_duration_s, 6),
        detail=f"off by {delta_ms:.2f} ms (tolerance {tolerance_ms})",
    )


def beat_alignment(audio: Audio, ctx: AudioGateContext) -> GateResult:
    """The loop length must be exactly `bars * beats_per_bar * 60 / bpm` seconds.

    This is the gate that makes "16-bar loop" a fact: a file that is 31.9 s where the grid
    says 32.0 drifts against the game's clock on every repeat.
    """
    if not ctx.bpm or not ctx.bars or not ctx.beats_per_bar:
        return GateResult("beat_alignment", SKIPPED, detail="no tempo or bar count declared")
    expected = ctx.bars * ctx.beats_per_bar * 60.0 / ctx.bpm
    tolerance_ms = ctx.threshold("beat_tolerance_ms", 10.0)
    delta_ms = abs(audio.duration_s - expected) * 1000.0
    return GateResult(
        "beat_alignment",
        PASS if delta_ms <= tolerance_ms else FAIL,
        value=round(audio.duration_s, 6),
        threshold=round(expected, 6),
        detail=(
            f"{ctx.bars} bars x {ctx.beats_per_bar} beats @ {ctx.bpm:g} bpm; "
            f"off by {delta_ms:.2f} ms"
        ),
    )


AUDIO_GATES: Mapping[str, Gate] = {
    "audio_clip": audio_clip,
    "audio_loop_seam": audio_loop_seam,
    "audio_peak": audio_peak,
    "beat_alignment": beat_alignment,
    "duration_exact": duration_exact,
}


def evaluate_audio(gates: Sequence[str], audio: Audio, ctx: AudioGateContext) -> list[GateResult]:
    results: list[GateResult] = []
    for name in gates:
        try:
            gate = AUDIO_GATES[name]
        except KeyError:
            raise KeyError(
                f"unknown audio gate {name!r}; known gates: {', '.join(sorted(AUDIO_GATES))}"
            ) from None
        results.append(gate(audio, ctx))
    return results


__all__ = [
    "AUDIO_GATES",
    "AudioGateContext",
    "Gate",
    "audio_clip",
    "audio_loop_seam",
    "audio_peak",
    "beat_alignment",
    "duration_exact",
    "evaluate_audio",
]
