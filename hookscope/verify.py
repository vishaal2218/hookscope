"""Keep reports honest: hook quotes must match the transcript, times must exist."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

QUOTE_MATCH_THRESHOLD = 0.75
TIME_KEYS = ("at", "start", "end")
LIST_KEYS = ("beats", "working", "better", "retention_risks", "on_screen_text", "lose_them", "fixes", "ideas")


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", (text or "").lower())).strip()


def quote_score(quote: str, transcript_text: str) -> float:
    """Best fuzzy match of the quote against any same-length window of the transcript (0..1)."""
    q, t = normalise(quote).split(), normalise(transcript_text).split()
    if not q or not t:
        return 0.0
    size = len(q)
    best = 0.0
    for start in range(0, max(len(t) - size, 0) + 1):
        window = " ".join(t[start: start + size])
        best = max(best, SequenceMatcher(None, " ".join(q), window).ratio())
        if best >= 0.99:
            break
    return round(best, 3)


def opening_line(transcript: dict, window: float = 3.5) -> str:
    words = [w["w"] for w in transcript.get("words", []) if w["s"] <= window]
    if words:
        return " ".join(words)
    segments = transcript.get("segments", [])
    return segments[0]["text"] if segments else ""


def clamp(value, duration: float):
    if not isinstance(value, (int, float)):
        return None
    return round(min(max(float(value), 0.0), max(duration, 0.0)), 1)


def _clean_item(item, duration: float):
    if not isinstance(item, dict):
        return item
    return {k: (clamp(v, duration) if k in TIME_KEYS else v) for k, v in item.items()}


def check_hook(hook: dict, transcript: dict, duration: float) -> dict:
    hook = _clean_item(hook if isinstance(hook, dict) else {}, duration)
    source = hook.get("source") or "spoken"
    if source != "spoken" or not transcript.get("text"):
        return {**hook, "quote_check": "not_spoken"}
    score = quote_score(hook.get("quote") or "", transcript["text"])
    if score >= QUOTE_MATCH_THRESHOLD:
        return {**hook, "quote_check": "verified"}
    actual = opening_line(transcript)
    if not actual:
        return {**hook, "quote_check": "unverified"}
    return {**hook, "quote": actual, "quote_check": "corrected", "model_quote": hook.get("quote")}


POST_LIST_KEYS = ("slides", "working", "better", "drop_off", "lose_them", "fixes", "ideas")


def clamp_slide(value, slide_count: int):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return int(min(max(round(value), 1), max(slide_count, 1)))


def _clean_post_item(item, slide_count: int):
    if not isinstance(item, dict):
        return item
    return {k: (clamp_slide(v, slide_count) if k == "slide" else v) for k, v in item.items()}


def clean_post_report(report: dict, transcript: dict, slide_count: int) -> dict:
    """Same honesty rules for photo and carousel posts: real slide numbers, checked spoken quotes."""
    cleaned = {k: v for k, v in report.items() if k not in POST_LIST_KEYS and k != "hook"}
    for key in POST_LIST_KEYS:
        value = report.get(key)
        cleaned[key] = [_clean_post_item(i, slide_count) for i in value] if isinstance(value, list) else []
    hook = _clean_post_item(report.get("hook") if isinstance(report.get("hook"), dict) else {}, slide_count)
    if hook.get("source") == "spoken" and transcript.get("text"):
        ok = quote_score(hook.get("quote") or "", transcript["text"]) >= QUOTE_MATCH_THRESHOLD
        hook = {**hook, "quote_check": "verified" if ok else "unverified"}
    else:
        hook = {**hook, "quote_check": "on_slide"}
    cleaned["hook"] = {**hook, "slide": hook.get("slide") or 1}
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    cleaned["scores"] = {k: max(1, min(10, int(v))) for k, v in scores.items() if isinstance(v, (int, float))}
    return cleaned


def clean_report(report: dict, transcript: dict, duration: float) -> dict:
    cleaned = {k: v for k, v in report.items() if k not in LIST_KEYS and k != "hook"}
    for key in LIST_KEYS:
        value = report.get(key)
        cleaned[key] = [_clean_item(i, duration) for i in value] if isinstance(value, list) else []
    cleaned["hook"] = check_hook(report.get("hook") or {}, transcript, duration)
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    cleaned["scores"] = {k: max(1, min(10, int(v))) for k, v in scores.items() if isinstance(v, (int, float))}
    return cleaned
