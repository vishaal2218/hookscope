"""Everything generated on demand: scripts, text tools, chat, weekly plan, voice learning."""

from __future__ import annotations

import json
from datetime import date, timedelta

from . import brain, config, db, prompts
from .pipeline import read_json

DIGEST_LIMIT = 40
CHAT_HISTORY_TURNS = 12

SCRIPT_SHAPE = """{
  "title": "working title",
  "format": "e.g. talking head with b-roll",
  "length_seconds": 35,
  "hook_options": [{"style": "e.g. bold claim", "line": "an opening line"}],
  "chosen_hook": "the opening line the script uses",
  "beats": [{"time": "0-3s", "say": "exact words to say", "show": "what is on screen / the shot", "on_screen_text": "text overlay or empty"}],
  "shot_list": ["shot 1", "shot 2"],
  "cta": "the ending call to action",
  "caption": "ready-to-post caption",
  "hashtags": ["tag"],
  "filming_notes": "1-3 practical tips for recording and editing this"
}"""

TOOLS = {
    "hook_generator": ("Hook generator", "Describe your video", "Write 8 scroll-stopping opening lines for the video described below. Mix styles (bold claim, curiosity gap, direct callout, result first, question, pattern interrupt) and label each style. Each line must be sayable in under 3 seconds."),
    "hook_analyser": ("Hook analyser", "Paste your opening line", "Judge this opening line for a short-form video. Say what works, what weakens it (vagueness, slow start, no stakes, too long to say), rate it 1-10, then give 3 stronger rewrites that keep the meaning."),
    "script_generator": ("Script generator", "Describe your video", "Write a first-draft short-form script (30-45 seconds) for the video described below: a hook, then beats with what to say and what to show, then a call to action. Keep sentences short and spoken."),
    "script_analyser": ("Script analyser", "Paste your script", "Review this short-form script before filming. Point out vague lines, padding, slow moments, missing payoff and anything off-voice. Quote the exact lines, then give a tightened version."),
    "idea_generator": ("Idea generator", "What do you post about?", "Give 10 video ideas worth filming for this creator. For each: a title, an opening line, and one sentence on why it should work. Vary the formats."),
    "caption_generator": ("Caption generator", "What is the video about?", "Write 4 caption options for this video. Each adds something the video doesn't say out loud (context, a question, a takeaway); none just repeats the hook. Add 5-8 hashtags at the end."),
    "bio_generator": ("Bio generator", "Who are you and what do you post?", "Write 5 profile bios (each under 150 characters) that read like a real person, say who it is for and what they get, and avoid buzzwords."),
}


def _profile() -> str:
    return prompts.profile_block(db.get_profile())


def _report_brief(analysis: dict) -> dict:
    report = analysis.get("report") or {}
    hook = report.get("hook") or {}
    return {
        "id": analysis["id"], "mode": analysis["mode"], "kind": analysis.get("kind") or "video",
        "mine": bool(analysis.get("is_mine")),
        "title": analysis.get("title"), "author": analysis.get("author"), "platform": analysis.get("platform"),
        "duration": analysis.get("duration"),
        "numbers": {k: v for k, v in (analysis.get("metrics") or {}).items() if k in ("views", "likes", "comments", "upload_date")},
        "format": report.get("format"), "summary": report.get("summary") or report.get("verdict_reason"),
        "hook": {"quote": hook.get("quote"), "type": hook.get("type")}, "scores": report.get("scores"),
        "working": [w.get("title") for w in report.get("working", [])][:5],
        "template": report.get("template"),
    }


def library_digest(ids: list[str] | None = None) -> list[dict]:
    rows = [a for a in db.list_analyses(limit=DIGEST_LIMIT * 3) if a["status"] == "done"]
    if ids:
        rows = [a for a in rows if a["id"] in set(ids)]
    return [_report_brief(a) for a in rows[:DIGEST_LIMIT]]


CAROUSEL_SHAPE = """{
  "type": "carousel",
  "title": "working title",
  "format": "e.g. step-by-step carousel",
  "slide_count": 7,
  "hook_options": [{"style": "e.g. numbered promise", "line": "a cover headline"}],
  "chosen_hook": "the cover headline the plan uses",
  "slides": [{"slide": 1, "headline": "big text on the slide", "body": "smaller supporting text, or empty", "visual": "what is shown: photo, screenshot, icon, layout"}],
  "cta": "the last slide's call to action",
  "caption": "ready-to-post caption that adds to the slides",
  "hashtags": ["tag"],
  "design_notes": "1-3 practical tips: fonts, colours, consistency, legibility on a phone"
}"""


def wants_carousel(idea: dict, source: dict | None) -> bool:
    fmt = str(idea.get("format") or "").lower()
    if "reel" in fmt or "video" in fmt:
        return False
    return "carousel" in fmt or bool(source and source.get("kind") in ("photo", "carousel"))


def generate_carousel(idea: dict, source: dict | None, analysis_id: str | None) -> dict:
    reference = ""
    if source and source.get("report"):
        r = source["report"]
        reference = (f"\nREFERENCE POST it was inspired by (borrow the structure, not the content):\n"
                     f"Format: {r.get('format')}\nTemplate: {r.get('template')}\nCover move: {(r.get('hook') or {}).get('type')}\n")
    prompt = (
        "Plan a ready-to-design carousel for this idea, in the creator's voice. Offer 3 cover headlines in "
        "different proven styles, pick the strongest as chosen_hook, then write every slide: the exact headline, "
        "supporting text and what is shown. Each slide should earn the next swipe; the last slide carries the CTA.\n\n"
        f"IDEA: {json.dumps(idea, ensure_ascii=False)}\n{reference}\n{_profile()}\n\n"
        f"Return ONLY one JSON object in this shape:\n{CAROUSEL_SHAPE}"
    )
    plan = {**brain.ask_json(prompt, prompts.SYSTEM), "type": "carousel"}
    return db.create_script(analysis_id, idea, plan)


def generate_script(idea: dict, analysis_id: str | None) -> dict:
    source = db.get_analysis(analysis_id) if analysis_id else None
    if wants_carousel(idea, source):
        return generate_carousel(idea, source, analysis_id)
    reference = ""
    if source and source.get("report"):
        r = source["report"]
        reference = (f"\nREFERENCE VIDEO it was inspired by (borrow the structure, not the content):\n"
                     f"Format: {r.get('format')}\nTemplate: {r.get('template')}\nHook move: {(r.get('hook') or {}).get('type')}\n")
    prompt = (
        "Write a ready-to-film short-form script for this idea, in the creator's voice. Offer 3 hook options in "
        "different proven styles, pick the strongest as chosen_hook, then write every beat with exact words to say "
        "and what to show. Spoken, short sentences.\n\n"
        f"IDEA: {json.dumps(idea, ensure_ascii=False)}\n{reference}\n{_profile()}\n\n"
        f"Return ONLY one JSON object in this shape:\n{SCRIPT_SHAPE}"
    )
    script = brain.ask_json(prompt, prompts.SYSTEM)
    return db.create_script(analysis_id, idea, script)


def run_tool(tool: str, text: str) -> dict:
    if tool not in TOOLS:
        raise ValueError("unknown tool")
    name, _label, task = TOOLS[tool]
    prompt = f"{task}\n\nINPUT:\n{text.strip()[:6000]}\n\n{_profile()}\n\nAnswer in clean Markdown (short headings, lists). No preamble."
    return {"tool": tool, "name": name, "output": brain.ask_text(prompt, prompts.SYSTEM)}


def chat(question: str) -> dict:
    history = db.list_chat(CHAT_HISTORY_TURNS)
    db.add_chat("user", question)
    transcript = "\n".join(f"{m['role'].upper()}: {m['text'][:2000]}" for m in history)
    digest = library_digest()
    prompt = (
        "Answer the creator's question using their library of analysed videos and their profile below. "
        "Refer to videos by title and author. If the library can't answer it, say what to analyse first. "
        "When asked for hooks, offer 2-3 in labelled styles first; write a full script only once a hook is chosen. "
        "Answer in clean Markdown, short.\n\n"
        f"{_profile()}\n\nLIBRARY ({len(digest)} analyses):\n{json.dumps(digest, ensure_ascii=False)}\n\n"
        f"CONVERSATION SO FAR:\n{transcript or '(new conversation)'}\n\nQUESTION: {question.strip()[:4000]}"
    )
    try:
        answer = brain.ask_text(prompt, prompts.SYSTEM)
    except brain.BrainError as exc:
        db.add_chat("assistant", f"Sorry, I couldn't answer: {exc}")
        raise
    return db.add_chat("assistant", answer)


PLAN_SHAPE = """{
  "headline": "the single clearest pattern, one sentence",
  "findings": [{"finding": "what keeps working, number first if there is one", "evidence": "which videos show it"}],
  "improvement_areas": [{"area": "short", "detail": "what to change"}],
  "do_next": ["a concrete action for this week"],
  "days": [{"day": "Mon", "date": "DD-MM-YYYY", "title": "video idea", "hook": "opening line", "format": "format", "why": "why this, why now", "inspired_by": "id of the library video or empty"}]
}"""


def make_plan(analysis_ids: list[str]) -> dict:
    digest = library_digest(analysis_ids)
    if not digest:
        raise ValueError("Pick at least one finished analysis first.")
    start = date.today()
    dates = [(start + timedelta(days=i)).strftime("%a %d-%m-%Y") for i in range(7)]
    prompt = (
        "Study these analysed videos together. Find the patterns that repeat across the ones that worked "
        "(hooks, formats, length, pacing), what to fix, and plan the next 7 days of posts for this creator. "
        "Not every day needs a post: plan 4-6 posts and mark rest days with an empty title. Ideas must fit the "
        "creator profile and say which library video inspired them. In all text, refer to videos by their "
        "title and author, never by id; ids go only in inspired_by.\n\n"
        f"DATES: {', '.join(dates)}\n\n{_profile()}\n\nVIDEOS:\n{json.dumps(digest, ensure_ascii=False)}\n\n"
        f"Return ONLY one JSON object in this shape:\n{PLAN_SHAPE}"
    )
    return db.create_plan([d["id"] for d in digest], brain.ask_json(prompt, prompts.SYSTEM))


VOICE_SHAPE = """{
  "tone": "how they sound, one sentence",
  "pillars": ["3-5 content pillars"],
  "strongest_formats": ["formats that suit them"],
  "signature_phrases": ["phrases they actually repeat"],
  "voice_facts": ["8-12 short, specific facts about how they speak and present, e.g. 'opens with a question to camera', 'mixes Hindi and English mid-sentence'"]
}"""


def learn_voice() -> dict:
    own = [a for a in db.list_analyses() if a.get("is_mine") and a["status"] == "done"]
    if not own:
        raise ValueError("Mark at least one analysed video as yours first (the 'This is my video' switch on a report).")
    samples = []
    for a in own[:15]:
        transcript = read_json(config.analysis_dir(a["id"]) / "transcript.json", {}) or {}
        samples.append({**_report_brief(a), "caption": (a.get("metrics") or {}).get("caption", "")[:600],
                        "transcript": (transcript.get("text") or "")[:3000]})
    current = db.get_profile()
    prompt = (
        "These are the creator's own videos. Learn how they talk and what they make. Quote real phrases only. "
        f"Say nothing you can't see in the material. They have {len(own)} video(s); with fewer than 3, keep facts cautious.\n\n"
        f"CURRENT PROFILE: {json.dumps(current, ensure_ascii=False)}\n\nVIDEOS:\n{json.dumps(samples, ensure_ascii=False)}\n\n"
        f"Return ONLY one JSON object in this shape:\n{VOICE_SHAPE}"
    )
    learned = brain.ask_json(prompt, prompts.SYSTEM)
    return merge_learned(current, learned)


def merge_learned(current: dict, learned: dict) -> dict:
    known = {f.get("text", "").strip().lower() for f in current.get("voice_facts", [])}
    new_facts = [{"text": t.strip(), "source": "learned"} for t in learned.get("voice_facts", [])
                 if isinstance(t, str) and t.strip() and t.strip().lower() not in known]
    merged = {
        **current,
        "tone": current.get("tone") or learned.get("tone", ""),
        "pillars": current.get("pillars") or [p for p in learned.get("pillars", []) if isinstance(p, str)],
        "strongest_formats": [f for f in learned.get("strongest_formats", []) if isinstance(f, str)],
        "signature_phrases": [p for p in learned.get("signature_phrases", []) if isinstance(p, str)],
        "voice_facts": current.get("voice_facts", []) + new_facts,
    }
    return db.save_profile(merged)
