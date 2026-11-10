// S12 Settings: health of every moving part, plus the three settings.

import { api } from "../api.js";
import { busy, h, pageHead, toast } from "../ui.js";

const BROWSERS = [["chrome", "Chrome"], ["safari", "Safari"], ["firefox", "Firefox"], ["brave", "Brave"], ["edge", "Edge"], ["", "None"]];
const MODELS = [["", "Plan default (recommended)"], ["opus", "Opus: best judgement"], ["sonnet", "Sonnet: faster"], ["haiku", "Haiku: fastest, lighter"]];
const LANGUAGES = [["", "Auto-detect"], ["en", "English"], ["hi", "Hindi"]];
const FIXES = {
  claude: "Open Terminal and run: claude auth login",
  ffmpeg: "Open Terminal and run: brew install ffmpeg",
  whisper: "The speech model folder is missing. Copy it back into hookscope/models/.",
};

function select(options, value) {
  const el = h("select", {}, options.map(([v, label]) => h("option", { value: v }, label)));
  el.value = value || "";
  return el;
}

export async function renderSettings(main) {
  const [health, settings] = await Promise.all([api.get("/api/health"), api.get("/api/settings")]);
  const browser = select(BROWSERS, settings.cookies_browser);
  const model = select(MODELS, settings.model);
  const language = select(LANGUAGES, settings.language);
  const save = h("button", { class: "btn btn-signal", type: "submit" }, "Save");

  async function onSave(e) {
    e.preventDefault();
    const done = busy(save, "Saving…");
    try {
      await api.put("/api/settings", { cookies_browser: browser.value, model: model.value, language: language.value });
      toast("Saved.");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      done();
    }
  }

  const row = (name, item, key) => h("li", {},
    h("b", {}, name),
    h("span", { class: `badge ${item.ok ? "badge-good" : "badge-signal"}` }, item.ok ? "OK" : "Needs a fix"),
    h("span", { class: "small muted" }, item.ok ? item.detail : FIXES[key] || item.detail));

  const fixAccess = h("button", { class: "btn btn-signal btn-small", type: "button" }, "Fix browser access");
  fixAccess.addEventListener("click", async () => {
    try {
      await api.post("/api/open-privacy-settings");
      toast("System Settings is open at Full Disk Access. Switch on Hookscope, choose Quit & Reopen, then try again.");
    } catch (err) {
      toast(err.message, "error");
    }
  });
  const browserRow = () => {
    const b = health.browser || { ok: true, detail: "" };
    return h("li", {}, h("b", {}, "Browser login"),
      h("span", { class: `badge ${b.ok ? "badge-good" : "badge-signal"}` }, b.ok ? "OK" : "Needs a fix"),
      h("span", { class: "small muted" }, b.state === "blocked"
        ? "macOS is blocking Hookscope from reading your browser's login, so Instagram downloads fail. Click the button, then switch on Hookscope in the list."
        : b.detail),
      b.state === "blocked" ? fixAccess : null);
  };

  main.append(
    pageHead("Settings", "Under the hood", null),
    h("div", { class: "two" },
      h("section", { class: "card" }, h("h2", {}, "Health"),
        h("ul", { class: "health" },
          row("Claude", health.claude, "claude"), browserRow(), row("Downloader", health.ytdlp, "ytdlp"), row("ffmpeg", health.ffmpeg, "ffmpeg"), row("Speech model", health.whisper, "whisper"),
          h("li", {}, h("b", {}, "Disk free"), h("span", { class: `badge ${health.disk_free_gb > 5 ? "badge-good" : "badge-warn"}` }, `${health.disk_free_gb} GB`),
            h("span", { class: "small muted" }, "Each analysis keeps its video. Delete old ones from their report page."))),
        h("p", { class: "hint" }, "If downloads start failing, update the downloader: open Terminal in the hookscope folder and run: .venv/bin/python -m pip install -U yt-dlp"),
        h("p", { class: "hint" }, `Your data lives in ${health.data_dir}`)),
      h("form", { class: "card", onsubmit: onSave }, h("h2", {}, "Settings"),
        h("label", { class: "field" }, "Browser to borrow logins from"), browser,
        h("p", { class: "hint" }, "Instagram usually needs you to be logged in. Hookscope reads that browser's cookies on this Mac only, read-only."),
        h("label", { class: "field" }, "Claude model"), model,
        h("label", { class: "field" }, "Speech language"), language,
        h("p", { class: "hint" }, "Auto works for most videos. Pick Hindi if Hindi or Hinglish videos come out wrong."),
        h("div", { class: "row" }, save))));
}
