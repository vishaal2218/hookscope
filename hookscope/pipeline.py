"""The five-step analysis job, run one at a time on a background worker."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import traceback
from pathlib import Path

from . import brain, config, db, fetch, gallery, media, prompts, signals, transcribe, verify

log = logging.getLogger("hookscope.pipeline")

STEPS = (
    ("fetch", "Getting the video"),
    ("transcribe", "Listening: transcript"),
    ("watch", "Watching: key frames"),
    ("measure", "Measuring pacing and audio"),
    ("judge", "Writing the report"),
)
POST_LABELS = {
    "fetch": "Getting the post",
    "transcribe": "Listening: video slides",
    "watch": "Reading the slides",
    "measure": "Measuring the post",
    "judge": "Writing the report",
}
POST_KINDS = ("photo", "carousel")
KNOWN_ERRORS = (fetch.FetchError, media.MediaError, transcribe.TranscribeError, brain.BrainError)
INTERRUPTED = "Hookscope was closed while this was running. Press Retry."

_jobs: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None


def is_post(kind: str | None) -> bool:
    return kind in POST_KINDS


def fresh_steps(kind: str | None = "video") -> list[dict]:
    return [{"key": k, "label": POST_LABELS[k] if is_post(kind) else label, "status": "waiting", "started": None,
             "ended": None} for k, label in STEPS]


def relabel(steps: list[dict], kind: str) -> list[dict]:
    if not is_post(kind):
        return steps
    return [{**s, "label": POST_LABELS.get(s["key"], s["label"])} for s in steps]


def uploaded_slides(folder: Path) -> list[gallery.Slide]:
    files = sorted(p for p in (folder / "slides").glob("s_*")
                   if p.suffix.lower() in gallery.IMAGE_EXTENSIONS | config.VIDEO_EXTENSIONS)
    return [gallery.Slide(index=i, path=p, is_video=p.suffix.lower() in config.VIDEO_EXTENSIONS)
            for i, p in enumerate(files, start=1)]


def _mark(steps: list[dict], key: str, status: str) -> list[dict]:
    stamp = round(time.time(), 2)
    out = []
    for step in steps:
        if step["key"] != key:
            out.append(step)
        elif status == "running":
            out.append({**step, "status": status, "started": stamp, "ended": None})
        else:
            out.append({**step, "status": status, "ended": stamp})
    return out


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False))


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class _Run:
    """Holds one job's state while it moves through the steps."""

    def __init__(self, analysis: dict):
        self.id = analysis["id"]
        self.analysis = analysis
        self.folder = config.analysis_dir(self.id)
        self.kind = analysis.get("kind") or "video"
        self.steps = fresh_steps(self.kind)
        self.video: Path | None = None
        self.slides: list[gallery.Slide] = []
        self.truncated = False

    @property
    def post(self) -> bool:
        return is_post(self.kind)

    def step(self, key: str, status: str) -> None:
        self.steps = _mark(self.steps, key, status)
        db.update_analysis(self.id, {"steps": self.steps})

    def do_fetch(self) -> None:
        if self.analysis.get("source_url"):
            result = fetch.fetch(self.analysis["source_url"], self.folder, config.load_settings()["cookies_browser"])
            self.video, self.truncated, self.kind = result.video_path, result.truncated, result.kind
            self.slides = list(result.slides)
            self.steps = relabel(self.steps, self.kind)
            db.update_analysis(self.id, {"platform": result.platform, "title": result.title, "kind": self.kind,
                                         "author": result.author, "metrics": result.metrics, "steps": self.steps})
            if self.post:
                return
        elif self.post:
            self.slides = uploaded_slides(self.folder)
            if not self.slides:
                raise media.MediaError("The uploaded images are missing. Please add them again.")
            return
        else:
            found = sorted(p for p in self.folder.glob("video.*") if p.suffix.lower() in config.VIDEO_EXTENSIONS)
            if not found:
                raise media.MediaError("The uploaded file is missing. Please add it again.")
            self.video = found[0]
        probe = media.probe(self.video)
        if probe.duration > config.MAX_ANALYSE_SECONDS + 1:
            self.video = media.trim_copy(self.video, self.folder / f"trimmed{self.video.suffix}", config.MAX_ANALYSE_SECONDS)
            self.truncated = True
            probe = media.probe(self.video)
        self.probe = probe
        db.update_analysis(self.id, {"duration": round(probe.duration, 2)})

    def do_transcribe(self) -> None:
        language = config.load_settings().get("language", "")
        if self.post:
            self.transcript = self._slide_speech(language)
        else:
            self.transcript = transcribe.transcribe(self.video, language) if self.probe.has_audio else transcribe.empty_transcript()
        _write_json(self.folder / "transcript.json", self.transcript)

    def _slide_speech(self, language: str) -> dict:
        """Speech from video slides only, each segment tagged with its slide number."""
        segments, words, texts = [], [], []
        for slide in (s for s in self.slides if s.is_video):
            if not media.probe(slide.path).has_audio:
                continue
            part = transcribe.transcribe(slide.path, language)
            segments += [{**seg, "slide": slide.index} for seg in part["segments"]]
            words += part["words"]
            texts += [f"[slide {slide.index}] {part['text']}"] if part["text"] else []
        return {"language": None, "text": " ".join(texts), "segments": segments, "words": words}

    def do_watch(self) -> None:
        if self.post:
            self._read_slides()
            return
        self.cuts = media.scene_cuts(self.video)
        hook_times, body_times = media.pick_frame_times(self.probe.duration, self.cuts)
        frames = media.grab_frames(self.video, hook_times, body_times, self.folder / "frames")
        hook = [f for f in frames if f.kind == "hook"]
        body = [f for f in frames if f.kind == "body"]
        vertical = self.probe.vertical
        self.sheets = [media.contact_sheet(hook, self.folder / "sheet_1.jpg", 3 if vertical else 2)]
        if body:
            self.sheets.append(media.contact_sheet(body, self.folder / "sheet_2.jpg", 4 if vertical else 3))
        media.thumbnail(hook[min(2, len(hook) - 1)] if hook else frames[0], self.folder / "thumb.jpg")
        _write_json(self.folder / "frames.json",
                    [{"index": f.index, "time": f.time, "kind": f.kind, "file": f.path.name} for f in frames])

    def _read_slides(self) -> None:
        self.slide_images = media.prepare_slides(self.slides, self.folder / "frames", self.folder / "ai")
        media.thumbnail_from_image(self.slide_images[0].view_path, self.folder / "thumb.jpg")
        _write_json(self.folder / "frames.json", [
            {"index": s.index, "time": None, "kind": "slide", "slide": s.index, "file": s.view_path.name,
             "video": next((sl.path.name for sl in self.slides if sl.index == s.index and sl.is_video), None),
             "duration": round(s.duration, 1) if s.duration else None}
            for s in self.slide_images])

    def do_measure(self) -> None:
        if self.post:
            first = self.slide_images[0]
            video_seconds = sum(s.duration or 0 for s in self.slide_images)
            self.signals = {
                "kind": self.kind, "slides": len(self.slide_images),
                "video_slides": sum(1 for s in self.slide_images if s.is_video),
                "image_slides": sum(1 for s in self.slide_images if not s.is_video),
                "aspect": media.aspect_label(first.width, first.height),
                "video_seconds": round(video_seconds, 1),
                "speech": signals.speech_stats(self.transcript["words"], video_seconds) if self.transcript["words"] else None,
            }
        else:
            curve = signals.loudness_curve(self.video) if self.probe.has_audio else []
            self.signals = signals.compile_signals(curve, self.transcript["words"], self.cuts, self.probe.duration)
        _write_json(self.folder / "signals.json", self.signals)

    def do_judge(self) -> None:
        if self.post:
            self._judge_post()
            return
        latest = db.get_analysis(self.id)
        material = prompts.material_block(latest, transcribe.as_prompt_lines(self.transcript), self.signals, self.truncated)
        profile = prompts.profile_block(db.get_profile())
        note = (latest.get("note") or "").strip()
        build = prompts.draft_prompt if latest["mode"] == "draft" else prompts.breakdown_prompt
        raw = brain.ask_json(build(material, profile, note), prompts.SYSTEM, self.sheets)
        report = verify.clean_report(raw, self.transcript, self.probe.duration)
        db.update_analysis(self.id, {"report": {**report, "truncated": self.truncated}})

    def _judge_post(self) -> None:
        latest = db.get_analysis(self.id)
        lines = "\n".join(f"[slide {s['slide']}, {s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in self.transcript["segments"])
        material = prompts.post_material_block(latest, self.signals, lines)
        profile = prompts.profile_block(db.get_profile())
        note = (latest.get("note") or "").strip()
        build = prompts.post_draft_prompt if latest["mode"] == "draft" else prompts.post_breakdown_prompt
        images = [s.ai_path for s in self.slide_images[: gallery.MAX_SLIDES]]
        raw = brain.ask_json(build(material, profile, note), prompts.SYSTEM, images)
        report = verify.clean_post_report(raw, self.transcript, len(self.slide_images))
        db.update_analysis(self.id, {"report": report})


def run(analysis_id: str) -> None:
    analysis = db.get_analysis(analysis_id)
    if not analysis:
        return
    job = _Run(analysis)
    job.folder.mkdir(parents=True, exist_ok=True)
    db.update_analysis(analysis_id, {"status": "running", "error": None, "steps": job.steps})
    current = None
    try:
        for key, _label in STEPS:
            current = key
            job.step(key, "running")
            getattr(job, f"do_{key}")()
            job.step(key, "done")
        db.update_analysis(analysis_id, {"status": "done"})
    except KNOWN_ERRORS as exc:
        _fail(job, current, str(exc))
    except Exception as exc:  # anything unexpected: keep the trace on disk, show a short reason
        (job.folder / "error.log").write_text(traceback.format_exc())
        log.exception("analysis %s failed", analysis_id)
        _fail(job, current, f"Something went wrong ({type(exc).__name__}: {str(exc)[:200]}). Press Retry.")


def _fail(job: _Run, step_key: str | None, message: str) -> None:
    if step_key:
        job.step(step_key, "failed")
    db.update_analysis(job.id, {"status": "failed", "error": message})


def _loop() -> None:
    while True:
        analysis_id = _jobs.get()
        try:
            run(analysis_id)
        finally:
            _jobs.task_done()


def start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_loop, name="hookscope-worker", daemon=True)
        _worker.start()


def submit(analysis_id: str) -> None:
    row = db.get_analysis(analysis_id) or {}
    db.update_analysis(analysis_id, {"status": "queued", "error": None, "steps": fresh_steps(row.get("kind"))})
    _jobs.put(analysis_id)


def recover() -> None:
    """After a restart: running jobs were cut off, queued jobs go back in line."""
    for row in db.analyses_with_status("running"):
        db.update_analysis(row["id"], {"status": "failed", "error": INTERRUPTED})
    for row in db.analyses_with_status("queued"):
        _jobs.put(row["id"])


def queue_position(analysis_id: str) -> int:
    waiting = [r["id"] for r in db.analyses_with_status("queued")]
    return waiting.index(analysis_id) + 1 if analysis_id in waiting else 0
