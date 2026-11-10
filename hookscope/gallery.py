"""Photo and carousel posts via gallery-dl. Single videos stay with yt-dlp (fetch.py)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import config

GALLERY_TIMEOUT_SECONDS = 240
MAX_SLIDES = 20
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".avif"}
# Instagram /p/ links can be a photo, a carousel or a single video; gallery-dl sorts it out.
GALLERY_FIRST = (("instagram.com", re.compile(r"^/(?:[\w.]+/)?p/")),)


class GalleryError(Exception):
    """gallery-dl failed; the message is safe to show the user."""

    def __init__(self, message: str, unsupported: bool = False):
        super().__init__(message)
        self.unsupported = unsupported


@dataclass(frozen=True)
class Slide:
    index: int
    path: Path
    is_video: bool


@dataclass(frozen=True)
class GalleryResult:
    slides: tuple[Slide, ...]
    title: str
    author: str
    metrics: dict = field(default_factory=dict)


def prefer_gallery(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return any((host == h or host.endswith("." + h)) and rx.match(parsed.path or "") for h, rx in GALLERY_FIRST)


def find_cli() -> str | None:
    beside_python = Path(sys.executable).parent / "gallery-dl"
    return str(beside_python) if beside_python.exists() else shutil.which("gallery-dl")


def _first(meta: dict, *keys):
    for key in keys:
        value = meta.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("username") or value.get("nick")
        if value not in (None, "", [], {}):
            return value
    return None


def _date(raw) -> str | None:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(raw or ""))
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def metrics_from_meta(meta: dict) -> dict:
    caption = str(_first(meta, "description", "content", "caption", "text", "title") or "").strip()
    return {
        "views": _first(meta, "video_view_count", "view_count", "views"),
        "likes": _first(meta, "likes", "like_count", "favorite_count", "score"),
        "comments": _first(meta, "comments", "comment_count", "reply_count", "num_comments"),
        "shares": _first(meta, "repost_count", "retweet_count", "shares"),
        "followers": _first(meta, "followers", "follower_count"),
        "upload_date": _date(_first(meta, "post_date", "date")),
        "caption": caption[:2000],
        "tags": [t for t in (meta.get("tags") or []) if isinstance(t, str)][:20],
    }


def friendly_error(stderr: str) -> GalleryError:
    text = stderr.lower()
    if "no suitable extractor" in text or "unsupported url" in text:
        return GalleryError("This link isn't a post Hookscope can open.", unsupported=True)
    if any(k in text for k in ("401", "403", "429", "login", "authorization", "checkpoint", "redirect")):
        return GalleryError("The site refused to show this post. Open it in Chrome and make sure you're logged in, then press Retry.")
    if "404" in text or "not found" in text:
        return GalleryError("That post couldn't be found. It may have been deleted or be private.")
    last = next((line for line in reversed(stderr.strip().splitlines()) if line.strip()), "no details")
    return GalleryError(f"The download failed: {last[:300]}")


def order_files(raw_dir: Path) -> list[tuple[Path, dict]]:
    """Downloaded media with their metadata sidecars, in post order."""
    items = []
    for path in raw_dir.iterdir():
        suffix = path.suffix.lower()
        if suffix not in IMAGE_EXTENSIONS and suffix not in config.VIDEO_EXTENSIONS:
            continue
        sidecar = path.with_name(path.name + ".json")
        try:
            meta = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        except ValueError:
            meta = {}
        items.append((path, meta))
    return sorted(items, key=lambda item: (int(item[1].get("num") or 0), item[0].name))


def download(url: str, dest_dir: Path, cookies_browser: str | None) -> GalleryResult:
    cli = find_cli()
    if not cli:
        raise GalleryError("gallery-dl isn't installed. In the hookscope folder run: uv sync")
    raw_dir = dest_dir / "gallery_raw"
    slides_dir = dest_dir / "slides"
    for folder in (raw_dir, slides_dir):
        shutil.rmtree(folder, ignore_errors=True)
    raw_dir.mkdir(parents=True)
    args = [cli, "--write-metadata", "--no-part", "--range", f"1-{MAX_SLIDES}", "-D", str(raw_dir)]
    if cookies_browser:
        args += ["--cookies-from-browser", cookies_browser]
    try:
        done = subprocess.run(args + [url], capture_output=True, text=True, timeout=GALLERY_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GalleryError("The post took too long to download. Press Retry.") from exc
    items = order_files(raw_dir)
    if not items:
        raise friendly_error(done.stderr or done.stdout or "nothing was downloaded")
    slides_dir.mkdir(parents=True)
    slides = []
    for number, (path, _meta) in enumerate(items, start=1):
        target = slides_dir / f"s_{number:02d}{path.suffix.lower()}"
        path.replace(target)
        slides.append(Slide(index=number, path=target, is_video=target.suffix in config.VIDEO_EXTENSIONS))
    meta = items[0][1]
    shutil.rmtree(raw_dir, ignore_errors=True)
    author = str(_first(meta, "username", "author", "user", "uploader", "owner") or "").strip()
    caption = metrics_from_meta(meta)["caption"]
    title = caption.splitlines()[0][:120] if caption else f"Post by {author or 'unknown'}"
    return GalleryResult(slides=tuple(slides), title=title, author=author, metrics=metrics_from_meta(meta))
