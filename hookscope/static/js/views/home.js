// S01 Analyse: paste a link or drop a file, choose Breakdown or Draft review.

import { api } from "../api.js";
import { busy, fmtDate, h, pageHead, platformName, toast } from "../ui.js";

const MODES = [
  { key: "breakdown", label: "Breakdown", hint: "Why does this video or post work? Hook, structure, pacing or slides, and ideas for you." },
  { key: "draft", label: "Draft review", hint: "Check your own video or carousel before posting: hook, drop-off moments, fixes, caption." },
];
const VIDEO_EXT = [".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"];
const IMAGE_EXT = [".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".avif"];
const ACCEPT = [...VIDEO_EXT, ...IMAGE_EXT].join(",");
const MAX_SLIDES = 20;
const DROP_LABEL = () => [h("strong", {}, "Drop a video, or images for a carousel"), " or click to choose (MP4, MOV, JPG, PNG…)"];
const ext = (name) => (name.match(/\.[^.]+$/) || [""])[0].toLowerCase();

// Files in name order (1.jpg, 2.jpg, 10.jpg), so carousel slides keep their sequence.
export function orderFiles(list) {
  return [...list].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
}

export function checkFiles(files) {
  if (!files.length) return "Choose a file.";
  if (files.some((f) => ![...VIDEO_EXT, ...IMAGE_EXT].includes(ext(f.name)))) return "Use video files or images (JPG, PNG, WebP, HEIC).";
  const videos = files.filter((f) => VIDEO_EXT.includes(ext(f.name)));
  if (files.length > 1 && videos.length === files.length) return "Drop one video at a time, or images for a carousel.";
  if (files.length > MAX_SLIDES) return `A carousel can have at most ${MAX_SLIDES} slides.`;
  return null;
}

export async function renderAnalyse(main) {
  let mode = "breakdown";
  let files = [];

  const urlInput = h("input", { type: "text", inputmode: "url", spellcheck: "false", placeholder: "Paste a link: Instagram reel or post, YouTube, Shorts, TikTok, X…", "aria-label": "Video or post link", autocomplete: "off" });
  const note = h("textarea", { placeholder: "Optional. e.g. Is my hook strong enough? What made this one blow up?", rows: 2 });
  const mine = h("input", { type: "checkbox" });
  const hint = h("p", { class: "hint" });
  const seg = h("div", { class: "seg", role: "group", "aria-label": "Analysis type" });
  const fileLabel = h("span", {}, DROP_LABEL());
  const picker = h("input", { type: "file", accept: ACCEPT, multiple: true, hidden: true });
  const drop = h("div", { class: "drop", role: "button", tabindex: "0" }, fileLabel);
  const go = h("button", { class: "btn btn-signal", type: "submit" }, "Analyse");

  function setMode(next) {
    mode = next;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    hint.textContent = MODES.find((m) => m.key === mode).hint;
    if (mode === "draft") mine.checked = true;
  }
  MODES.forEach((m) => seg.append(h("button", { type: "button", dataset: { mode: m.key }, onclick: () => setMode(m.key) }, m.label)));

  function chooseFiles(list) {
    const picked = orderFiles(list || []);
    if (!picked.length) return;
    const problem = checkFiles(picked);
    if (problem) {
      toast(problem, "error");
      return;
    }
    files = picked;
    const mb = (picked.reduce((sum, f) => sum + f.size, 0) / 1e6).toFixed(1);
    const isPost = picked.length > 1 || IMAGE_EXT.includes(ext(picked[0].name));
    const what = !isPost ? picked[0].name : picked.length > 1 ? `Carousel of ${picked.length} slides` : `Photo: ${picked[0].name}`;
    fileLabel.replaceChildren(h("strong", {}, what), ` · ${mb} MB · `, h("span", { class: "muted" }, "click to change"));
    urlInput.value = "";
    if (mode === "breakdown") setMode("draft");
  }
  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), picker.click()));
  picker.addEventListener("change", () => chooseFiles(picker.files));
  drop.addEventListener("dragover", (e) => (e.preventDefault(), drop.classList.add("is-over")));
  drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("is-over");
    chooseFiles(e.dataTransfer.files);
  });
  urlInput.addEventListener("input", () => {
    if (urlInput.value.trim() && files.length) {
      files = [];
      fileLabel.replaceChildren(...DROP_LABEL());
    }
  });

  async function submit(e) {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (!url && !files.length) {
      toast("Paste a link or choose a file first.", "error");
      urlInput.focus();
      return;
    }
    const done = busy(go, files.length ? "Uploading…" : "Starting…");
    try {
      let row;
      if (files.length) {
        const form = new FormData();
        files.forEach((f) => form.append("files", f));
        form.append("mode", mode);
        form.append("note", note.value);
        form.append("is_mine", String(mine.checked));
        row = await api.upload("/api/analyses/upload", form);
      } else {
        row = await api.post("/api/analyses", { url, mode, note: note.value, is_mine: mine.checked });
      }
      location.hash = `#/report/${row.id}`;
    } catch (err) {
      toast(err.message, "error");
      done();
    }
  }

  setMode("breakdown");
  const form = h("form", { class: "composer", onsubmit: submit },
    h("div", { class: "url-row" }, urlInput, go),
    h("div", { class: "composer-opts" }, seg, h("label", { class: "check" }, mine, "This is mine")),
    hint,
    h("label", { class: "field" }, "Anything you want to know? ", h("span", { class: "muted" }, "(optional)")),
    note,
    h("div", { class: "or" }, "or"),
    drop, picker,
    h("div", { class: "platforms" },
      ["Instagram reels & carousels", "YouTube & Shorts", "TikTok", "X", "Facebook", "Vimeo", "and most video sites"].map((p) => h("span", { class: "badge" }, p))));

  const recent = h("section", { class: "recent" });
  main.append(
    pageHead("Study a video", "What are we learning from today?", "Paste any video link. Hookscope watches it frame by frame, listens to every word, measures the pacing, then tells you why it works and what to film next."),
    form, recent);
  urlInput.focus();

  try {
    const rows = (await api.get("/api/analyses")).slice(0, 5);
    if (rows.length) {
      recent.append(h("h2", {}, "Recent"), ...rows.map(recentRow));
    }
  } catch (err) {
    recent.append(h("p", { class: "muted" }, err.message));
  }
}

export function recentRow(a) {
  const status = a.status === "done" ? (a.verdict ? (a.verdict === "ready" ? "Ready" : "Needs work") : "Done") : a.status === "failed" ? "Failed" : "Working…";
  const kind = a.status === "failed" ? "badge-signal" : a.status === "done" ? "badge-good" : "badge-warn";
  return h("a", { class: "list-row", href: `#/report/${a.id}` },
    a.has_thumb ? h("img", { class: "list-thumb", src: `/media/${a.id}/thumb.jpg`, alt: "" }) : h("div", { class: "list-thumb" }),
    h("div", { class: "grow" },
      h("div", { class: "list-title" }, a.title || a.source_url || "Untitled"),
      h("div", { class: "small muted" }, `${platformName(a.platform)} · ${a.mode === "draft" ? "Draft review" : "Breakdown"} · ${fmtDate(a.created_at)}`)),
    h("span", { class: `badge ${kind}` }, status));
}
