"""Measured pacing and audio signals: cuts, speech speed, dead air, loudness."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 8000
WINDOW_SECONDS = 0.5
SILENCE_DB = -42.0
MIN_SILENCE_SECONDS = 0.8
DEAD_AIR_GAP_SECONDS = 1.2
MAX_CURVE_POINTS = 120


def loudness_curve(path: Path) -> list[float]:
    """dBFS per half second of the mono mix. Empty when the file has no audio."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, timeout=600, check=False,
    )
    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return rms_db(samples, int(SAMPLE_RATE * WINDOW_SECONDS))


def rms_db(samples: np.ndarray, window: int) -> list[float]:
    if samples.size < window:
        return []
    usable = samples[: samples.size - samples.size % window].reshape(-1, window)
    rms = np.sqrt(np.mean(usable**2, axis=1))
    return [round(float(v), 1) for v in 20 * np.log10(np.maximum(rms, 1e-6))]


def silences(curve: list[float], window: float = WINDOW_SECONDS) -> list[dict]:
    spans, start = [], None
    for i, db in enumerate(curve + [0.0]):
        quiet = db < SILENCE_DB and i < len(curve)
        if quiet and start is None:
            start = i
        elif not quiet and start is not None:
            if (i - start) * window >= MIN_SILENCE_SECONDS:
                spans.append({"start": round(start * window, 1), "end": round(i * window, 1)})
            start = None
    return spans


def speech_stats(words: list[dict], duration: float) -> dict:
    if not words:
        return {"word_count": 0, "words_per_minute": 0, "first_word_at": None, "speech_ratio": 0.0, "dead_air": []}
    spoken = sum(max(w["e"] - w["s"], 0) for w in words)
    span = max(words[-1]["e"] - words[0]["s"], 1e-3)
    gaps = [
        {"start": round(a["e"], 1), "end": round(b["s"], 1)}
        for a, b in zip(words, words[1:])
        if b["s"] - a["e"] >= DEAD_AIR_GAP_SECONDS
    ]
    return {
        "word_count": len(words),
        "words_per_minute": round(len(words) / span * 60),
        "first_word_at": round(words[0]["s"], 2),
        "speech_ratio": round(min(spoken / max(duration, 1e-3), 1.0), 2),
        "dead_air": gaps,
    }


def cut_stats(cuts: list[float], duration: float) -> dict:
    bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    shots = [(a, b) for a, b in zip(bounds, bounds[1:]) if b > a]
    longest = max(shots, key=lambda s: s[1] - s[0]) if shots else (0.0, duration)
    hook_cuts = sum(1 for c in cuts if c <= 3.0)
    return {
        "cuts": len(cuts),
        "cuts_per_10s": round(len(cuts) / max(duration, 1e-3) * 10, 1),
        "average_shot_seconds": round(duration / max(len(shots), 1), 1),
        "longest_shot": {"start": round(longest[0], 1), "end": round(longest[1], 1)},
        "cuts_in_first_3s": hook_cuts,
    }


def downsample(curve: list[float], points: int = MAX_CURVE_POINTS) -> list[float]:
    if len(curve) <= points:
        return curve
    step = len(curve) / points
    return [round(max(curve[int(i * step): int((i + 1) * step)] or [curve[int(i * step)]]), 1) for i in range(points)]


def music_hint(curve: list[float], words: list[dict], window: float = WINDOW_SECONDS) -> float:
    """Share of non-speech time that is still loud: a rough sign of music or sound effects."""
    if not curve:
        return 0.0
    speaking = np.zeros(len(curve), dtype=bool)
    for w in words:
        speaking[int(w["s"] / window): int(w["e"] / window) + 1] = True
    quiet_speech = [db for db, s in zip(curve, speaking) if not s]
    if not quiet_speech:
        return 0.0
    return round(sum(1 for db in quiet_speech if db > -30) / len(quiet_speech), 2)


def compile_signals(curve: list[float], words: list[dict], cuts: list[float], duration: float) -> dict:
    return {
        "duration": round(duration, 1),
        "pacing": cut_stats(cuts, duration),
        "speech": speech_stats(words, duration),
        "audio": {
            "silences": silences(curve),
            "music_or_sfx_share": music_hint(curve, words),
            "average_db": round(float(np.mean(curve)), 1) if curve else None,
            "curve": downsample(curve),
            "curve_step_seconds": round(duration / max(len(downsample(curve)), 1), 2) if curve else None,
        },
        "cut_times": [round(c, 2) for c in cuts],
    }
