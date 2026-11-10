"""ffmpeg helpers: probe, scene cuts, frame picking, frame grabs and contact sheets."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

SCENE_THRESHOLD = 0.32
HOOK_TIMES = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
MIN_FRAME_GAP = 0.8
FRAME_HEIGHT = 480
TILE_LONG_SIDE = 400
LABEL_HEIGHT = 30


class MediaError(Exception):
    """ffmpeg could not read the file; the message is safe to show the user."""


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool

    @property
    def vertical(self) -> bool:
        return self.height >= self.width


@dataclass(frozen=True)
class Frame:
    index: int
    time: float
    path: Path
    kind: str  # "hook" or "body"


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def probe(path: Path) -> Probe:
    result = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 60)
    try:
        data = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise MediaError("This file couldn't be read as a video.") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise MediaError("This file has no video track.")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise MediaError("This video has no length. The file may be damaged.")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = abs(int(float((video.get("tags") or {}).get("rotate", 0) or 0)))
    for side in video.get("side_data_list") or []:
        rotation = abs(int(float(side.get("rotation", rotation) or 0)))
    if rotation in (90, 270):
        width, height = height, width
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return Probe(duration=duration, width=width, height=height, has_audio=has_audio)


def trim_copy(source: Path, dest: Path, seconds: float) -> Path:
    result = _run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-t", str(seconds), "-c", "copy", str(dest)])
    if result.returncode != 0 or not dest.exists():
        raise MediaError("Couldn't shorten this long video for analysis.")
    return dest


def scene_cuts(path: Path) -> list[float]:
    vf = f"scale=320:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo"
    result = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf", vf, "-f", "null", "-"])
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
    return sorted(set(round(t, 2) for t in times))


def _spread(candidates: list[float], count: int) -> list[float]:
    if len(candidates) <= count:
        return candidates
    step = (len(candidates) - 1) / (count - 1)
    return [candidates[round(i * step)] for i in range(count)]


def pick_frame_times(duration: float, cuts: list[float], max_body: int = config.MAX_BODY_FRAMES) -> tuple[list[float], list[float]]:
    """Hook frames in the first seconds, then body frames just after cuts or evenly spaced."""
    last = max(duration - 0.1, 0.0)
    hook = [t for t in HOOK_TIMES if t < duration]
    hook = hook or [0.0]
    start = config.HOOK_WINDOW_SECONDS + MIN_FRAME_GAP
    after_cuts = [round(c + 0.3, 2) for c in cuts if start <= c + 0.3 <= last]
    even_count = max(2, min(max_body, int(duration // 4)))
    even = [round(start + (last - start) * i / max(even_count - 1, 1), 2) for i in range(even_count)] if last > start else []
    pool = sorted(set(after_cuts + even)) if len(after_cuts) < max_body // 2 else after_cuts
    body: list[float] = []
    for t in _spread(pool, max_body):
        if all(abs(t - b) >= MIN_FRAME_GAP for b in body):
            body.append(t)
    if even and last > start and (not body or last - body[-1] > 2):
        body = body[: max_body - 1] + [round(last, 2)]
    return hook, body


def grab_frames(path: Path, hook: list[float], body: list[float], out_dir: Path) -> list[Frame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Frame] = []
    for kind, times in (("hook", hook), ("body", body)):
        for t in times:
            index = len(frames) + 1
            target = out_dir / f"f_{index:04d}.jpg"
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                  "-vf", f"scale=-2:{FRAME_HEIGHT}", "-q:v", "4", str(target)], 60)
            if target.exists():
                frames.append(Frame(index=index, time=t, path=target, kind=kind))
    if not frames:
        raise MediaError("Couldn't read any frames from this video.")
    return frames


def format_time(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}.{int((seconds - whole) * 10)}"


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(frames: list[Frame], out_path: Path, columns: int) -> Path:
    """One labelled grid image, so the model sees many frames in a single picture."""
    with Image.open(frames[0].path) as first:
        ratio = first.width / first.height
    tile_w, tile_h = (int(TILE_LONG_SIDE * ratio), TILE_LONG_SIDE) if ratio <= 1 else (TILE_LONG_SIDE, int(TILE_LONG_SIDE / ratio))
    columns = max(1, min(columns, len(frames)))
    rows = -(-len(frames) // columns)
    sheet = Image.new("RGB", (columns * tile_w, rows * (tile_h + LABEL_HEIGHT)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for i, frame in enumerate(frames):
        x, y = (i % columns) * tile_w, (i // columns) * (tile_h + LABEL_HEIGHT)
        with Image.open(frame.path) as img:
            sheet.paste(img.convert("RGB").resize((tile_w, tile_h)), (x, y + LABEL_HEIGHT))
        draw.rectangle([x, y, x + tile_w, y + LABEL_HEIGHT], fill="black")
        draw.text((x + 8, y + 5), f"#{frame.index}  {format_time(frame.time)}", fill="white", font=font)
    sheet.save(out_path, quality=85)
    return out_path


SLIDE_VIEW_SIDE = 1080   # what the app shows
SLIDE_AI_SIDE = 1100     # what Claude reads; big enough for small slide text
SLIDE_LABEL_HEIGHT = 44


def _open_rgb(src: Path, scratch: Path) -> Image.Image:
    """PIL for common formats, ffmpeg for the rest (HEIC, AVIF) and for video slides."""
    try:
        with Image.open(src) as img:
            img.seek(0)
            return img.convert("RGB")
    except (OSError, ValueError):
        pass
    target = scratch.with_suffix(".src.jpg")
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(target)], 60)
    if not target.exists():
        raise MediaError(f"Couldn't read slide {src.name}.")
    with Image.open(target) as img:
        rgb = img.convert("RGB")
    target.unlink(missing_ok=True)
    return rgb


def _video_still(src: Path, scratch: Path) -> tuple[Image.Image, float]:
    duration = probe(src).duration
    target = scratch.with_suffix(".still.jpg")
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{min(1.0, duration / 2):.2f}", "-i", str(src),
          "-frames:v", "1", "-q:v", "2", str(target)], 60)
    if not target.exists():
        raise MediaError(f"Couldn't read video slide {src.name}.")
    with Image.open(target) as img:
        rgb = img.convert("RGB")
    target.unlink(missing_ok=True)
    return rgb, duration


def _fit(img: Image.Image, long_side: int) -> Image.Image:
    scale = long_side / max(img.size)
    if scale >= 1:
        return img.copy()
    return img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)


def _labelled(img: Image.Image, label: str) -> Image.Image:
    out = Image.new("RGB", (img.width, img.height + SLIDE_LABEL_HEIGHT), "black")
    out.paste(img, (0, SLIDE_LABEL_HEIGHT))
    ImageDraw.Draw(out).text((14, 10), label, fill="white", font=_font(22))
    return out


@dataclass(frozen=True)
class SlideImage:
    index: int
    view_path: Path       # clean copy shown in the app
    ai_path: Path         # labelled copy sent to Claude
    is_video: bool
    duration: float | None
    width: int
    height: int


def prepare_slides(slides: list, frames_dir: Path, ai_dir: Path) -> list[SlideImage]:
    """Normalise every slide to JPEG: a clean view copy and a labelled copy for Claude."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    ai_dir.mkdir(parents=True, exist_ok=True)
    total = len(slides)
    out = []
    for slide in slides:
        scratch = ai_dir / f"tmp_{slide.index:02d}"
        img, duration = _video_still(slide.path, scratch) if slide.is_video else (_open_rgb(slide.path, scratch), None)
        view = frames_dir / f"f_{slide.index:04d}.jpg"
        _fit(img, SLIDE_VIEW_SIDE).save(view, quality=86)
        label = f"SLIDE {slide.index} / {total}" + (f"  ·  VIDEO {duration:.0f} s" if slide.is_video else "")
        ai = ai_dir / f"s_{slide.index:02d}.jpg"
        _labelled(_fit(img, SLIDE_AI_SIDE), label).save(ai, quality=85)
        out.append(SlideImage(index=slide.index, view_path=view, ai_path=ai, is_video=slide.is_video,
                              duration=duration, width=img.width, height=img.height))
    if not out:
        raise MediaError("This post has no slides to read.")
    return out


def aspect_label(width: int, height: int) -> str:
    known = {"1:1": 1.0, "4:5": 0.8, "9:16": 0.5625, "16:9": 1.7778, "3:4": 0.75, "4:3": 1.3333}
    ratio = width / max(height, 1)
    name, value = min(known.items(), key=lambda kv: abs(kv[1] - ratio))
    return name if abs(value - ratio) < 0.04 else f"{width}x{height}"


def thumbnail_from_image(src: Path, out_path: Path) -> Path:
    with Image.open(src) as img:
        small = img.convert("RGB")
        small.thumbnail((360, 640))
        small.save(out_path, quality=80)
    return out_path


def thumbnail(frame: Frame, out_path: Path) -> Path:
    with Image.open(frame.path) as img:
        small = img.convert("RGB")
        small.thumbnail((360, 640))
        small.save(out_path, quality=80)
    return out_path
