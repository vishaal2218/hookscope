"""Download a video and its public numbers from a link, using yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import download_range_func

from . import config, gallery

# Sites where anonymous access usually fails, so cookies are sent from the start.
LOGIN_SITES = {"instagram", "facebook", "threads"}

PLATFORM_HOSTS = {
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "x": ("twitter.com", "x.com"),
    "facebook": ("facebook.com", "fb.watch"),
    "threads": ("threads.net", "threads.com"),
    "linkedin": ("linkedin.com",),
    "vimeo": ("vimeo.com",),
    "reddit": ("reddit.com", "redd.it"),
    "snapchat": ("snapchat.com",),
}


class FetchError(Exception):
    """A download failed; the message is safe to show the user."""


# Where each browser keeps the cookies yt-dlp and gallery-dl read for logged-in sites.
BROWSER_DATA = {
    "chrome": "Library/Application Support/Google/Chrome",
    "brave": "Library/Application Support/BraveSoftware/Brave-Browser",
    "edge": "Library/Application Support/Microsoft Edge",
    "firefox": "Library/Application Support/Firefox/Profiles",
    "safari": "Library/Containers/com.apple.Safari/Data/Library/Cookies",
}
PRIVACY_BLOCKED = ("Hookscope can't read your browser's login because macOS is blocking it. "
                   "Open Hookscope's Settings page and click Fix browser access (a one-time switch), then press Retry.")


def browser_access(browser: str) -> dict:
    """Can this process read the browser's data folder? macOS privacy can block apps (not Terminal)."""
    if not browser:
        return {"ok": True, "state": "off", "detail": "not using a browser login"}
    relative = BROWSER_DATA.get(browser)
    if not relative:
        return {"ok": False, "state": "unknown", "detail": f"unknown browser {browser}"}
    folder = Path.home() / relative
    try:
        next(iter(folder.iterdir()), None)
    except PermissionError:
        return {"ok": False, "state": "blocked", "detail": "blocked by macOS privacy: give Hookscope Full Disk Access"}
    except FileNotFoundError:
        return {"ok": False, "state": "missing", "detail": f"{browser.title()} doesn't seem to be installed or used yet"}
    except OSError as exc:
        return {"ok": False, "state": "blocked", "detail": f"can't read it ({exc.strerror or exc})"}
    return {"ok": True, "state": "ok", "detail": f"{browser.title()} login readable"}


@dataclass(frozen=True)
class FetchResult:
    video_path: Path | None
    platform: str
    title: str
    author: str
    duration: float
    truncated: bool
    metrics: dict = field(default_factory=dict)
    kind: str = "video"  # video | photo | carousel
    slides: tuple = ()


def kind_for(slide_count: int) -> str:
    return "carousel" if slide_count > 1 else "photo"


NO_VIDEO_HINTS = ("no video", "unsupported url", "there is no video", "no media", "not a video")


def validate_url(raw: str) -> str:
    url = (raw or "").strip()
    # Links copied from apps often drop the scheme: "instagram.com/reel/..."
    if url and "://" not in url and re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", url):
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
        raise FetchError("That doesn't look like a web link. Paste the full link, starting with https://")
    return url


def platform_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, hosts in PLATFORM_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return name
    return "web"


def format_upload_date(raw: str | None) -> str | None:
    if not raw or not re.fullmatch(r"\d{8}", raw):
        return None
    return f"{raw[6:8]}-{raw[4:6]}-{raw[0:4]}"


def metrics_from_info(info: dict) -> dict:
    description = (info.get("description") or "").strip()
    return {
        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "shares": info.get("repost_count"),
        "followers": info.get("channel_follower_count"),
        "upload_date": format_upload_date(info.get("upload_date")),
        "caption": description[:2000],
        "tags": (info.get("tags") or [])[:20],
    }


def friendly_error(message: str, platform: str) -> str:
    text = message.lower()
    if "unsupported url" in text:
        return "This link isn't a single video Hookscope can open. Use the link to one post, reel, short or video, not a profile or a feed."
    if "no video formats" in text or "there is no video" in text:
        return "This post has no video (it may be a photo or a carousel). Hookscope analyses videos."
    if "private" in text:
        return "This video is private, so it can't be opened."
    if ("cookies" in text and "could not" in text) or "operation not permitted" in text:
        return PRIVACY_BLOCKED
    if any(k in text for k in ("login required", "log in", "rate-limit", "rate limit", "not available", "sign in to confirm")):
        if platform in LOGIN_SITES:
            return "Instagram refused the download. Open instagram.com in Chrome, make sure you're logged in, then press Retry. You can also save the reel and drop the file in instead."
        return "The site asked for a login or blocked the download. Try again in a minute, or download the video yourself and drop the file in."
    if "http error 404" in text or "not found" in text:
        return "That video couldn't be found. It may have been deleted."
    return f"The download failed: {message.strip()[:300]}"


def _base_options(dest_dir: Path, cookies_browser: str | None) -> dict:
    opts = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "format": f"bv*[height<={config.MAX_VIDEO_HEIGHT}]+ba/b[height<={config.MAX_VIDEO_HEIGHT}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "video.%(ext)s"),
        "retries": 3,
        "socket_timeout": 30,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser, None, None, None)
    return opts


def _first_video(info: dict) -> dict:
    entries = info.get("entries")
    if not entries:
        return info
    for entry in entries:
        if entry and (entry.get("formats") or entry.get("url")):
            return entry
    raise FetchError("This post has no video (it may be a photo or a carousel). Hookscope analyses videos.")


def _download(url: str, dest_dir: Path, cookies_browser: str | None) -> tuple[dict, bool]:
    opts = _base_options(dest_dir, cookies_browser)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = _first_video(ydl.extract_info(url, download=False))
    duration = float(info.get("duration") or 0)
    truncated = duration > config.MAX_ANALYSE_SECONDS
    if truncated:
        opts = {**opts, "download_ranges": download_range_func(None, [(0, config.MAX_ANALYSE_SECONDS)]),
                "force_keyframes_at_cuts": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.process_ie_result(info, download=True)
    return info, truncated


def _find_video(dest_dir: Path) -> Path:
    found = sorted(p for p in dest_dir.glob("video.*") if p.suffix.lower() in config.VIDEO_EXTENSIONS)
    if not found:
        raise FetchError("The download finished but no video file was saved. Try again, or drop the file in.")
    return found[0]


def from_gallery(url: str, dest_dir: Path, browser: str | None, platform: str) -> FetchResult:
    """Photo / carousel posts. A post that is one video goes down the video path."""
    result = gallery.download(url, dest_dir, browser)
    if len(result.slides) == 1 and result.slides[0].is_video:
        only = result.slides[0].path
        video = only.replace(dest_dir / f"video{only.suffix}")
        return FetchResult(video_path=video, platform=platform, title=result.title, author=result.author,
                           duration=0.0, truncated=False, metrics=result.metrics)
    return FetchResult(video_path=None, platform=platform, title=result.title, author=result.author, duration=0.0,
                       truncated=False, metrics=result.metrics, kind=kind_for(len(result.slides)), slides=result.slides)


def _video(url: str, dest_dir: Path, browser: str | None, platform: str) -> FetchResult:
    # Public sites first try without cookies; login sites go straight to cookies.
    attempts = [browser] if platform in LOGIN_SITES else [None, browser]
    last_error = ""
    for cookies in dict.fromkeys(attempts):
        try:
            info, truncated = _download(url, dest_dir, cookies)
            return FetchResult(
                video_path=_find_video(dest_dir),
                platform=platform,
                title=(info.get("title") or "").strip()[:300],
                author=(info.get("uploader") or info.get("channel") or info.get("uploader_id") or "").strip(),
                duration=float(info.get("duration") or 0),
                truncated=truncated,
                metrics=metrics_from_info(info),
            )
        except FetchError as exc:
            last_error = str(exc)
            break
        except Exception as exc:  # yt-dlp raises many types; all mean "this attempt failed"
            last_error = str(exc)
    raise FetchError(last_error)


def fetch(url: str, dest_dir: Path, cookies_browser: str = "chrome") -> FetchResult:
    url = validate_url(url)
    platform = platform_of(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    browser = (cookies_browser or "").strip() or None
    # Say the real reason up front instead of a confusing download error later.
    if browser and platform in LOGIN_SITES and browser_access(browser)["state"] == "blocked":
        raise FetchError(PRIVACY_BLOCKED)
    try:
        if gallery.prefer_gallery(url):
            return from_gallery(url, dest_dir, browser, platform)
    except gallery.GalleryError:
        pass  # the video path below gets its own chance
    try:
        return _video(url, dest_dir, browser, platform)
    except FetchError as exc:
        video_error = str(exc)
    if not any(h in video_error.lower() for h in NO_VIDEO_HINTS) or gallery.prefer_gallery(url):
        raise FetchError(friendly_error(video_error, platform))
    try:
        return from_gallery(url, dest_dir, browser, platform)
    except gallery.GalleryError as exc:
        raise FetchError(friendly_error(video_error, platform) if exc.unsupported else str(exc)) from exc
