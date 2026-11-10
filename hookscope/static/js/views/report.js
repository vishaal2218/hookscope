// S02-S04: live progress while running, then the Breakdown or Draft review report.

import { api } from "../api.js";
import { busy, copyButton, download, elapsed, empty, fmtDate, fmtNum, fmtTime, h, platformName, toast } from "../ui.js";

const POLL_MS = 1500;

export async function renderReport(main, id) {
  let pollTimer = null;
  let tickTimer = null;
  const stop = () => (clearTimeout(pollTimer), clearInterval(tickTimer));

  async function load() {
    let a;
    try {
      a = await api.get(`/api/analyses/${id}`);
    } catch (err) {
      main.replaceChildren(empty("Couldn't open this analysis", err.message, h("a", { class: "btn", href: "#/library" }, "Back to library")));
      return;
    }
    clearInterval(tickTimer);
    if (a.status === "queued" || a.status === "running") {
      main.replaceChildren(progressView(a));
      tickTimer = setInterval(() => updateTimers(main, a), 250);
      pollTimer = setTimeout(load, POLL_MS);
    } else if (a.status === "failed") {
      main.replaceChildren(progressView(a));
    } else {
      main.replaceChildren(reportView(a, load));
    }
  }

  await load();
  return stop;
}

// Progress ----------------------------------------------------------------

function progressView(a) {
  const failed = a.status === "failed";
  const steps = h("ol", { class: "steps" }, (a.steps || []).map((s) =>
    h("li", { class: `step is-${s.status}`, dataset: { started: s.started || "", ended: s.ended || "" } },
      h("span", { class: "step-dot", "aria-hidden": "true" }),
      h("span", {}, s.label),
      h("span", { class: "step-time" }, s.started ? elapsed(s.started, s.ended) : ""))));
  const retry = h("button", { class: "btn", onclick: async (e) => {
    const done = busy(e.currentTarget, "Retrying…");
    try {
      await api.post(`/api/analyses/${a.id}/retry`);
      location.reload();
    } catch (err) {
      toast(err.message, "error");
      done();
    }
  } }, "Retry");
  return h("section", { class: "progress" },
    h("p", { class: "kicker" }, failed ? "Stopped" : a.status === "queued" ? `In line${a.queue_position > 1 ? ` (#${a.queue_position})` : ""}` : "Working"),
    h("h1", {}, a.title || shortUrl(a.source_url) || "Your video"),
    h("p", { class: "lede" }, failed ? "This one didn't finish." : "Usually about a minute for a reel. You can leave this page; it keeps going."),
    steps,
    failed ? h("div", { class: "stack" }, h("div", { class: "alert", role: "alert" }, a.error || "Unknown error"),
      h("div", { class: "row" }, retry, deleteButton(a))) : null);
}

function updateTimers(main) {
  main.querySelectorAll(".step.is-running").forEach((li) => {
    li.querySelector(".step-time").textContent = elapsed(Number(li.dataset.started), null);
  });
}

function shortUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    return `${u.hostname.replace(/^www\./, "")}${u.pathname}`.slice(0, 60);
  } catch {
    return url.slice(0, 60);
  }
}

// Report ------------------------------------------------------------------

function reportView(a, reload) {
  if (POST_KINDS.includes(a.kind)) return postReportView(a, reload);
  const r = a.report || {};
  const video = a.video ? h("video", { src: `/media/${a.id}/${a.video}`, controls: true, playsinline: true, preload: "metadata" }) : null;
  const seek = (t) => {
    if (!video || t === null || t === undefined) return;
    video.currentTime = Number(t);
    video.play().catch(() => {});
    video.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };
  const chip = (t) => (t === null || t === undefined ? h("span") : h("button", { class: "chip", type: "button", onclick: () => seek(t), title: "Play from here" }, fmtTime(t)));
  const ctx = { a, r, seek, chip };
  return h("article", {},
    header(a, r, reload),
    h("div", { class: "report" },
      h("aside", { class: "report-aside" }, video ? h("div", { class: "player" }, video) : null, metrics(a), spark(a), frames(a, seek)),
      h("div", { class: "report-main" }, a.mode === "draft" ? draftSections(ctx) : breakdownSections(ctx), transcript(a, chip))));
}

function header(a, r, reload) {
  const mine = h("input", { type: "checkbox", checked: Boolean(a.is_mine) });
  const noun = POST_KINDS.includes(a.kind) ? "post" : "video";
  mine.addEventListener("change", async () => {
    try {
      await api.patch(`/api/analyses/${a.id}`, { is_mine: mine.checked });
      toast(mine.checked ? `Marked as your ${noun}. It will teach Your voice.` : "No longer marked as yours.");
    } catch (err) {
      toast(err.message, "error");
      mine.checked = !mine.checked;
    }
  });
  const reanalyse = h("button", { class: "btn btn-ghost btn-small", onclick: async () => {
    try {
      await api.post(`/api/analyses/${a.id}/retry`);
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  } }, "Re-run");
  return h("header", { class: "report-head" },
    h("div", {},
      h("p", { class: "kicker" }, a.mode === "draft" ? "Draft review" : "Breakdown", " · ", platformName(a.platform), r.format ? ` · ${r.format}` : ""),
      h("h1", {}, a.title || "Untitled video"),
      h("p", { class: "muted small" }, [a.author, fmtDate(a.created_at), a.duration ? `${Math.round(a.duration)} s` : null].filter(Boolean).join(" · "),
        a.source_url ? [" · ", h("a", { href: a.source_url, target: "_blank", rel: "noopener noreferrer" }, "open original")] : null),
      r.truncated ? h("p", { class: "badge badge-warn" }, "Only the first 15 minutes were analysed") : null),
    h("div", { class: "row" }, h("label", { class: "check" }, mine, "This is mine"),
      h("button", { class: "btn btn-ghost btn-small", onclick: () => download(`${slug(a.title)}.md`, toMarkdown(a)) }, "Export"),
      reanalyse, deleteButton(a)));
}

function deleteButton(a) {
  return h("button", { class: "btn btn-danger btn-small", onclick: async () => {
    if (!confirm("Delete this analysis and its video from this Mac?")) return;
    try {
      await api.del(`/api/analyses/${a.id}`);
      location.hash = "#/library";
    } catch (err) {
      toast(err.message, "error");
    }
  } }, "Delete");
}

function metrics(a) {
  const m = a.metrics || {};
  const s = a.signals || {};
  const eng = m.views && (m.likes || m.comments) ? `${(((m.likes || 0) + (m.comments || 0)) / m.views * 100).toFixed(1)}%` : null;
  const tiles = [
    ["Views", fmtNum(m.views)], ["Likes", fmtNum(m.likes)], ["Comments", fmtNum(m.comments)],
    ["Engagement", eng || "–"], ["Cuts / 10 s", s.pacing ? s.pacing.cuts_per_10s : "–"], ["Words / min", s.speech ? s.speech.words_per_minute || "–" : "–"],
    ["First word", s.speech && s.speech.first_word_at !== null ? `${s.speech.first_word_at}s` : "–"], ["Avg shot", s.pacing ? `${s.pacing.average_shot_seconds}s` : "–"], ["Posted", m.upload_date || "–"],
  ];
  return h("div", { class: "metrics" }, tiles.map(([label, value]) => h("div", { class: "metric" }, h("b", {}, String(value)), h("span", {}, label))));
}

function spark(a) {
  const audio = a.signals && a.signals.audio;
  if (!audio || !audio.curve || audio.curve.length < 2) return null;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "spark");
  svg.setAttribute("viewBox", "0 0 300 52");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Loudness over time, red ticks are cuts");
  const lo = -60, hi = 0, n = audio.curve.length;
  const pts = audio.curve.map((db, i) => `${(i / (n - 1)) * 300},${50 - ((Math.max(lo, Math.min(hi, db)) - lo) / (hi - lo)) * 46}`);
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", `M${pts.join(" L")}`);
  svg.append(path);
  const dur = a.signals.duration || 1;
  for (const c of a.signals.cut_times || []) {
    const line = document.createElementNS(ns, "line");
    const x = (c / dur) * 300;
    Object.entries({ x1: x, x2: x, y1: 0, y2: 6, class: "cut" }).forEach(([k, v]) => line.setAttribute(k, v));
    svg.append(line);
  }
  return h("div", { class: "card" }, h("p", { class: "small muted" }, "Loudness across the video · red ticks are cuts"), svg);
}

function frames(a, seek) {
  if (!a.frames || !a.frames.length) return null;
  return h("details", { class: "card" }, h("summary", {}, `Key frames (${a.frames.length})`),
    h("div", { class: "frames" }, a.frames.map((f) =>
      h("button", { type: "button", onclick: () => seek(f.time), title: `Play from ${fmtTime(f.time)}` },
        h("img", { src: `/media/${a.id}/frames/${f.file}`, alt: `Frame at ${fmtTime(f.time)}`, loading: "lazy" }),
        h("span", {}, fmtTime(f.time))))));
}

// Sections ------------------------------------------------------------------

function section(title, ...body) {
  return h("section", { class: "card" }, h("h2", {}, title), ...body);
}

function scoreRow(scores) {
  const keys = ["hook", "pacing", "flow", "clarity", "payoff", "design"].filter((k) => scores && scores[k]);
  if (!keys.length) return null;
  return h("div", { class: "scores card" }, keys.map((k) =>
    h("div", { class: `score ${scores[k] >= 8 ? "hi" : scores[k] <= 4 ? "lo" : ""}` }, h("b", {}, scores[k]), h("span", {}, k))));
}

function hookCard(hook, chip, extra) {
  if (!hook) return null;
  const check = { verified: ["badge-good", "Checked against the transcript"], corrected: ["badge-warn", "Quote corrected to the real words"],
    not_spoken: ["badge", "On-screen / visual hook"], unverified: ["badge", "Not checked"],
    on_slide: ["badge", "Read from the slide"] }[hook.quote_check] || ["badge", ""];
  return h("section", { class: "card hook-card" },
    h("div", { class: "card-head" }, h("h2", {}, hook.slide ? "The cover" : "The hook"), h("div", { class: "row" }, chip(hook.slide ?? hook.start), check[1] ? h("span", { class: `badge ${check[0]}` }, check[1]) : null)),
    h("p", { class: "hook-quote" }, hook.quote || "No opening line"),
    h("dl", { class: "kv" },
      hook.type ? [h("dt", {}, "Move"), h("dd", {}, hook.type)] : null,
      hook.visual ? [h("dt", {}, "On screen"), h("dd", {}, hook.visual)] : null,
      hook.why_it_works ? [h("dt", {}, "Why it works"), h("dd", {}, hook.why_it_works)] : null,
      hook.assessment ? [h("dt", {}, "Assessment"), h("dd", {}, hook.assessment)] : null,
      hook.strength ? [h("dt", {}, "Strength"), h("dd", {}, `${hook.strength} / 10`)] : null),
    hook.use_it ? h("div", { class: "use-it" }, h("strong", {}, "Use it yourself: "), hook.use_it) : null,
    extra || null);
}

function itemList(items, chip, render, cls = "") {
  if (!items || !items.length) return h("p", { class: "muted" }, "Nothing stood out here.");
  return h("ul", { class: `items ${cls}` }, items.map((it) => h("li", { class: it.priority === "high" ? "fix-high" : "" },
    h("div", { class: "when" }, chip(it.slide ?? it.at ?? it.start)), h("div", {}, render(it)))));
}

const titled = (title, detail) => [h("div", { class: "items-title" }, title), detail ? h("p", {}, detail) : null];

function structure(r, chip, duration) {
  if (!r.beats || !r.beats.length) return null;
  const total = duration || r.beats[r.beats.length - 1].end || 1;
  const bar = h("div", { class: "beatbar", "aria-hidden": "true" }, r.beats.map((b) => {
    const seg = h("i", { title: b.label });
    seg.style.width = `${Math.max(2, ((b.end - b.start) / total) * 100)}%`;
    return seg;
  }));
  return section("Structure", bar, itemList(r.beats, chip, (b) => titled(b.label, b.what_happens)));
}

function ideasSection(a, ideas) {
  if (!ideas || !ideas.length) return null;
  return section("Ideas for you", h("div", { class: "ideas" }, ideas.map((idea) => {
    const fmt = String(idea.format || (POST_KINDS.includes(a.kind) ? "carousel" : "")).toLowerCase();
    const btn = h("button", { class: "btn btn-small" }, fmt.includes("carousel") ? "Plan the carousel" : "Generate script");
    btn.addEventListener("click", async () => {
      const done = busy(btn, "Writing… about a minute");
      try {
        const s = await api.post("/api/scripts", { idea, analysis_id: a.id });
        location.hash = `#/script/${s.id}`;
      } catch (err) {
        toast(err.message, "error");
        done();
      }
    });
    return h("div", { class: "idea" }, h("h3", {}, idea.title), idea.hook ? h("p", { class: "line" }, `“${idea.hook}”`) : null,
      h("p", {}, idea.angle), idea.why_for_you ? h("p", { class: "small muted" }, idea.why_for_you) : null, btn);
  })));
}

function breakdownSections({ a, r, chip }) {
  return [
    section("Why it works", h("p", {}, r.summary || "")),
    hookCard(r.hook, chip),
    scoreRow(r.scores),
    structure(r, chip, a.duration),
    section("What's working", itemList(r.working, chip, (w) => titled(w.title, w.detail), "good")),
    section("Could be even better", itemList(r.better, chip, (b) => titled(b.title, b.detail))),
    r.retention_risks && r.retention_risks.length ? section("Where viewers may swipe", itemList(r.retention_risks, chip, (x) => titled(x.reason))) : null,
    r.on_screen_text && r.on_screen_text.length ? section("On-screen text", itemList(r.on_screen_text, chip, (x) => titled(x.text))) : null,
    r.audio ? section("Sound and delivery", h("dl", { class: "kv" },
      h("dt", {}, "Delivery"), h("dd", {}, r.audio.delivery || "–"), h("dt", {}, "Music"), h("dd", {}, r.audio.music || "–"),
      h("dt", {}, "Energy"), h("dd", {}, r.audio.energy || "–"))) : null,
    r.performance_read ? section("What the numbers say", h("p", {}, r.performance_read)) : null,
    r.template ? section("Reusable template", h("div", { class: "template" }, r.template), h("div", { class: "row" }, copyButton(r.template, "Copy template"))) : null,
    ideasSection(a, r.ideas),
  ];
}

function draftSections({ a, r, chip }) {
  const openers = r.hook && r.hook.stronger_openers && r.hook.stronger_openers.length
    ? h("div", {}, h("h3", {}, "Stronger openers to try"), h("ul", { class: "openers" },
      r.hook.stronger_openers.map((line) => h("li", {}, h("span", {}, `“${line}”`), copyButton(line)))))
    : null;
  const caption = r.caption && r.caption.text
    ? `${r.caption.text}\n\n${(r.caption.hashtags || []).map((t) => `#${String(t).replace(/^#/, "")}`).join(" ")}`.trim() : "";
  return [
    h("div", { class: `verdict ${r.verdict === "ready" ? "ready" : "needs_work"}` },
      h("b", {}, r.verdict === "ready" ? "Ready to post" : "Needs work"), h("span", {}, r.verdict_reason || "")),
    hookCard(r.hook, chip, openers),
    r.answer_to_note ? section("Your question", h("p", { class: "muted small" }, a.note || ""), h("p", {}, r.answer_to_note)) : null,
    section("Overall", h("p", {}, r.summary || "")),
    scoreRow(r.scores),
    section("Keep these", itemList(r.working, chip, (w) => titled(w.title, w.detail), "good")),
    section("Where you might lose them", itemList(r.lose_them, chip, (x) => titled(x.reason, x.fix ? `Fix: ${x.fix}` : ""))),
    section("Fixes before you post", itemList(r.fixes, chip, (f) => titled(f.change, f.why))),
    caption ? section("Caption", h("p", { class: "template" }, caption), h("div", { class: "row" }, copyButton(caption, "Copy caption"))) : null,
    structure(r, chip, a.duration),
  ];
}

function transcript(a, chip) {
  const segs = (a.transcript && a.transcript.segments) || [];
  if (!segs.length) return section("Transcript", h("p", { class: "muted" }, "No speech was detected in this video."));
  const text = segs.map((s) => `[${fmtTime(s.start)}] ${s.text}`).join("\n");
  return h("details", { class: "card transcript" },
    h("summary", {}, `Read the transcript${a.transcript.language ? ` (${a.transcript.language})` : ""}`),
    h("div", { class: "row" }, copyButton(text, "Copy transcript")),
    h("div", {}, segs.map((s) => h("p", {}, chip(s.start), h("span", {}, s.text)))));
}

// Photo and carousel posts ----------------------------------------------------

const POST_KINDS = ["photo", "carousel"];

function slideViewer(a) {
  const slides = (a.frames || []).filter((f) => f.kind === "slide");
  const stage = h("div", { class: "viewer-stage" });
  const counter = h("span", { class: "viewer-count mono" });
  const thumbs = h("div", { class: "viewer-thumbs", role: "group", "aria-label": "Slides" });
  let current = 1;
  const goTo = (n, scroll = true) => {
    if (!slides.length) return;
    current = Math.min(Math.max(1, Number(n) || 1), slides.length);
    const f = slides[current - 1];
    stage.replaceChildren(f.video
      ? h("video", { src: `/media/${a.id}/slides/${f.video}`, controls: true, playsinline: true, poster: `/media/${a.id}/frames/${f.file}` })
      : h("img", { src: `/media/${a.id}/frames/${f.file}`, alt: `Slide ${current} of ${slides.length}` }));
    counter.textContent = `${current} / ${slides.length}`;
    thumbs.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-current", String(i + 1 === current)));
    if (scroll) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };
  slides.forEach((f, i) => thumbs.append(h("button", { type: "button", onclick: () => goTo(i + 1, false), title: `Slide ${i + 1}` },
    h("img", { src: `/media/${a.id}/frames/${f.file}`, alt: "", loading: "lazy" }), f.video ? h("span", {}, "Video") : null)));
  const nav = (step, label, text) => h("button", { class: "btn btn-ghost btn-small", type: "button", "aria-label": label, onclick: () => goTo(current + step, false) }, text);
  const el = h("div", { class: "viewer", tabindex: "0", "aria-label": "Slide viewer, use the arrow keys" }, stage,
    slides.length > 1 ? h("div", { class: "spread" }, nav(-1, "Previous slide", "← Prev"), counter, nav(1, "Next slide", "Next →")) : null,
    slides.length > 1 ? thumbs : null);
  el.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") goTo(current - 1, false);
    if (e.key === "ArrowRight") goTo(current + 1, false);
  });
  goTo(1, false);
  return { el, goTo };
}

function postMetrics(a) {
  const m = a.metrics || {};
  const s = a.signals || {};
  const eng = m.followers && (m.likes || m.comments) ? `${(((m.likes || 0) + (m.comments || 0)) / m.followers * 100).toFixed(1)}%` : "–";
  const tiles = [
    ["Likes", fmtNum(m.likes)], ["Comments", fmtNum(m.comments)], ["Engagement", eng],
    ["Slides", s.slides ?? "–"], ["Video slides", s.video_slides ?? "–"], ["Shape", s.aspect || "–"],
    ["Views", fmtNum(m.views)], ["Followers", fmtNum(m.followers)], ["Posted", m.upload_date || "–"],
  ];
  return h("div", { class: "metrics" }, tiles.map(([label, value]) => h("div", { class: "metric" }, h("b", {}, String(value)), h("span", {}, label))));
}

function postReportView(a, reload) {
  const r = a.report || {};
  const viewer = slideViewer(a);
  const chip = (n) => (n === null || n === undefined ? h("span")
    : h("button", { class: "chip", type: "button", onclick: () => viewer.goTo(n), title: "Show this slide" }, `Slide ${n}`));
  const sections = a.mode === "draft" ? postDraftSections(a, r, chip) : postBreakdownSections(a, r, chip);
  return h("article", {},
    header(a, r, reload),
    h("div", { class: "report" },
      h("aside", { class: "report-aside" }, viewer.el, postMetrics(a)),
      h("div", { class: "report-main" }, sections, slideSpeech(a, chip))));
}

function slidesSection(slides, chip) {
  if (!slides || !slides.length) return null;
  return section("Slide by slide", itemList(slides, chip, (s) => [
    h("div", { class: "items-title" }, s.role || `Slide ${s.slide}`),
    s.text ? h("p", { class: "slide-text" }, `“${s.text}”`) : null,
    s.note ? h("p", {}, s.note) : null]));
}

function captionBlock(r) {
  if (!r.caption || !r.caption.text) return null;
  const text = `${r.caption.text}\n\n${(r.caption.hashtags || []).map((t) => `#${String(t).replace(/^#/, "")}`).join(" ")}`.trim();
  return section("Caption", h("p", { class: "template" }, text), h("div", { class: "row" }, copyButton(text, "Copy caption")));
}

function postBreakdownSections(a, r, chip) {
  const caption = (a.metrics || {}).caption;
  return [
    section("Why it works", h("p", {}, r.summary || "")),
    hookCard(r.hook, chip),
    scoreRow(r.scores),
    slidesSection(r.slides, chip),
    section("What's working", itemList(r.working, chip, (w) => titled(w.title, w.detail), "good")),
    section("Could be even better", itemList(r.better, chip, (b) => titled(b.title, b.detail))),
    r.drop_off && r.drop_off.length ? section("Where people stop swiping", itemList(r.drop_off, chip, (x) => titled(x.reason))) : null,
    r.design ? section("Design", h("dl", { class: "kv" },
      h("dt", {}, "Type"), h("dd", {}, r.design.typography || "–"), h("dt", {}, "Layout"), h("dd", {}, r.design.layout || "–"),
      h("dt", {}, "Colour"), h("dd", {}, r.design.color || "–"), h("dt", {}, "As a set"), h("dd", {}, r.design.consistency || "–"))) : null,
    r.caption_read ? section("The caption", caption ? h("p", { class: "template" }, caption.slice(0, 600)) : null, h("p", {}, r.caption_read)) : null,
    r.performance_read ? section("What the numbers say", h("p", {}, r.performance_read)) : null,
    r.template ? section("Reusable template", h("div", { class: "template" }, r.template), h("div", { class: "row" }, copyButton(r.template, "Copy template"))) : null,
    ideasSection(a, r.ideas),
  ];
}

function postDraftSections(a, r, chip) {
  const openers = r.hook && r.hook.stronger_openers && r.hook.stronger_openers.length
    ? h("div", {}, h("h3", {}, "Stronger covers to try"), h("ul", { class: "openers" },
      r.hook.stronger_openers.map((line) => h("li", {}, h("span", {}, `“${line}”`), copyButton(line)))))
    : null;
  return [
    h("div", { class: `verdict ${r.verdict === "ready" ? "ready" : "needs_work"}` },
      h("b", {}, r.verdict === "ready" ? "Ready to post" : "Needs work"), h("span", {}, r.verdict_reason || "")),
    hookCard(r.hook, chip, openers),
    r.answer_to_note ? section("Your question", h("p", { class: "muted small" }, a.note || ""), h("p", {}, r.answer_to_note)) : null,
    section("Overall", h("p", {}, r.summary || "")),
    scoreRow(r.scores),
    section("Keep these", itemList(r.working, chip, (w) => titled(w.title, w.detail), "good")),
    section("Where people may stop swiping", itemList(r.lose_them, chip, (x) => titled(x.reason, x.fix ? `Fix: ${x.fix}` : ""))),
    section("Fixes before you post", itemList(r.fixes, chip, (f) => titled(f.change, f.why))),
    slidesSection(r.slides, chip),
    captionBlock(r),
  ];
}

function slideSpeech(a, chip) {
  const segs = (a.transcript && a.transcript.segments) || [];
  if (!segs.length) return null;
  return h("details", { class: "card transcript" }, h("summary", {}, "Speech in the video slides"),
    h("div", {}, segs.map((s) => h("p", {}, chip(s.slide), h("span", {}, s.text)))));
}

// Export ------------------------------------------------------------------

function slug(text) {
  return (text || "hookscope-report").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "hookscope-report";
}

function toMarkdown(a) {
  const r = a.report || {};
  const t = (x) => (x === null || x === undefined ? "" : `[${fmtTime(x)}] `);
  const list = (items, f) => (items || []).map((i) => `- ${i.slide ? `[Slide ${i.slide}] ` : t(i.at ?? i.start)}${f(i)}`).join("\n");
  const out = [`# ${a.title || "Video"}`, `${a.mode === "draft" ? "Draft review" : "Breakdown"} · ${platformName(a.platform)} · ${fmtDate(a.created_at)}`];
  if (a.source_url) out.push(a.source_url);
  if (r.verdict) out.push(`\n**Verdict:** ${r.verdict === "ready" ? "Ready to post" : "Needs work"}. ${r.verdict_reason || ""}`);
  out.push(`\n## Summary\n${r.summary || ""}`);
  if (r.hook) out.push(`\n## The hook\n> ${r.hook.quote || ""}\n\n${r.hook.why_it_works || r.hook.assessment || ""}${r.hook.use_it ? `\n\n**Use it:** ${r.hook.use_it}` : ""}`);
  if (r.hook && r.hook.stronger_openers) out.push(r.hook.stronger_openers.map((o) => `- ${o}`).join("\n"));
  if (r.slides && r.slides.length) out.push(`\n## Slide by slide\n${list(r.slides, (s) => `**${s.role || ""}** ${s.text ? `"${s.text}" ` : ""}${s.note || ""}`)}`);
  out.push(`\n## What's working\n${list(r.working, (w) => `**${w.title}**: ${w.detail || ""}`)}`);
  if (r.drop_off && r.drop_off.length) out.push(`\n## Where people stop swiping\n${list(r.drop_off, (x) => x.reason)}`);
  if (r.better) out.push(`\n## Could be better\n${list(r.better, (b) => `**${b.title}**: ${b.detail || ""}`)}`);
  if (r.lose_them) out.push(`\n## Where you might lose them\n${list(r.lose_them, (x) => `${x.reason} Fix: ${x.fix || ""}`)}`);
  if (r.fixes) out.push(`\n## Fixes\n${list(r.fixes, (f) => `${f.change} (${f.why || ""})`)}`);
  if (r.template) out.push(`\n## Template\n${r.template}`);
  if (r.ideas) out.push(`\n## Ideas\n${r.ideas.map((i) => `- **${i.title}**: "${i.hook}" ${i.angle || ""}`).join("\n")}`);
  if (r.caption) out.push(`\n## Caption\n${r.caption.text}\n${(r.caption.hashtags || []).map((x) => `#${x}`).join(" ")}`);
  return out.join("\n");
}
