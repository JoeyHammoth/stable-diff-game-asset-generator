"""Audio postprocess ops (docs/04 §10, ticket T32).

The image chain is `downscale → snap → anchor`; the audio chain is `loop → normalize`. The
one op worth reading closely is `loop_crossfade`, because the obvious implementation is wrong:

* the source guide's `make_seamless_loop.py` fades the **midpoint** and swaps halves, which
  attenuates audio that was already continuous and leaves the real seam — A's end into B's
  start — untouched (gap analysis A5);
* here the **tail is mixed into the head** with an equal-power curve and the file is cut by
  the fade length. The new first sample is the old tail's first sample, whose predecessor is
  the new last sample, so the wrap is interior continuity rather than a fade to silence.

Equal power (`sin`/`cos`) rather than a linear ramp keeps a sustained tone at constant
loudness through the join; a linear crossfade of two correlated signals dips ~3 dB.
"""

from __future__ import annotations

import math

from .wav import SILENCE_DBFS, Audio, db_to_gain, gain_to_db


def loop_crossfade(audio: Audio, fade_s: float, *, curve: str = "equal_power") -> Audio:
    """Fold the tail into the head and shorten the file by `fade_s`.

    Output length is `frames - fade`, exactly as the plan assumes. `fade_s` of zero is a
    no-op; a fade at least as long as the file is a usage error.
    """
    fade = int(round(fade_s * audio.sample_rate))
    if fade <= 0:
        return audio
    if fade >= audio.frame_count:
        raise ValueError(
            f"crossfade {fade_s}s is not shorter than the file ({audio.duration_s:.3f}s)"
        )

    if curve not in {"equal_power", "linear"}:
        raise ValueError(f"unknown crossfade curve {curve!r}")

    kept = audio.frame_count - fade
    channels: list[tuple[float, ...]] = []
    for channel in audio.channels:
        folded = list(channel[:kept])
        for index in range(fade):
            position = (index + 1) / fade
            if curve == "equal_power":
                theta = position * math.pi / 2.0
                incoming = math.sin(theta)
                outgoing = math.cos(theta)
            else:
                incoming = position
                outgoing = 1.0 - position
            folded[index] = channel[index] * incoming + channel[kept + index] * outgoing
        channels.append(tuple(folded))
    return Audio(channels=tuple(channels), sample_rate=audio.sample_rate)


def loudness_normalize(audio: Audio, target_dbfs: float = -3.0) -> Audio:
    """Scale to a peak target. Peak, not RMS: the gates measure peak and clipping is peak."""
    peak = audio.peak()
    if peak <= 0.0:
        raise ValueError("cannot normalize silence: the file has no audible samples")
    return audio.scaled(db_to_gain(target_dbfs) / peak)


def trim_silence(audio: Audio, threshold_dbfs: float = -60.0) -> Audio:
    """Drop leading and trailing near-silence, keeping at least one audible sample.

    Used for one-shots only. Trimming a loop would break its bar alignment, so the music
    chain never runs it.
    """
    floor = db_to_gain(threshold_dbfs)
    samples = audio.mono()
    audible = [index for index, value in enumerate(samples) if abs(value) >= floor]
    if not audible:
        raise ValueError(f"the file is silent below {threshold_dbfs} dBFS")
    return audio.slice_samples(audible[0], audible[-1] + 1)


def fade_edges(audio: Audio, fade_s: float = 0.005) -> Audio:
    """Linear fade in and out. For one-shots: a click starting at full amplitude is audible."""
    fade = int(round(fade_s * audio.sample_rate))
    if fade <= 0:
        return audio
    if 2 * fade > audio.frame_count:
        raise ValueError(f"fade {fade_s}s does not fit in {audio.duration_s:.3f}s of audio")

    channels: list[tuple[float, ...]] = []
    for channel in audio.channels:
        shaped = list(channel)
        for index in range(fade):
            ramp = (index + 1) / (fade + 1)
            shaped[index] *= ramp
            shaped[-1 - index] *= ramp
        channels.append(tuple(shaped))
    return Audio(channels=tuple(channels), sample_rate=audio.sample_rate)


def mix(melody: Audio, bed: Audio | None, *, melody_gain_db: float = 0.0) -> Audio:
    """Sum the authored melody over a backing bed at a fixed gain.

    The melody is mixed in, never prompted for: that is what keeps it sample-exact across
    tracks (docs/04 §10 step 4). With no bed this is just the melody at its gain.
    """
    gain = db_to_gain(melody_gain_db)
    melody_channels = tuple(tuple(value * gain for value in channel) for channel in melody.channels)
    if bed is None:
        return Audio(channels=melody_channels, sample_rate=melody.sample_rate)
    if bed.sample_rate != melody.sample_rate:
        raise ValueError(f"sample rates differ: melody {melody.sample_rate}, bed {bed.sample_rate}")
    if bed.frame_count < melody.frame_count:
        raise ValueError("the bed is shorter than the melody")
    channels = tuple(
        tuple(a + b for a, b in zip(melody_channel, bed_channel, strict=False))
        for melody_channel, bed_channel in zip(melody_channels, bed.channels, strict=True)
    )
    return Audio(channels=channels, sample_rate=melody.sample_rate)


def peak_report(audio: Audio) -> dict[str, float]:
    """The numbers a job record needs about its artifact, measured once."""
    return {
        "duration_s": round(audio.duration_s, 6),
        "peak_dbfs": round(audio.peak_dbfs(), 3),
        "rms_dbfs": round(gain_to_db(audio.rms()), 3) if audio.rms() > 0 else SILENCE_DBFS,
    }


__all__ = [
    "fade_edges",
    "loop_crossfade",
    "loudness_normalize",
    "mix",
    "peak_report",
    "trim_silence",
]
