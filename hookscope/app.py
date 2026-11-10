"""The local web API and page server. Listens on 127.0.0.1 only."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import brain, config, db, fetch, gallery, generate, pipeline
from .pipeline import read_json

ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "testserver"}
MEDIA_NAME = re.compile(r"^(video|trimmed)\.(mp4|mov|m4v|webm|mkv|avi)$|^thumb\.jpg$|^sheet_[12]\.jpg$|^frames/f_\d{4}\.jpg$"
                        r"|^slides/s_\d{2}\.(mp4|mov|m4v|webm)$")
MODES = {"breakdown", "draft"}
CHUNK = 1024 * 1024

@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    db.connect()
    pipeline.start_worker()
    pipeline.recover()
    yield


app = FastAPI(title="Hookscope", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Blocks DNS-rebinding and other websites posting to this server from the browser.
    if request.headers.get("host", "").rsplit(":", 1)[0] not in ALLOWED_HOSTNAMES:
        return PlainTextResponse("Forbidden host", status_code=403)
    if request.method not in ("GET", "HEAD") and request.headers.get("x-hookscope") != "1":
        return PlainTextResponse("Missing app header", status_code=403)
    response = await call_next(request)
    # The page is split into many script files; make Chrome re-check them every load so it never
    # mixes an old cached file with new ones (the ETag keeps this a cheap 304 when nothing changed).
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _need(row: dict | None, what: str = "Not found") -> dict:
    if row is None:
        raise HTTPException(404, what)
    return row


def _public(analysis: dict, full: bool = False) -> dict:
    folder = config.analysis_dir(analysis["id"])
    out = {**analysis, "has_thumb": (folder / "thumb.jpg").exists(),
           "queue_position": pipeline.queue_position(analysis["id"]) if analysis["status"] == "queued" else 0}
    if not full:
        report = analysis.get("report") or {}
        return {**{k: v for k, v in out.items() if k != "report"},
                "summary": report.get("summary") or report.get("verdict_reason"),
                "verdict": report.get("verdict"), "format": report.get("format")}
    video = next((p.name for p in sorted(folder.glob("trimmed.*")) + sorted(folder.glob("video.*"))
                  if MEDIA_NAME.match(p.name)), None)
    return {**out, "video": video,
            "transcript": read_json(folder / "transcript.json", None),
            "frames": read_json(folder / "frames.json", []),
            "signals": read_json(folder / "signals.json", None)}


# Analyses ---------------------------------------------------------------

class LinkIn(BaseModel):
    url: str = Field(max_length=2000)
    mode: str = "breakdown"
    note: str = Field("", max_length=1000)
    is_mine: bool = False


@app.post("/api/analyses")
def create_from_link(body: LinkIn) -> dict:
    if body.mode not in MODES:
        raise HTTPException(400, "Unknown mode")
    try:
        url = fetch.validate_url(body.url)
    except fetch.FetchError as exc:
        raise HTTPException(400, str(exc)) from exc
    row = db.create_analysis({"mode": body.mode, "source_url": url, "platform": fetch.platform_of(url),
                              "note": body.note.strip(), "is_mine": int(body.is_mine or body.mode == "draft")})
    pipeline.submit(row["id"])
    return _public(db.get_analysis(row["id"]))


def upload_plan(names: list[str]) -> tuple[str, list[str]]:
    """Decide what an upload is: one video, or a photo / carousel of up to 20 images and clips."""
    suffixes = [Path(n or "").suffix.lower() for n in names]
    allowed = config.VIDEO_EXTENSIONS | gallery.IMAGE_EXTENSIONS
    if not suffixes or any(s not in allowed for s in suffixes):
        raise HTTPException(400, "Use a video file, or images (JPG, PNG, WebP, HEIC) for a photo or carousel post.")
    if len(suffixes) == 1 and suffixes[0] in config.VIDEO_EXTENSIONS:
        return "video", [f"video{suffixes[0]}"]
    if len(suffixes) > gallery.MAX_SLIDES:
        raise HTTPException(400, f"A carousel can have at most {gallery.MAX_SLIDES} slides.")
    if all(s in config.VIDEO_EXTENSIONS for s in suffixes):
        raise HTTPException(400, "Drop one video at a time, or images for a carousel.")
    kind = fetch.kind_for(len(suffixes))
    return kind, [f"slides/s_{i:02d}{s}" for i, s in enumerate(suffixes, start=1)]


async def _save_upload(file: UploadFile, target: Path, budget: int) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(target, "wb") as out:
        while chunk := await file.read(CHUNK):
            written += len(chunk)
            if written > budget:
                raise HTTPException(413, "That upload is over 1 GB.")
            out.write(chunk)
    return written


@app.post("/api/analyses/upload")
async def create_from_upload(files: list[UploadFile] = File(...), mode: str = Form("draft"), note: str = Form(""),
                             is_mine: bool = Form(True)) -> dict:
    if mode not in MODES:
        raise HTTPException(400, "Unknown mode")
    kind, targets = upload_plan([f.filename for f in files])
    first = Path(files[0].filename or "upload").stem[:200]
    title = first if kind == "video" else f"{'Carousel' if kind == 'carousel' else 'Photo'}: {first}"
    row = db.create_analysis({"mode": mode, "source_url": None, "platform": "upload", "note": note.strip()[:1000],
                              "title": title, "is_mine": int(is_mine), "kind": kind})
    folder = config.analysis_dir(row["id"])
    budget = config.MAX_UPLOAD_BYTES
    try:
        for file, target in zip(files, targets):
            budget -= await _save_upload(file, folder / target, budget)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        db.delete_analysis(row["id"])
        raise
    pipeline.submit(row["id"])
    return _public(db.get_analysis(row["id"]))


@app.get("/api/analyses")
def list_analyses(q: str = "") -> list[dict]:
    return [_public(a) for a in db.list_analyses(q.strip()[:200])]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    return _public(_need(db.get_analysis(analysis_id)), full=True)


class AnalysisPatch(BaseModel):
    is_mine: bool | None = None


@app.patch("/api/analyses/{analysis_id}")
def patch_analysis(analysis_id: str, body: AnalysisPatch) -> dict:
    _need(db.get_analysis(analysis_id))
    if body.is_mine is not None:
        db.update_analysis(analysis_id, {"is_mine": int(body.is_mine)})
    return _public(db.get_analysis(analysis_id), full=True)


@app.post("/api/analyses/{analysis_id}/retry")
def retry_analysis(analysis_id: str) -> dict:
    row = _need(db.get_analysis(analysis_id))
    if row["status"] in ("queued", "running"):
        raise HTTPException(409, "It's already running.")
    pipeline.submit(analysis_id)
    return _public(db.get_analysis(analysis_id))


@app.delete("/api/analyses/{analysis_id}")
def delete_analysis(analysis_id: str) -> dict:
    row = _need(db.get_analysis(analysis_id))
    if row["status"] == "running":
        raise HTTPException(409, "Wait for it to finish, then delete it.")
    db.delete_analysis(analysis_id)
    shutil.rmtree(config.analysis_dir(analysis_id), ignore_errors=True)
    return {"deleted": analysis_id}


@app.get("/media/{analysis_id}/{name:path}")
def media(analysis_id: str, name: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{12}", analysis_id) or not MEDIA_NAME.match(name):
        raise HTTPException(404, "Not found")
    path = config.analysis_dir(analysis_id) / name
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path)


# Profile ----------------------------------------------------------------

@app.get("/api/profile")
def get_profile() -> dict:
    return db.get_profile()


@app.put("/api/profile")
def put_profile(body: dict) -> dict:
    return db.save_profile(body)


@app.post("/api/profile/learn")
def learn_profile() -> dict:
    try:
        return generate.learn_voice()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# Scripts ----------------------------------------------------------------

class ScriptIn(BaseModel):
    idea: dict
    analysis_id: str | None = None


@app.post("/api/scripts")
def create_script(body: ScriptIn) -> dict:
    return generate.generate_script(body.idea, body.analysis_id)


@app.get("/api/scripts")
def list_scripts() -> list[dict]:
    return db.list_scripts()


@app.get("/api/scripts/{script_id}")
def get_script(script_id: str) -> dict:
    return _need(db.get_script(script_id))


class ScriptText(BaseModel):
    edited_text: str | None = Field(None, max_length=50000)


@app.put("/api/scripts/{script_id}")
def put_script(script_id: str, body: ScriptText) -> dict:
    _need(db.get_script(script_id))
    return db.update_script_text(script_id, body.edited_text)


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: str) -> dict:
    db.delete_script(script_id)
    return {"deleted": script_id}


# Tools, chat, plans -----------------------------------------------------

class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@app.get("/api/tools")
def list_tools() -> list[dict]:
    return [{"key": k, "name": n, "label": label} for k, (n, label, _task) in generate.TOOLS.items()]


@app.post("/api/tools/{tool}")
def run_tool(tool: str, body: TextIn) -> dict:
    if tool not in generate.TOOLS:
        raise HTTPException(404, "Unknown tool")
    return generate.run_tool(tool, body.text)


@app.get("/api/chat")
def get_chat() -> list[dict]:
    return db.list_chat()


@app.post("/api/chat")
def post_chat(body: TextIn) -> dict:
    return generate.chat(body.text)


@app.delete("/api/chat")
def clear_chat() -> dict:
    db.clear_chat()
    return {"cleared": True}


class PlanIn(BaseModel):
    analysis_ids: list[str] = Field(default_factory=list, max_length=60)


@app.post("/api/plans")
def create_plan(body: PlanIn) -> dict:
    try:
        return generate.make_plan(body.analysis_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plans")
def list_plans() -> list[dict]:
    return db.list_plans()


class PlanDone(BaseModel):
    done: list[int]


@app.patch("/api/plans/{plan_id}")
def patch_plan(plan_id: str, body: PlanDone) -> dict:
    _need(db.get_plan(plan_id))
    return db.set_plan_done(plan_id, body.done)


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: str) -> dict:
    db.delete_plan(plan_id)
    return {"deleted": plan_id}


# Settings and health ----------------------------------------------------

def _version(args: list[str]) -> str | None:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (done.stdout or done.stderr).splitlines()[0].strip() if done.returncode == 0 else None


class ClientLog(BaseModel):
    kind: str = Field("error", max_length=40)
    message: str = Field("", max_length=4000)
    source: str = Field("", max_length=400)
    line: int | None = None
    page: str = Field("", max_length=400)
    agent: str = Field("", max_length=400)


@app.post("/api/client-log")
def client_log(body: ClientLog) -> dict:
    """Errors from the browser page, so a blank screen leaves a trace in data/hookscope.log."""
    logging.getLogger("hookscope.page").warning(
        "page %s: %s | %s:%s | %s | %s", body.kind, body.message, body.source, body.line, body.page, body.agent)
    return {"logged": True}


@app.get("/api/ping")
def ping() -> dict:
    return {"app": "hookscope"}


@app.get("/api/health")
def health() -> dict:
    import yt_dlp.version

    ffmpeg = _version(["ffmpeg", "-version"])
    return {
        "ytdlp": {"ok": True, "detail": yt_dlp.version.__version__},
        "ffmpeg": {"ok": bool(ffmpeg), "detail": ffmpeg or "not found: brew install ffmpeg"},
        "whisper": {"ok": config.WHISPER_MODEL.exists(), "detail": str(config.WHISPER_MODEL)},
        "claude": brain.auth_status(),
        "browser": fetch.browser_access(config.load_settings().get("cookies_browser", "")),
        "disk_free_gb": round(shutil.disk_usage(config.DATA_DIR).free / 1e9, 1),
        "data_dir": str(config.DATA_DIR),
    }


FULL_DISK_ACCESS_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


@app.post("/api/open-privacy-settings")
def open_privacy_settings() -> dict:
    """Opens System Settings at Full Disk Access. It only opens the page; the user flips the switch."""
    subprocess.run(["open", FULL_DISK_ACCESS_PANE], check=False, timeout=10)
    return {"opened": True}


@app.get("/api/settings")
def get_settings() -> dict:
    return config.load_settings()


@app.put("/api/settings")
def put_settings(body: dict) -> dict:
    return config.save_settings(body)


@app.exception_handler(brain.BrainError)
def brain_error(_request: Request, exc: brain.BrainError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=502)


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")
