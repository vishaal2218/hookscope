# Hookscope

Paste any video link (Instagram reel, YouTube, Shorts, TikTok, X, Facebook, Vimeo and most
video sites) or drop in a video file. Hookscope watches it frame by frame, listens to every
word, measures the pacing, then tells you why it works and what to film next, in your voice.

It is a from-scratch rebuild of the link-in, analysis-out part of getpattern.io, running
entirely on this Mac. The recon map is in `replica/recon.md`, the feature list in
`replica/features.csv`.

## Set up from GitHub

Needs a Mac with Apple silicon, [Homebrew](https://brew.sh) and the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (signed in, run `claude` once).

```bash
git clone https://github.com/vishaal2218/hookscope.git
cd hookscope
brew install uv ffmpeg
uv sync
uv run python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-turbo', local_dir='models/whisper-large-v3-turbo')"
./Hookscope.command
```

The speech model (about 1.5 GB) is downloaded into `models/` by the fourth command; it isn't stored in this repo. `data/` (your library and log) is created on first run. To get the menu-bar app, run `./mac/build-app.sh`.

## Start it

**The app:** open **Hookscope.app** (in Applications, or `build/` in this folder). It starts
the engine in the background and opens your browser at http://127.0.0.1:8777 (or the next
free port if another app has 8777). The magnifier in the menu bar has Open, Show Log, Show
Hookscope Folder and Quit. Quit stops the engine. Clicking the Dock icon again reopens the page.

**Or the Terminal way:** double-click **Hookscope.command**. Close that Terminal window to stop.

The app is a 300 KB wrapper: the engine, model and your data stay in this folder. If you move
or rename the folder, rebuild the app with `./mac/build-app.sh` (it signs with your free Apple
Development certificate, so macOS keeps your permission answers across rebuilds). The engine's
output goes to `data/hookscope.log`.

First launch may ask two one-time questions: access to the Documents folder (Allow) and, on the
first Instagram download, Chrome Safe Storage in Keychain (Always Allow).

## What you can do

| Page | What it does |
| --- | --- |
| Analyse | Paste a link or drop a file. **Breakdown** explains why a video or post works. **Draft review** checks your own video or carousel before you post. Add an optional question. Drop one video, or up to 20 images (and short clips) for a photo or carousel post; slides follow the file names (1.jpg, 2.jpg …). |
| Carousels and photos | Instagram `/p/` links, image tweets, Reddit galleries and similar. The report has a slide viewer, the cover as the hook, slide-by-slide notes, where people stop swiping, design notes and the caption. Ideas from a carousel become slide-by-slide carousel plans. |
| Report | The hook (its quote is checked against the transcript), scores, structure, what's working, what could be better, where viewers may swipe, on-screen text, sound, what the numbers say, a reusable template and three ideas for you. Draft reviews add a ready / needs-work verdict, stronger openers, timestamped fixes and a caption. Every timestamp plays the video from that moment. Export saves a Markdown copy. |
| Library | Every analysis, searchable. Filter by breakdowns, drafts or yours. |
| Weekly plan | Pick videos to learn from; get what keeps working, what to fix, a do-this-week checklist and a 7-day plan. |
| Scripts | Ready-to-film scripts: hook options, beats (say / show / on-screen text), shot list, caption. Editable and saved. |
| Ask | Chat about your library and your voice. |
| Quick tools | Hook generator, hook analyser, script generator, script analyser, idea generator, caption generator, bio generator. |
| Your voice | Niche, audience, pillars, tone, goals and facts about how you talk. Tick "This is my video" on your own reports, then press **Learn from my videos**. |
| Settings | Health check, which browser lends its login, Claude model, speech language. |

## How it works

```
link or file
  -> Getting the video    yt-dlp, 720p max; Instagram uses your Chrome login (read-only)
                          photo / carousel posts: gallery-dl, every slide in order;
                          each slide goes to Claude as its own labelled image
  -> Listening            Whisper large-v3-turbo on this Mac (models/), word timings
  -> Watching             ffmpeg: 6 frames from the first 3 s + frames after scene cuts,
                          laid out as two labelled contact sheets
  -> Measuring            cuts per 10 s, shot length, words per minute, first word,
                          dead air, loudness curve, music share
  -> Writing the report   Claude (your own Claude login via the claude CLI) reads the
                          sheets, transcript, measurements, public numbers and your
                          profile; the reply is checked before it is saved
```

Videos longer than 15 minutes are cut to their first 15 minutes for analysis.

## Privacy and cost

- Speech-to-text, frames and measurements run on this Mac. The video never leaves it.
- Claude receives two contact-sheet images, the transcript, the measurements and your
  profile, through your own Claude account. It uses your plan's usage, about one
  report-sized message per analysis. No API key is stored anywhere.
- The server only answers requests from this Mac (127.0.0.1) and refuses requests made
  by other websites.
- Data lives in `data/`: `hookscope.db` plus one folder per analysis (video, frames,
  transcript). Deleting an analysis deletes its folder.

## When something fails

| Problem | Fix |
| --- | --- |
| "Claude isn't signed in" | Terminal: `claude auth login` |
| Instagram refuses | Open instagram.com in Chrome and log in, then Retry. Or save the reel and drop the file in. |
| YouTube or another site suddenly fails | Update the downloaders: `uv pip install -U yt-dlp gallery-dl` in this folder |
| Hindi or Hinglish comes out wrong | Settings, Speech language: Hindi |
| Carousel link refused | Open the post in Chrome while logged in, then Retry. Or save the slides and drop the images in. |

## Not included (and why)

Connecting Instagram / TikTok accounts and private insights (needs each platform's app
review), cross-posting and scheduling (needs publishing approval), billing and weekly
emails (single-user local tool).

## For developers

```bash
uv sync
.venv/bin/python -m pytest -q
.venv/bin/python -m hookscope --no-browser
```

Code: `hookscope/` (FastAPI app, pipeline, prompts), `hookscope/static/` (plain HTML, CSS,
JS modules, no build step), `tests/`.
