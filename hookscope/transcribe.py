"""Local speech-to-text with mlx-whisper. Nothing leaves the Mac."""

from __future__ import annotations

import threading
from pathlib import Path

from . import config

_lock = threading.Lock()


class TranscribeError(Exception):
    """Transcription failed; the message is safe to show the user."""


def empty_transcript() -> dict:
    return {"language": None, "text": "", "segments": [], "words": []}


def simplify(raw: dict) -> dict:
    """Turn whisper's output (numpy floats, token lists) into small plain JSON."""
    segments, words = [], []
    for seg in raw.get("segments", []):
        text = (seg.get("text") or "").strip()
        if not text or float(seg.get("no_speech_prob") or 0) > 0.9:
            continue
        segments.append({"start": round(float(seg["start"]), 2), "end": round(float(seg["end"]), 2), "text": text})
        for w in seg.get("words") or []:
            token = (w.get("word") or "").strip()
            if token:
                words.append({"w": token, "s": round(float(w["start"]), 2), "e": round(float(w["end"]), 2)})
    return {
        "language": raw.get("language"),
        "text": " ".join(s["text"] for s in segments),
        "segments": segments,
        "words": words,
    }


def transcribe(path: Path, language: str = "") -> dict:
    if not config.WHISPER_MODEL.exists():
        raise TranscribeError(f"The speech model is missing from {config.WHISPER_MODEL}.")
    import mlx_whisper  # heavy import, kept out of app start-up

    options = {"path_or_hf_repo": str(config.WHISPER_MODEL), "word_timestamps": True,
               "condition_on_previous_text": False}
    if language:
        options["language"] = language
    try:
        with _lock:
            raw = mlx_whisper.transcribe(str(path), **options)
    except Exception as exc:  # mlx and ffmpeg errors vary
        raise TranscribeError(f"Transcription failed: {str(exc)[:200]}") from exc
    return simplify(raw)


def as_prompt_lines(transcript: dict, limit_chars: int = 30000) -> str:
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript.get("segments", [])]
    text = "\n".join(lines)
    return text if len(text) <= limit_chars else text[:limit_chars] + "\n[transcript cut for length]"
