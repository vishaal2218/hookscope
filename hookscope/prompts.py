"""Every prompt Hookscope sends to Claude, with the JSON shape each one must return."""

from __future__ import annotations

import json

SYSTEM = (
    "You are a sharp short-form video strategist and editor. You have watched thousands of Reels, "
    "Shorts and TikToks and you explain, in plain everyday English, exactly why a video holds attention "
    "or loses it. You are specific: you name the moment (with its timestamp), the words, the shot, the "
    "edit. You never invent numbers, quotes or events that are not in the material you were given. When "
    "something can't be judged from the material, say so briefly instead of guessing. No hype, no filler, "
    "no em dashes."
)

MATERIAL_GUIDE = """How to read the material:
- Image 1 is the HOOK sheet: frames from the first 3 seconds. Image 2 is the BODY sheet: frames across the rest.
  Every tile is labelled "#n  m:ss.s" (frame number and time). Use those times.
- Read on-screen text, captions, framing, faces, b-roll, props and setting from the frames.
- The transcript is speech-to-text with [start-end] seconds. Quote it exactly; don't fix its wording.
- SIGNALS are measured by software: cuts per 10 s, average shot length, words per minute, time of the
  first spoken word, dead-air gaps, quiet stretches and a music/sound-effects share. Trust them over
  your impression of the frames for pacing.
- PUBLIC NUMBERS come from the platform page and may be missing."""


def profile_block(profile: dict) -> str:
    if not profile or not any(profile.get(k) for k in ("niche", "audience", "pillars", "tone", "voice_facts")):
        return "CREATOR PROFILE: not set up yet. Write ideas for a general creator and say once that they get sharper after the Your voice page is filled in."
    facts = "\n".join(f"- {f.get('text')}" for f in profile.get("voice_facts", []) if f.get("text"))
    pillars = ", ".join(profile.get("pillars", []))
    return (
        "CREATOR PROFILE (the person you are advising):\n"
        f"Niche: {profile.get('niche') or 'not given'}\nAudience: {profile.get('audience') or 'not given'}\n"
        f"Content pillars: {pillars or 'not given'}\nTone: {profile.get('tone') or 'not given'}\n"
        f"Goals: {profile.get('goals') or 'not given'}\nVoice facts:\n{facts or '- none yet'}"
    )


def material_block(meta: dict, transcript_lines: str, signals: dict, truncated: bool) -> str:
    numbers = {k: v for k, v in (meta.get("metrics") or {}).items() if k != "caption" and v not in (None, [], "")}
    signals_view = {k: v for k, v in signals.items() if k != "cut_times"}
    signals_view["audio"] = {k: v for k, v in signals.get("audio", {}).items() if k not in ("curve", "curve_step_seconds")}
    caption = (meta.get("metrics") or {}).get("caption") or ""
    return (
        f"VIDEO: {meta.get('title') or 'untitled'} by {meta.get('author') or 'unknown'} on {meta.get('platform') or 'unknown'}, "
        f"{signals.get('duration')} s long{' (only the first 15 minutes were analysed)' if truncated else ''}.\n"
        f"PUBLIC NUMBERS: {json.dumps(numbers, ensure_ascii=False) if numbers else 'none available'}\n"
        f"POSTED CAPTION: {caption[:1500] or 'none'}\n"
        f"SIGNALS: {json.dumps(signals_view, ensure_ascii=False)}\n"
        f"TRANSCRIPT:\n{transcript_lines or '(no speech detected)'}"
    )


BREAKDOWN_SHAPE = """{
  "summary": "3-4 sentences: why this video works (or doesn't), in plain words",
  "format": "short label, e.g. talking-head tutorial, POV skit, listicle, before/after, storytime",
  "hook": {
    "quote": "the exact opening line from the transcript, or the on-screen text if the hook is silent",
    "source": "spoken | on_screen | visual",
    "start": 0.0, "end": 2.5,
    "type": "e.g. bold claim, curiosity gap, pattern interrupt, direct callout, result first, question",
    "visual": "what the viewer sees in the first seconds",
    "why_it_works": "2-3 sentences",
    "use_it": "how to use the same move on the creator's own topic, with one example line"
  },
  "scores": {"hook": 1, "pacing": 1, "clarity": 1, "payoff": 1},
  "beats": [{"start": 0.0, "end": 3.0, "label": "Hook", "what_happens": "one sentence"}],
  "working": [{"title": "short", "detail": "1-2 sentences", "layer": "script | visual | audio | pacing | performance", "at": 4.5}],
  "better": [{"title": "short", "detail": "what to change and why", "at": 12.0}],
  "retention_risks": [{"at": 9.0, "reason": "why a viewer might swipe here"}],
  "on_screen_text": [{"at": 0.5, "text": "exact text read from a frame"}],
  "audio": {"delivery": "pace, energy, tone of voice", "music": "music or sound design, or none", "energy": "how energy moves across the video"},
  "performance_read": "what the public numbers suggest (engagement rate if possible), or that there are none",
  "template": "a fill-in-the-blank structure anyone could reuse, beat by beat",
  "ideas": [{"title": "idea title", "hook": "an opening line in the creator's voice", "angle": "what the video is and how it borrows the structure", "why_for_you": "why it fits this creator", "pillar": "which content pillar, or empty"}]
}"""

DRAFT_SHAPE = """{
  "verdict": "ready | needs_work",
  "verdict_reason": "one sentence",
  "summary": "3-4 sentences: overall read of the draft",
  "hook": {
    "quote": "the exact opening line from the transcript, or on-screen text if silent",
    "source": "spoken | on_screen | visual",
    "start": 0.0, "end": 2.5,
    "strength": 1,
    "assessment": "2-3 sentences on how well it stops the scroll",
    "stronger_openers": ["3 alternative opening lines, ready to say"]
  },
  "scores": {"hook": 1, "pacing": 1, "clarity": 1, "payoff": 1},
  "beats": [{"start": 0.0, "end": 3.0, "label": "Hook", "what_happens": "one sentence"}],
  "working": [{"title": "short", "detail": "keep this because...", "at": 4.0}],
  "lose_them": [{"at": 9.0, "reason": "why viewers may swipe here", "fix": "the specific change"}],
  "fixes": [{"at": 12.0, "change": "specific edit, line or shot", "why": "reason", "priority": "high | medium | low"}],
  "answer_to_note": "a direct answer to the creator's note, or null when there is no note",
  "caption": {"text": "a ready-to-post caption written from what is actually in the video, not a repeat of the hook", "hashtags": ["5-8 relevant tags without #"]}
}"""

RULES = """Rules:
- Return ONLY one JSON object in exactly this shape. Use null for unknown numbers. Times are seconds (numbers).
- Scores are integers 1-10. Be honest; most videos are not a 9.
- Every "at", "start" and "end" must fall inside the video length and point to a real moment.
- working: 3-6 items. better / lose_them / fixes: 2-5 items, ordered by impact. beats: cover the whole video.
- Do not pad lists. If the video is tight and nothing stands out as a drop-off, say so with fewer items."""


POST_GUIDE = """How to read the material:
- Every image is one slide of the post, in order. The black bar on top reading "SLIDE n / N" is added by us
  and is not part of the post; refer to slides by that number.
- Read every word on every slide exactly. Judge the cover (slide 1) as the hook: it has to stop the scroll
  in the feed on its own.
- Slides marked VIDEO are short clips; their speech, if any, is in the transcript tagged [slide n].
- PUBLIC NUMBERS come from the platform page and may be missing. The caption is part of the post."""


def post_material_block(meta: dict, signals: dict, transcript_lines: str) -> str:
    numbers = {k: v for k, v in (meta.get("metrics") or {}).items() if k != "caption" and v not in (None, [], "")}
    caption = (meta.get("metrics") or {}).get("caption") or ""
    kind = "single-photo post" if signals.get("slides") == 1 else f"carousel of {signals.get('slides')} slides"
    return (
        f"POST: {kind} by {meta.get('author') or 'unknown'} on {meta.get('platform') or 'unknown'}.\n"
        f"PUBLIC NUMBERS: {json.dumps(numbers, ensure_ascii=False) if numbers else 'none available'}\n"
        f"POSTED CAPTION: {caption[:2000] or 'none'}\n"
        f"SIGNALS: {json.dumps(signals, ensure_ascii=False)}\n"
        f"VIDEO SLIDE SPEECH:\n{transcript_lines or '(none)'}"
    )


POST_BREAKDOWN_SHAPE = """{
  "summary": "3-4 sentences: why this post works (or doesn't), in plain words",
  "format": "short label, e.g. educational carousel, listicle carousel, step-by-step guide, photo dump, meme, quote card, before/after, single photo",
  "hook": {
    "quote": "the exact headline text on slide 1, or the caption's first line if the cover has no text",
    "source": "slide_text | visual | caption",
    "slide": 1,
    "type": "e.g. bold claim, curiosity gap, numbered promise, direct callout, result first, question",
    "visual": "what the cover looks like in the feed",
    "why_it_works": "2-3 sentences",
    "use_it": "how to use the same move on the creator's own topic, with one example cover line"
  },
  "scores": {"hook": 1, "flow": 1, "clarity": 1, "payoff": 1, "design": 1},
  "slides": [{"slide": 1, "role": "e.g. Cover / hook, Problem, Step 1, Proof, Payoff, CTA", "text": "the exact main words on the slide, or empty", "note": "what this slide does and how well, one sentence"}],
  "working": [{"title": "short", "detail": "1-2 sentences", "layer": "copy | design | structure | caption | performance", "slide": 2}],
  "better": [{"title": "short", "detail": "what to change and why", "slide": 4}],
  "drop_off": [{"slide": 5, "reason": "why people may stop swiping here"}],
  "design": {"typography": "fonts, size, hierarchy, legibility on a phone", "layout": "composition and white space", "color": "palette and contrast", "consistency": "how the slides hold together as a set"},
  "caption_read": "how the caption works with the slides (CTA, keywords, giveaway, length)",
  "performance_read": "what the public numbers suggest, or that there are none",
  "template": "a slide-by-slide fill-in-the-blank structure anyone could reuse",
  "ideas": [{"title": "idea title", "hook": "a cover line in the creator's voice", "angle": "what the post is and how it borrows the structure", "why_for_you": "why it fits this creator", "pillar": "content pillar or empty", "format": "carousel | reel"}]
}"""

POST_DRAFT_SHAPE = """{
  "verdict": "ready | needs_work",
  "verdict_reason": "one sentence",
  "summary": "3-4 sentences: overall read of the draft post",
  "hook": {
    "quote": "the exact headline text on the cover (slide 1)",
    "source": "slide_text | visual | caption",
    "slide": 1,
    "strength": 1,
    "assessment": "2-3 sentences on how well the cover stops the scroll",
    "stronger_openers": ["3 alternative cover headlines, ready to use"]
  },
  "scores": {"hook": 1, "flow": 1, "clarity": 1, "payoff": 1, "design": 1},
  "slides": [{"slide": 1, "role": "role of the slide", "text": "exact main words, or empty", "note": "what works or what is off, one sentence"}],
  "working": [{"title": "short", "detail": "keep this because...", "slide": 2}],
  "lose_them": [{"slide": 4, "reason": "why people may stop swiping here", "fix": "the specific change"}],
  "fixes": [{"slide": 3, "change": "specific edit to copy, layout or order", "why": "reason", "priority": "high | medium | low"}],
  "answer_to_note": "a direct answer to the creator's note, or null when there is no note",
  "caption": {"text": "a ready-to-post caption that adds to the slides instead of repeating them", "hashtags": ["5-8 relevant tags without #"]}
}"""

POST_RULES = """Rules:
- Return ONLY one JSON object in exactly this shape. Use null for unknown numbers.
- Every "slide" is a slide number between 1 and the number of slides. Quote slide text exactly as written.
- Scores are integers 1-10. Be honest; most posts are not a 9.
- slides: one entry per slide, in order. working: 3-6 items. better / drop_off / lose_them / fixes: 2-5 items, ordered by impact.
- For a single photo, judge the photo and the caption together; drop_off can be empty."""


def post_breakdown_prompt(material: str, profile: str, note: str) -> str:
    focus = f"\nThe creator wants to learn this from it: {note}\n" if note else ""
    return (
        "Break down this post so the creator understands why it performs and can reuse what works. "
        "Give exactly 3 ideas adapted to the creator profile (mostly carousels, a reel where it fits better), never a copy.\n"
        f"{focus}\n{POST_GUIDE}\n\n{profile}\n\n{material}\n\n{POST_RULES}\n\nShape:\n{POST_BREAKDOWN_SHAPE}"
    )


def post_draft_prompt(material: str, profile: str, note: str) -> str:
    asked = f"\nThe creator's note (what they are unsure about): {note}\n" if note else "\nThe creator left no note.\n"
    return (
        "This is the creator's own unposted carousel or photo. Review it before they post it. Open with the cover, "
        "keep what works, show the exact slides where people may stop swiping and how to fix each one, then write "
        "the caption. Verdict 'ready' only if you would post it as is.\n"
        f"{asked}\n{POST_GUIDE}\n\n{profile}\n\n{material}\n\n{POST_RULES}\n\nShape:\n{POST_DRAFT_SHAPE}"
    )


def breakdown_prompt(material: str, profile: str, note: str) -> str:
    focus = f"\nThe creator wants to learn this from it: {note}\n" if note else ""
    return (
        "Break down this video so the creator understands why it performs and can reuse what works. "
        "Give exactly 3 ideas, adapted to the creator profile, never a copy of the original.\n"
        f"{focus}\n{MATERIAL_GUIDE}\n\n{profile}\n\n{material}\n\n{RULES}\n\nShape:\n{BREAKDOWN_SHAPE}"
    )


def draft_prompt(material: str, profile: str, note: str) -> str:
    asked = f"\nThe creator's note (what they are unsure about): {note}\n" if note else "\nThe creator left no note.\n"
    return (
        "This is the creator's own unposted draft. Review it before they post it. Open with the hook, "
        "keep what works, show the exact moments viewers may swipe away and how to fix each one, then "
        "write the caption. Verdict 'ready' only if you would post it as is.\n"
        f"{asked}\n{MATERIAL_GUIDE}\n\n{profile}\n\n{material}\n\n{RULES}\n\nShape:\n{DRAFT_SHAPE}"
    )
