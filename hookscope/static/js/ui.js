// Small DOM helpers. All text goes in through textContent; markdown is escaped before formatting.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key in el && typeof value !== "string") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export function toast(message, kind = "info") {
  const box = document.getElementById("toasts");
  const item = h("div", { class: `toast toast-${kind}`, role: kind === "error" ? "alert" : "status" }, message);
  box.append(item);
  setTimeout(() => item.classList.add("toast-out"), 4200);
  setTimeout(() => item.remove(), 4700);
}

export function fmtTime(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "";
  const s = Math.max(0, Number(seconds));
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
export function fmtNum(n) {
  return n === null || n === undefined ? "–" : compact.format(n);
}

export function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
}

export function elapsed(start, end) {
  if (!start) return "";
  const secs = Math.max(0, (end || Date.now() / 1000) - start);
  return secs < 60 ? `${secs.toFixed(0)}s` : `${Math.floor(secs / 60)}m ${String(Math.floor(secs % 60)).padStart(2, "0")}s`;
}

const PLATFORMS = {
  instagram: "Instagram", youtube: "YouTube", tiktok: "TikTok", x: "X", facebook: "Facebook",
  threads: "Threads", linkedin: "LinkedIn", vimeo: "Vimeo", reddit: "Reddit", snapchat: "Snapchat",
  upload: "Your file", web: "Web",
};
export const platformName = (p) => PLATFORMS[p] || "Web";

export function copyButton(getText, label = "Copy") {
  const btn = h("button", { class: "btn btn-ghost btn-small", type: "button" }, label);
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(typeof getText === "function" ? getText() : getText);
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = label), 1400);
    } catch {
      toast("Couldn't copy. Select the text and press Cmd+C.", "error");
    }
  });
  return btn;
}

export function busy(button, text) {
  const original = button.textContent;
  button.disabled = true;
  button.classList.add("is-busy");
  button.textContent = text;
  return () => {
    button.disabled = false;
    button.classList.remove("is-busy");
    button.textContent = original;
  };
}

export function empty(title, body, action) {
  return h("div", { class: "empty" }, h("h3", {}, title), body ? h("p", {}, body) : null, action || null);
}

export function pageHead(kicker, title, sub) {
  return h("header", { class: "page-head" },
    kicker ? h("p", { class: "kicker" }, kicker) : null,
    h("h1", {}, title),
    sub ? h("p", { class: "lede" }, sub) : null);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}

// Minimal, safe Markdown: headings, lists, bold, italics, code, paragraphs.
export function markdown(text) {
  const out = [];
  let list = null;
  const closeList = () => {
    if (list) out.push(`</${list}>`);
    list = null;
  };
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trimEnd();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      if (list !== kind) {
        closeList();
        out.push(`<${kind}>`);
        list = kind;
      }
      out.push(`<li>${inline((bullet || numbered)[1])}</li>`);
    } else if (!line.trim()) {
      closeList();
    } else {
      closeList();
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  const box = h("div", { class: "md" });
  box.innerHTML = out.join("");
  return box;
}

export function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = h("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
