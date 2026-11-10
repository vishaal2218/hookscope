"""API tests with the pipeline and Claude replaced by fakes."""

import re

import pytest
from fastapi.testclient import TestClient

from hookscope import app as app_module
from hookscope import brain, db, pipeline

H = {"X-Hookscope": "1"}


@pytest.fixture
def client(monkeypatch):
    submitted = []
    monkeypatch.setattr(pipeline, "submit", lambda analysis_id: submitted.append(analysis_id))
    monkeypatch.setattr(pipeline, "start_worker", lambda: None)
    with TestClient(app_module.app) as c:
        c.submitted = submitted
        yield c


BLOCKER_BAIT = re.compile(r"analy[sz]|track|beacon|pixel|telemetry|metric|stats|advert|(^|[/_.-])ads?([/_.-]|$)", re.I)


def test_no_page_file_is_named_like_a_tracker():
    """Ad and tracker blockers silently block files like analyse.js, which blanked the whole page once."""
    from hookscope import config
    names = [str(p.relative_to(config.STATIC_DIR)) for p in config.STATIC_DIR.rglob("*") if p.is_file()]
    assert names and not [n for n in names if BLOCKER_BAIT.search(n)]


def test_every_imported_module_exists():
    from hookscope import config
    js = config.STATIC_DIR / "js"
    for path in js.rglob("*.js"):
        for target in re.findall(r'from "(\.{1,2}/[^"]+)"', path.read_text()):
            assert (path.parent / target).resolve().exists(), f"{path.name} imports missing {target}"


def test_index_serves_page(client):
    res = client.get("/")
    assert res.status_code == 200 and "Hookscope" in res.text


def test_writes_need_app_header(client):
    assert client.post("/api/analyses", json={"url": "https://youtu.be/x"}).status_code == 403


def test_foreign_host_is_blocked(client):
    assert client.get("/api/analyses", headers={"host": "evil.example:8765"}).status_code == 403


def test_create_from_link_queues_job(client):
    res = client.post("/api/analyses", json={"url": "https://www.instagram.com/reel/abc/", "mode": "breakdown"}, headers=H)
    assert res.status_code == 200
    body = res.json()
    assert body["platform"] == "instagram" and body["status"] == "queued"
    assert client.submitted == [body["id"]]


def test_create_rejects_bad_link_and_mode(client):
    assert client.post("/api/analyses", json={"url": "not a link"}, headers=H).status_code == 400
    assert client.post("/api/analyses", json={"url": "https://youtu.be/x", "mode": "zzz"}, headers=H).status_code == 400


def test_draft_from_link_is_marked_mine(client):
    body = client.post("/api/analyses", json={"url": "https://youtu.be/x", "mode": "draft"}, headers=H).json()
    assert body["is_mine"] == 1


def test_upload_rejects_non_video(client):
    res = client.post("/api/analyses/upload", files={"files": ("notes.txt", b"hi")}, data={"mode": "draft"}, headers=H)
    assert res.status_code == 400


def test_upload_saves_file_and_queues(client):
    res = client.post("/api/analyses/upload", files={"files": ("clip.mp4", b"\x00" * 100)}, data={"mode": "draft", "note": "hook ok?"}, headers=H)
    assert res.status_code == 200
    body = res.json()
    assert body["platform"] == "upload" and body["note"] == "hook ok?" and body["kind"] == "video"
    assert client.submitted == [body["id"]]


def test_upload_images_become_a_carousel(client):
    from hookscope import config
    files = [("files", (f"{n}.jpg", b"\xff\xd8\xff", "image/jpeg")) for n in (1, 2, 3)]
    body = client.post("/api/analyses/upload", files=files, data={"mode": "draft"}, headers=H).json()
    assert body["kind"] == "carousel" and body["title"].startswith("Carousel")
    saved = sorted(p.name for p in (config.analysis_dir(body["id"]) / "slides").iterdir())
    assert saved == ["s_01.jpg", "s_02.jpg", "s_03.jpg"]
    assert client.submitted == [body["id"]]


def test_upload_one_image_is_a_photo(client):
    body = client.post("/api/analyses/upload", files={"files": ("me.png", b"\x89PNG")}, data={"mode": "draft"}, headers=H).json()
    assert body["kind"] == "photo"


@pytest.mark.parametrize("names, message", [
    (["a.mp4", "b.mp4"], "one video"),
    ([f"{n}.jpg" for n in range(21)], "at most 20"),
])
def test_upload_plan_rejects_bad_mixes(names, message):
    with pytest.raises(app_module.HTTPException) as err:
        app_module.upload_plan(names)
    assert message in err.value.detail


def test_upload_plan_mixed_carousel():
    assert app_module.upload_plan(["1.jpg", "2.mp4"]) == ("carousel", ["slides/s_01.jpg", "slides/s_02.mp4"])


def test_media_route_serves_video_slides_only(client):
    assert app_module.MEDIA_NAME.match("slides/s_03.mp4")
    assert not app_module.MEDIA_NAME.match("slides/s_03.jpg")
    assert not app_module.MEDIA_NAME.match("slides/../x.mp4")


def test_carousel_pipeline_end_to_end(monkeypatch):
    """A 3-slide upload runs through all five steps with Claude faked."""
    from PIL import Image
    from hookscope import config, pipeline as real_pipeline
    row = db.create_analysis({"mode": "breakdown", "platform": "upload", "kind": "carousel", "title": "t"})
    slides = config.analysis_dir(row["id"]) / "slides"
    slides.mkdir(parents=True)
    for n, colour in enumerate(("red", "green", "blue"), start=1):
        Image.new("RGB", (1080, 1350), colour).save(slides / f"s_{n:02d}.jpg")
    seen = {}

    def fake_ask(prompt, system, images=None, **_):
        seen["images"] = images
        seen["prompt"] = prompt
        return {"summary": "s", "hook": {"quote": "Cover", "source": "slide_text", "slide": 9},
                "slides": [{"slide": 1, "role": "Cover"}, {"slide": 7}], "working": [{"title": "w", "slide": 0}],
                "scores": {"hook": 7, "design": 11}}
    monkeypatch.setattr(brain, "ask_json", fake_ask)
    real_pipeline.run(row["id"])
    done = db.get_analysis(row["id"])
    assert done["status"] == "done", done["error"]
    assert [s["label"] for s in done["steps"]][2] == "Reading the slides"
    assert len(seen["images"]) == 3 and "carousel of 3 slides" in seen["prompt"]
    report = done["report"]
    assert report["hook"]["slide"] == 3 and report["hook"]["quote_check"] == "on_slide"
    assert report["slides"][1]["slide"] == 3 and report["working"][0]["slide"] == 1
    assert report["scores"] == {"hook": 7, "design": 10}
    frames = real_pipeline.read_json(config.analysis_dir(row["id"]) / "frames.json")
    assert [f["kind"] for f in frames] == ["slide"] * 3
    assert (config.analysis_dir(row["id"]) / "thumb.jpg").exists()


def test_get_list_patch_delete(client):
    row = db.create_analysis({"mode": "breakdown", "source_url": "https://youtu.be/x", "platform": "youtube", "title": "Caption tricks"})
    db.update_analysis(row["id"], {"status": "done", "report": {"summary": "Great hook"}})
    assert client.get("/api/analyses?q=caption").json()[0]["summary"] == "Great hook"
    assert client.get(f"/api/analyses/{row['id']}").json()["frames"] == []
    assert client.patch(f"/api/analyses/{row['id']}", json={"is_mine": True}, headers=H).json()["is_mine"] == 1
    assert client.delete(f"/api/analyses/{row['id']}", headers=H).status_code == 200
    assert client.get(f"/api/analyses/{row['id']}").status_code == 404


def test_retry_refuses_running(client):
    row = db.create_analysis({"mode": "breakdown", "source_url": "https://youtu.be/x"})
    db.update_analysis(row["id"], {"status": "running"})
    assert client.post(f"/api/analyses/{row['id']}/retry", headers=H).status_code == 409


def test_media_route_blocks_traversal(client):
    assert client.get("/media/abcdefabcdef/../../hookscope.db").status_code == 404
    assert client.get("/media/abcdefabcdef/secret.txt").status_code == 404


def test_profile_roundtrip(client):
    saved = client.put("/api/profile", json={"niche": "editing", "pillars": ["captions"], "evil": 1}, headers=H).json()
    assert saved["niche"] == "editing" and "evil" not in saved
    assert client.get("/api/profile").json()["pillars"] == ["captions"]


def test_learn_without_own_videos_explains(client):
    res = client.post("/api/profile/learn", headers=H)
    assert res.status_code == 400 and "yours" in res.json()["detail"]


def test_script_generation_and_edit(client, monkeypatch):
    monkeypatch.setattr(brain, "ask_json", lambda *a, **k: {"title": "T", "chosen_hook": "Hook", "beats": []})
    s = client.post("/api/scripts", json={"idea": {"title": "Idea"}}, headers=H).json()
    assert s["script"]["title"] == "T"
    edited = client.put(f"/api/scripts/{s['id']}", json={"edited_text": "my words"}, headers=H).json()
    assert edited["edited_text"] == "my words"
    assert len(client.get("/api/scripts").json()) == 1


def test_tools_and_chat_use_brain(client, monkeypatch):
    monkeypatch.setattr(brain, "ask_text", lambda *a, **k: "**answer**")
    tools = client.get("/api/tools").json()
    assert len(tools) == 7
    assert client.post("/api/tools/hook_generator", json={"text": "editing"}, headers=H).json()["output"] == "**answer**"
    assert client.post("/api/tools/nope", json={"text": "x"}, headers=H).status_code == 404
    assert client.post("/api/chat", json={"text": "hi"}, headers=H).json()["role"] == "assistant"
    assert [m["role"] for m in client.get("/api/chat").json()] == ["user", "assistant"]


def test_brain_errors_become_readable(client, monkeypatch):
    def boom(*a, **k):
        raise brain.BrainError("Claude isn't signed in on this Mac.")
    monkeypatch.setattr(brain, "ask_text", boom)
    res = client.post("/api/tools/hook_generator", json={"text": "x"}, headers=H)
    assert res.status_code == 502 and "signed in" in res.json()["detail"]


def test_plan_needs_finished_analyses(client, monkeypatch):
    assert client.post("/api/plans", json={"analysis_ids": []}, headers=H).status_code == 400
    row = db.create_analysis({"mode": "breakdown", "source_url": "https://youtu.be/x"})
    db.update_analysis(row["id"], {"status": "done", "report": {"summary": "s"}})
    monkeypatch.setattr(brain, "ask_json", lambda *a, **k: {"headline": "H", "do_next": ["a", "b"], "days": []})
    plan = client.post("/api/plans", json={"analysis_ids": [row["id"]]}, headers=H).json()
    assert plan["data"]["headline"] == "H"
    assert client.patch(f"/api/plans/{plan['id']}", json={"done": [1, 1, 0]}, headers=H).json()["done"] == [0, 1]


def test_settings_only_known_keys(client):
    saved = client.put("/api/settings", json={"cookies_browser": "safari", "junk": "x"}, headers=H).json()
    assert saved["cookies_browser"] == "safari" and "junk" not in saved


def test_recover_marks_running_as_interrupted(monkeypatch):
    row = db.create_analysis({"mode": "breakdown", "source_url": "https://youtu.be/x"})
    db.update_analysis(row["id"], {"status": "running"})
    pipeline.recover()
    after = db.get_analysis(row["id"])
    assert after["status"] == "failed" and "Retry" in after["error"]
