"""Paths, limits and settings shared by every module."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HOOKSCOPE_DATA", ROOT / "data"))
ANALYSES_DIR = DATA_DIR / "a"
DB_PATH = DATA_DIR / "hookscope.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"
WHISPER_MODEL = Path(os.environ.get("HOOKSCOPE_WHISPER", ROOT / "models" / "whisper-large-v3-turbo"))

HOST = "127.0.0.1"
PORT = int(os.environ.get("HOOKSCOPE_PORT", "8777"))
PORT_TRIES = 15

# Longer videos are cut to this many seconds before analysis.
MAX_ANALYSE_SECONDS = 15 * 60
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
MAX_VIDEO_HEIGHT = 720

HOOK_WINDOW_SECONDS = 3.0
MAX_BODY_FRAMES = 12
CLAUDE_TIMEOUT_SECONDS = 300

DEFAULT_SETTINGS = {
    # Browser yt-dlp reads cookies from for sites that need a login (Instagram).
    "cookies_browser": "chrome",
    # Claude model alias passed to the claude CLI. Empty means the plan default.
    "model": "",
    # Whisper language code, or empty for auto-detect.
    "language": "",
}


def ensure_dirs() -> None:
    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}


def save_settings(changes: dict) -> dict:
    merged = {**load_settings(), **{k: str(v) for k, v in changes.items() if k in DEFAULT_SETTINGS}}
    ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2))
    return merged


def analysis_dir(analysis_id: str) -> Path:
    return ANALYSES_DIR / analysis_id
