# Recon map: Pattern (getpattern.io, web)

Scope: the link-in, analysis-out slice: competitor breakdown, draft review, creator
profile ("your voice"), script generation, a chat over your own library, the seven free
text tools and a weekly plan built from saved breakdowns. Inputs widened from
"Reels and TikTok" to any link yt-dlp can read (Instagram, YouTube, Shorts, TikTok, X,
Facebook, Vimeo, ...) plus file upload.
For: Vishal's own use, a single creator on one Mac. No accounts, no billing.
Date: 10-10-2026

Source rules followed: public marketing pages only. No login, no app account, no
network capture, no JS bundles. Pattern's terms (section 6) bar scraping and reverse
engineering the service; nothing here touches the service itself.

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | marketing home | https://www.getpattern.io/ | core loop (connect, analyse, plan), pricing, plan contents |
| 2 | competitor analysis page | https://www.getpattern.io/features/competitor-analysis | link input, hook / what's working / ideas in your voice |
| 3 | draft review page | https://www.getpattern.io/features/draft-review | upload + optional note, hook, keep, where you lose them (timestamps), caption |
| 4 | AI chatbot page | https://www.getpattern.io/features/ai-chatbot | answers from posts, weekly analysis, pillars, voice, uploaded docs |
| 5 | FAQ | https://www.getpattern.io/faq | four analysis layers: transcript, visual, audio, performance; 5-post minimum |
| 6 | try page | https://www.getpattern.io/try | free tool: MP4/MOV up to 90 s, choose draft review or competitor analysis |
| 7 | changelog | https://www.getpattern.io/changelog | hook section quotes checked against transcript; five-step timeline; generate script on each idea; editable voice facts |
| 8 | free tools | https://www.getpattern.io/free-tools | hook, hook analyser, script, script analyser, idea, caption, bio generators |
| 9 | terms | https://www.getpattern.io/terms | no scraping / reverse engineering of their service |

## Core loop

Paste a video link, get a breakdown of why it works and a ready-to-film idea in your own
voice.

## Screens (the clone's screens, mapped from what Pattern describes)

| ID | screen | route / how to reach | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Analyse | `#/` (home) | paste a link or drop a file, pick Breakdown or Draft review, optional note | URL input, dropzone, mode toggle, note field | empty, invalid link, submitting |
| S02 | Job progress | `#/report/:id` while running | five-step timeline with a timer per step; survives refresh | step list, timer | running, failed (with reason), done |
| S03 | Breakdown report | `#/report/:id` | why a video worked | metrics card, The Hook, what's working, could be better, beat sheet, ideas + Generate script, transcript, key frames | filled, partial (no speech), error |
| S04 | Draft review report | `#/report/:id` | fix a video before posting | verdict, hook + stronger openers, keep, where you lose them (timestamps), fixes, caption | ready, needs work |
| S05 | Library | `#/library` | every analysis, searchable | cards with thumbnail, platform and mode badges, search, delete | empty, filled |
| S06 | Your voice | `#/voice` | creator profile: niche, audience, pillars, tone, learned voice facts | form, fact list (edit / delete), "learn from my videos" | empty, filled |
| S07 | Script | `#/script/:id` | generated script, editable, saved | hook options, beats with timing, shot list, on-screen text, caption | generating, filled, edited |
| S08 | Scripts list | `#/scripts` | saved scripts | list | empty, filled |
| S09 | Chat | `#/chat` | ask questions about your library and voice | message list, suggestions, input | empty, thinking, answer, error |
| S10 | Tools | `#/tools` | seven text tools | tool picker, input, output | empty, running, result |
| S11 | Weekly plan | `#/plan` | patterns across chosen breakdowns + 7-day calendar | picker, findings list, do-next checklist, day cards | empty, generating, filled |
| S12 | Settings / health | `#/settings` | check yt-dlp, ffmpeg, whisper, Claude sign-in | status rows | ok, problem with fix text |

## Flows

```
F01 Break down a competitor's reel
    S01 paste link -> S02 progress -> S03 report
    happy path clicks: 2 (paste, Analyse)
    edge: private / login-only reel, carousel (no video), no speech, very long YouTube
          video, link to a profile not a post, Instagram rate limit

F02 Review my draft before posting
    S01 drop file + note -> S02 -> S04
    happy path clicks: 3 (drop, Draft review, Analyse)
    edge: wrong file type, file over 15 min, silent video

F03 Turn an idea into a script
    S03 idea -> Generate script -> S07 (edit, save)
    happy path clicks: 1
    edge: no voice profile yet (use generic voice, say so)

F04 Teach it my voice
    S06 fill niche + pillars, or mark my own analysed videos as mine -> learn
    happy path clicks: 3
    edge: fewer than 3 own videos (still works, says what it could not learn)

F05 Plan my week
    S11 pick breakdowns -> generate -> findings + 7-day plan
    edge: under 3 breakdowns selected

F06 Ask a question
    S09 type -> answer grounded in library
    edge: empty library

F07 Quick text tool
    S10 pick tool -> type -> result
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| Button | primary, secondary, ghost, danger | default, hover, focus, disabled, loading | all |
| Text input / textarea | url, plain, long | default, focus, invalid | S01 S06 S09 S10 |
| Dropzone | | idle, drag-over, file chosen, rejected | S01 |
| Segmented toggle | 2 options | selected | S01 S10 |
| Step timeline | | waiting, running (timer), done, failed | S02 |
| Section card | plain, highlighted | | S03 S04 S07 S11 |
| Metric tile | | value, missing | S03 S04 |
| Timestamp chip | | clickable (seeks video) | S03 S04 |
| Badge | platform, mode, verdict | | S03 S04 S05 |
| Report card (library) | | | S05 |
| Chat bubble | user, assistant | thinking | S09 |
| Toast | info, error | | all |
| Sidebar nav | | current page | all |

## Inferred data model

```
Analysis  id, mode (breakdown | draft), source_url, platform, title, author, duration,
          metrics json (views, likes, comments, upload_date), note, is_mine,
          status (queued | running | done | failed), steps json, error,
          transcript json (segments with word timing), frames json, signals json
          (cut rate, words per minute, loudness curve, silence gaps), report json,
          created_at
          evidence: S03/S04 sections, FAQ four layers, changelog five-step timeline
          confidence: high for sections, guess for field names

Profile   singleton: niche, audience, pillars[], tone, goals, voice_facts[] (text, source)
          evidence: "creator profile: pillars, tone, strongest formats"; editable facts
          confidence: medium

Script    id, analysis_id?, idea, script json, edited_text, created_at
          evidence: changelog "generated scripts are saved", "editable scripts"
          confidence: high

Plan      id, analysis_ids[], findings json, do_next[], days json, created_at
          evidence: weekly analysis "improvement areas", "do next checklist", calendar
          confidence: medium

ChatMessage  id, role, text, created_at
```

Relationships: Analysis 1-n Script, Plan n-n Analysis, Profile used by every generation.

## Feature matrix

See `features.csv`. Must: 14, should: 10, could: 4, skip: 7.

## Out of scope (cannot or should not be cloned)

- Connecting Instagram / TikTok accounts and reading private insights (skip rate, watch
  time, reach): needs each platform's approved app review. Public counts (views, likes,
  comments) from the link are used instead.
- Cross-posting and scheduling: needs publishing approval from both platforms.
- Billing, trials, plans: single-user local tool.
- Weekly emails: no mail server; the weekly plan is generated on demand.
- Pattern's own dataset of 10,000+ analysed videos and its tuned prompts.
- Their brand, copy, demo videos.

## Size

Screens 12, flows 7, entities 5. Hard parts: reliable downloads (Instagram blocks
anonymous access, YouTube changes often), getting a vision model to judge pacing from
frames plus measured signals, keeping quotes and timestamps honest (checked against the
transcript). Size: M, built as a local web app in one push.

## Build plan (how the clone is executed)

Local web app, runs only on this Mac at http://127.0.0.1:8765, started by double-clicking
`Hookscope.command`.

```
link or file
  -> fetch      yt-dlp (Chrome cookies for Instagram), metadata + video <= 720p
  -> transcribe mlx-whisper large-v3-turbo, local, word timings
  -> watch      ffmpeg: hook frames (first 3 s) + scene-cut frames, labelled contact sheets
  -> measure    cuts per 10 s, words per minute, loudness curve, silences, on-screen text
  -> judge      Claude (claude CLI, user's login): sheets + transcript + signals + profile
                -> strict JSON report; hook quote verified against transcript
  -> store      SQLite + per-analysis folder in data/
```

Backend: Python 3.12, FastAPI, SQLite. Frontend: plain HTML/CSS/JS, no build step.
Every generation (scripts, tools, chat, plan, voice learning) goes through one Claude
wrapper that runs isolated: no tools, no MCP, no user hooks.
