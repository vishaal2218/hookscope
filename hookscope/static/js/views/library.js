// S05 Library: every analysis, searchable and filterable.

import { api } from "../api.js";
import { clear, empty, fmtDate, h, pageHead, platformName, toast } from "../ui.js";

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "breakdown", label: "Breakdowns", test: (a) => a.mode === "breakdown" },
  { key: "draft", label: "Draft reviews", test: (a) => a.mode === "draft" },
  { key: "mine", label: "Mine", test: (a) => Boolean(a.is_mine) },
];
const SEARCH_DELAY_MS = 250;

export async function renderLibrary(main) {
  let filter = "all";
  let rows = [];
  let timer = null;
  const search = h("input", { type: "search", placeholder: "Search titles, creators, hooks…", "aria-label": "Search the library" });
  const seg = h("div", { class: "seg", role: "group", "aria-label": "Filter" });
  const grid = h("div", { class: "grid" });

  FILTERS.forEach((f) => seg.append(h("button", { type: "button", "aria-pressed": String(f.key === filter), onclick: () => {
    filter = f.key;
    seg.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(FILTERS[i].key === filter)));
    draw();
  } }, f.label)));

  function draw() {
    clear(grid);
    const shown = rows.filter(FILTERS.find((f) => f.key === filter).test);
    if (!shown.length) {
      grid.append(empty(rows.length ? "Nothing matches" : "Your library is empty",
        rows.length ? "Try another search or filter." : "Every video you analyse lands here.",
        rows.length ? null : h("a", { class: "btn", href: "#/" }, "Analyse a video")));
      return;
    }
    shown.forEach((a) => grid.append(tile(a)));
  }

  async function load() {
    try {
      rows = await api.get(`/api/analyses?q=${encodeURIComponent(search.value.trim())}`);
      draw();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(load, SEARCH_DELAY_MS);
  });

  main.append(pageHead("Library", "Everything you've studied", null), h("div", { class: "lib-tools" }, search, seg), grid);
  await load();
  return () => clearTimeout(timer);
}

function tile(a) {
  const status = a.status === "done"
    ? (a.verdict ? [a.verdict === "ready" ? "badge-good" : "badge-warn", a.verdict === "ready" ? "Ready" : "Needs work"] : null)
    : a.status === "failed" ? ["badge-signal", "Failed"] : ["badge-warn", "Working…"];
  return h("a", { class: "tile", href: `#/report/${a.id}` },
    a.has_thumb ? h("img", { class: "tile-thumb", src: `/media/${a.id}/thumb.jpg`, alt: "", loading: "lazy" })
      : h("div", { class: "tile-thumb ph" }, platformName(a.platform)),
    h("div", { class: "tile-body" },
      h("div", { class: "row" }, h("span", { class: "badge" }, platformName(a.platform)),
        h("span", { class: "badge" }, a.mode === "draft" ? "Draft" : "Breakdown"),
        a.kind === "carousel" || a.kind === "photo" ? h("span", { class: "badge" }, a.kind === "carousel" ? "Carousel" : "Photo") : null,
        a.is_mine ? h("span", { class: "badge badge-signal" }, "Mine") : null,
        status ? h("span", { class: `badge ${status[0]}` }, status[1]) : null),
      h("div", { class: "tile-title" }, a.title || "Untitled"),
      a.summary ? h("div", { class: "tile-sum" }, a.summary) : null,
      h("div", { class: "small muted" }, [a.author, fmtDate(a.created_at)].filter(Boolean).join(" · "))));
}
