"""Pure-function tests: no network, no models, no Claude."""

import json
import subprocess

import numpy as np
import pytest

from hookscope import brain, db, fetch, generate, media, signals, transcribe, verify


# fetch -----------------------------------------------------------------------

@pytest.mark.parametrize("url, platform", [
    ("https://www.instagram.com/reel/ABC123/", "instagram"),
    ("https://youtu.be/xyz", "youtube"),
    ("https://www.youtube.com/shorts/abc", "youtube"),
    ("https://vm.tiktok.com/ZM123/", "tiktok"),
    ("https://x.com/a/status/1", "x"),
    ("https://example.org/video.mp4", "web"),
])
def test_platform_of_maps_hosts(url, platform):
    assert fetch.platform_of(url) == platform


@pytest.mark.parametrize("bad", ["", "hello", "ftp://x.com/a", "javascript:alert(1)", "https://localhost"])
def test_validate_url_rejects_non_links(bad):
    with pytest.raises(fetch.FetchError):
        fetch.validate_url(bad)


def test_validate_url_trims_and_keeps_link():
    assert fetch.validate_url("  https://youtu.be/abc  ") == "https://youtu.be/abc"


def test_validate_url_adds_missing_scheme():
    assert fetch.validate_url("instagram.com/reel/ABC/?x=1") == "https://instagram.com/reel/ABC/?x=1"
    assert fetch.validate_url("www.youtube.com/shorts/x") == "https://www.youtube.com/shorts/x"


def test_upload_date_is_dd_mm_yyyy():
    assert fetch.format_upload_date("20260307") == "07-03-2026"
    assert fetch.format_upload_date("bad") is None


def test_friendly_error_explains_instagram_login():
    msg = fetch.friendly_error("ERROR: login required to view this", "instagram")
    assert "logged in" in msg


def test_browser_access_reports_states(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch.Path, "home", lambda: tmp_path)
    assert fetch.browser_access("")["state"] == "off"
    assert fetch.browser_access("chrome")["state"] == "missing"
    folder = tmp_path / fetch.BROWSER_DATA["chrome"]
    folder.mkdir(parents=True)
    assert fetch.browser_access("chrome")["ok"] is True
    folder.chmod(0)
    try:
        assert fetch.browser_access("chrome")["state"] == "blocked"
    finally:
        folder.chmod(0o755)


def test_cookie_errors_explain_the_privacy_fix():
    msg = fetch.friendly_error('ERROR: could not find chrome cookies database in "/x"', "instagram")
    assert "Fix browser access" in msg


def test_fetch_stops_early_when_browser_login_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "browser_access", lambda b: {"ok": False, "state": "blocked", "detail": ""})
    with pytest.raises(fetch.FetchError, match="Fix browser access"):
        fetch.fetch("https://www.instagram.com/reel/ABC/", tmp_path, "chrome")


def test_friendly_error_explains_profile_links():
    assert "single video" in fetch.friendly_error("Unsupported URL: https://x", "web")


def test_metrics_from_info_keeps_public_numbers_only():
    info = {"view_count": 10, "like_count": 2, "comment_count": 1, "upload_date": "20260101", "description": "hi"}
    m = fetch.metrics_from_info(info)
    assert m["views"] == 10 and m["upload_date"] == "01-01-2026" and m["caption"] == "hi"


# media -----------------------------------------------------------------------

def test_pick_frame_times_hook_covers_first_three_seconds():
    hook, body = media.pick_frame_times(30.0, [])
    assert hook == [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
    assert body and all(t > 3.0 for t in body) and len(body) <= 12


def test_pick_frame_times_short_clip():
    hook, body = media.pick_frame_times(2.0, [])
    assert hook == [0.0, 0.5, 1.0, 1.5]
    assert body == []


def test_pick_frame_times_uses_cuts_and_spacing():
    cuts = [float(c) for c in range(4, 60, 2)]
    _, body = media.pick_frame_times(60.0, cuts)
    assert len(body) <= 12
    assert all(b2 - b1 >= media.MIN_FRAME_GAP for b1, b2 in zip(body, body[1:]))


def test_format_time():
    assert media.format_time(65.5) == "1:05.5"


def test_probe_and_frames_on_generated_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=10", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "6", "-shortest", str(clip)], check=True)
    probe = media.probe(clip)
    assert probe.vertical and probe.has_audio and 5.5 < probe.duration < 6.5
    hook, body = media.pick_frame_times(probe.duration, media.scene_cuts(clip))
    frames = media.grab_frames(clip, hook, body, tmp_path / "frames")
    sheet = media.contact_sheet(frames, tmp_path / "sheet.jpg", 3)
    assert sheet.exists() and len(frames) >= 6
    assert signals.loudness_curve(clip)


def test_probe_rejects_non_video(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_text("not a video")
    with pytest.raises(media.MediaError):
        media.probe(bad)


# signals ---------------------------------------------------------------------

def test_rms_db_and_silences():
    loud = np.full(8000, 0.5, dtype=np.float32)
    quiet = np.zeros(8000, dtype=np.float32)
    curve = signals.rms_db(np.concatenate([loud, quiet, loud]), 4000)
    assert len(curve) == 6
    spans = signals.silences(curve)
    assert spans == [{"start": 1.0, "end": 2.0}]


def test_speech_stats_finds_dead_air():
    words = [{"w": "a", "s": 0.2, "e": 0.5}, {"w": "b", "s": 0.6, "e": 0.9}, {"w": "c", "s": 3.0, "e": 3.3}]
    stats = signals.speech_stats(words, 4.0)
    assert stats["first_word_at"] == 0.2
    assert stats["dead_air"] == [{"start": 0.9, "end": 3.0}]


def test_speech_stats_empty():
    assert signals.speech_stats([], 10)["word_count"] == 0


def test_cut_stats():
    stats = signals.cut_stats([2.0, 4.0, 9.0], 10.0)
    assert stats["cuts"] == 3 and stats["cuts_per_10s"] == 3.0
    assert stats["longest_shot"] == {"start": 4.0, "end": 9.0}
    assert stats["cuts_in_first_3s"] == 1


def test_downsample_caps_points():
    assert len(signals.downsample(list(range(1000)), 100)) == 100


# transcribe ------------------------------------------------------------------

def test_simplify_drops_numpy_and_silence():
    raw = {"language": "en", "segments": [
        {"start": np.float64(0.0), "end": np.float64(1.0), "text": " Hello there", "no_speech_prob": 0.1,
         "words": [{"word": " Hello", "start": np.float64(0.0), "end": np.float64(0.4)}]},
        {"start": 1.0, "end": 2.0, "text": " ...", "no_speech_prob": 0.95, "words": []},
    ]}
    out = transcribe.simplify(raw)
    assert out["text"] == "Hello there" and len(out["segments"]) == 1
    json.dumps(out)  # must be plain JSON


# brain -----------------------------------------------------------------------

def test_extract_json_from_fenced_reply():
    assert brain.extract_json('Sure!\n```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}


def test_extract_json_handles_escaped_quotes():
    assert brain.extract_json('{"q": "she said \\"hi\\" {x}"}') == {"q": 'she said "hi" {x}'}


def test_extract_json_none_when_missing():
    assert brain.extract_json("no json here") is None


def test_parse_result_reads_last_result_event():
    stdout = '{"type":"system"}\n{"type":"result","result":"ok","is_error":false}\n'
    assert brain.parse_result(stdout)["result"] == "ok"


def test_build_message_puts_images_before_text(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    msg = json.loads(brain.build_message("hi", [img]))
    content = msg["message"]["content"]
    assert content[0]["type"] == "image" and content[-1] == {"type": "text", "text": "hi"}


def test_friendly_cli_error_for_login():
    assert "claude auth login" in brain.friendly_cli_error("Not logged in · Please run /login")


# verify ----------------------------------------------------------------------

TRANSCRIPT = {"text": "Stop scrolling. This one trick fixes your captions forever. First open settings.",
              "words": [{"w": "Stop", "s": 0.0, "e": 0.3}, {"w": "scrolling.", "s": 0.3, "e": 0.8}],
              "segments": [{"start": 0.0, "end": 0.8, "text": "Stop scrolling."}]}


def test_quote_score_matches_exact_and_fuzzy():
    assert verify.quote_score("this one trick fixes your captions", TRANSCRIPT["text"]) > 0.95
    assert verify.quote_score("totally different words here", TRANSCRIPT["text"]) < 0.6


def test_check_hook_verifies_real_quote():
    hook = verify.check_hook({"quote": "Stop scrolling.", "source": "spoken", "start": 0}, TRANSCRIPT, 10)
    assert hook["quote_check"] == "verified"


def test_check_hook_corrects_invented_quote():
    hook = verify.check_hook({"quote": "Nobody tells you this secret", "source": "spoken"}, TRANSCRIPT, 10)
    assert hook["quote_check"] == "corrected"
    assert hook["quote"] == "Stop scrolling."
    assert hook["model_quote"] == "Nobody tells you this secret"


def test_check_hook_leaves_on_screen_hooks():
    hook = verify.check_hook({"quote": "POV: you edit at 3am", "source": "on_screen"}, TRANSCRIPT, 10)
    assert hook["quote_check"] == "not_spoken"


def test_clean_report_clamps_times_and_scores():
    report = {"working": [{"title": "x", "at": 99}], "beats": [{"start": -2, "end": 5}], "scores": {"hook": 14, "pacing": "x"},
              "hook": {"quote": "Stop scrolling.", "source": "spoken", "start": 50}}
    out = verify.clean_report(report, TRANSCRIPT, 20.0)
    assert out["working"][0]["at"] == 20.0
    assert out["beats"][0]["start"] == 0.0
    assert out["scores"] == {"hook": 10}
    assert out["hook"]["start"] == 20.0
    assert out["better"] == []


# generate / profile ------------------------------------------------------------

def test_merge_learned_keeps_user_values_and_dedupes_facts():
    db.save_profile({"tone": "calm", "voice_facts": [{"text": "Opens with a question", "source": "you"}]})
    merged = generate.merge_learned(db.get_profile(), {
        "tone": "loud", "pillars": ["captions"], "voice_facts": ["opens with a question", "Mixes Hindi and English"],
        "strongest_formats": ["tutorial"], "signature_phrases": ["chalo"]})
    assert merged["tone"] == "calm"
    assert merged["pillars"] == ["captions"]
    assert [f["text"] for f in merged["voice_facts"]] == ["Opens with a question", "Mixes Hindi and English"]


def test_run_tool_rejects_unknown():
    with pytest.raises(ValueError):
        generate.run_tool("nope", "x")


# photo and carousel posts --------------------------------------------------------

from hookscope import gallery  # noqa: E402


@pytest.mark.parametrize("url, expected", [
    ("https://www.instagram.com/p/DeSWi1XFovF/?img_index=1", True),
    ("https://instagram.com/someone/p/ABC/", True),
    ("https://www.instagram.com/reel/ABC/", False),
    ("https://x.com/a/status/1", False),
])
def test_prefer_gallery_only_for_instagram_posts(url, expected):
    assert gallery.prefer_gallery(url) is expected


def test_metrics_from_meta_reads_instagram_fields():
    m = gallery.metrics_from_meta({"description": "Comment claude\nmore", "likes": 410, "date": "2026-10-09 12:00:00",
                                   "username": "godofprompt"})
    assert m["likes"] == 410 and m["upload_date"] == "09-10-2026" and m["caption"].startswith("Comment")


def test_order_files_uses_num_then_name(tmp_path):
    for name, num in (("b.jpg", 2), ("a.jpg", 1), ("c.mp4", 3)):
        (tmp_path / name).write_bytes(b"x")
        (tmp_path / f"{name}.json").write_text(json.dumps({"num": num}))
    (tmp_path / "notes.txt").write_text("skip")
    assert [p.name for p, _ in gallery.order_files(tmp_path)] == ["a.jpg", "b.jpg", "c.mp4"]


def test_gallery_friendly_errors():
    assert gallery.friendly_error("[instagram][error] HttpError: 401 Unauthorized").unsupported is False
    assert gallery.friendly_error("No suitable extractor found for 'x'").unsupported is True


def test_fetch_falls_back_to_gallery_when_no_video(tmp_path, monkeypatch):
    def no_video(*_a, **_k):
        raise fetch.FetchError("This post has no video (it may be a photo or a carousel).")
    slides = tuple(gallery.Slide(i, tmp_path / f"s_{i:02d}.jpg", False) for i in (1, 2))
    monkeypatch.setattr(fetch, "_video", no_video)
    monkeypatch.setattr(gallery, "download", lambda *a: gallery.GalleryResult(slides, "t", "me", {"likes": 1}))
    result = fetch.fetch("https://x.com/a/status/1", tmp_path, "")
    assert result.kind == "carousel" and len(result.slides) == 2 and result.video_path is None


def test_fetch_single_video_post_uses_video_path(tmp_path, monkeypatch):
    clip = tmp_path / "slides" / "s_01.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"x")
    monkeypatch.setattr(gallery, "download", lambda *a: gallery.GalleryResult((gallery.Slide(1, clip, True),), "t", "me", {}))
    result = fetch.fetch("https://www.instagram.com/p/ABC/", tmp_path, "")
    assert result.kind == "video" and result.video_path.name == "video.mp4"


def test_prepare_slides_makes_view_and_labelled_copies(tmp_path):
    from PIL import Image
    src = tmp_path / "s_01.png"
    Image.new("RGB", (2160, 2700), "white").save(src)
    out = media.prepare_slides([gallery.Slide(1, src, False)], tmp_path / "frames", tmp_path / "ai")
    with Image.open(out[0].view_path) as view, Image.open(out[0].ai_path) as ai:
        assert max(view.size) == media.SLIDE_VIEW_SIDE
        assert ai.height == round(2700 * media.SLIDE_AI_SIDE / 2700) + media.SLIDE_LABEL_HEIGHT
    assert media.aspect_label(out[0].width, out[0].height) == "4:5"


def test_clean_post_report_clamps_slides():
    out = verify.clean_post_report({"hook": {"quote": "x", "source": "slide_text", "slide": 0},
                                    "drop_off": [{"slide": 99, "reason": "r"}], "scores": {"flow": 0}}, {}, 5)
    assert out["hook"]["slide"] == 1 and out["drop_off"][0]["slide"] == 5 and out["scores"] == {"flow": 1}
    assert out["better"] == [] and out["hook"]["quote_check"] == "on_slide"


@pytest.mark.parametrize("idea, source_kind, expected", [
    ({"format": "carousel"}, None, True),
    ({"format": "reel"}, "carousel", False),
    ({}, "photo", True),
    ({}, "video", False),
])
def test_wants_carousel(idea, source_kind, expected):
    source = {"kind": source_kind} if source_kind else None
    assert generate.wants_carousel(idea, source) is expected
