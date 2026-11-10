// Hash router: each view renders into <main> and may return a cleanup function.

// The home view lives in home.js, not analyse.js: ad and tracker blockers block files named like "analyse.js".
import { renderAnalyse } from "./views/home.js";
import { renderReport } from "./views/report.js";
import { renderLibrary } from "./views/library.js";
import { renderVoice } from "./views/voice.js";
import { renderScripts, renderScript } from "./views/scripts.js";
import { renderChat } from "./views/chat.js";
import { renderTools } from "./views/tools.js";
import { renderPlan } from "./views/plan.js";
import { renderSettings } from "./views/settings.js";
import { clear, empty, h } from "./ui.js";

const ROUTES = [
  { pattern: /^\/?$/, nav: "analyse", view: renderAnalyse },
  { pattern: /^\/report\/([0-9a-f]{12})$/, nav: "library", view: renderReport },
  { pattern: /^\/library$/, nav: "library", view: renderLibrary },
  { pattern: /^\/voice$/, nav: "voice", view: renderVoice },
  { pattern: /^\/scripts$/, nav: "scripts", view: renderScripts },
  { pattern: /^\/script\/([0-9a-f]{12})$/, nav: "scripts", view: renderScript },
  { pattern: /^\/chat$/, nav: "chat", view: renderChat },
  { pattern: /^\/tools$/, nav: "tools", view: renderTools },
  { pattern: /^\/plan$/, nav: "plan", view: renderPlan },
  { pattern: /^\/settings$/, nav: "settings", view: renderSettings },
];

let cleanup = null;

async function route() {
  const path = location.hash.replace(/^#/, "") || "/";
  const main = document.getElementById("main");
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  clear(main);
  const match = ROUTES.map((r) => ({ r, m: path.match(r.pattern) })).find((x) => x.m);
  document.querySelectorAll(".nav a").forEach((a) => {
    const on = match && a.dataset.route === match.r.nav;
    a.classList.toggle("is-current", Boolean(on));
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (!match) {
    main.append(empty("Page not found", "That page doesn't exist.", h("a", { class: "btn", href: "#/" }, "Go to Analyse")));
    return;
  }
  try {
    cleanup = await match.r.view(main, ...match.m.slice(1));
  } catch (err) {
    main.append(empty("Something went wrong", err.message));
  }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
route();
