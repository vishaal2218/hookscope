// S07/S08 Scripts: saved scripts, a blank-idea generator, and an editable script page.

import { api } from "../api.js";
import { busy, copyButton, empty, fmtDate, h, pageHead, toast } from "../ui.js";

export async function renderScripts(main) {
  const title = h("input", { type: "text", placeholder: "Idea, e.g. 3 caption mistakes that make reels look cheap" });
  const angle = h("textarea", { rows: 2, placeholder: "Optional: angle, format or anything to include" });
  const format = h("select", { "aria-label": "Format" }, h("option", { value: "reel" }, "Reel / video script"), h("option", { value: "carousel" }, "Carousel plan"));
  const go = h("button", { class: "btn btn-signal", type: "submit" }, "Write it");
  async function submit(e) {
    e.preventDefault();
    if (!title.value.trim()) {
      toast("Write the idea first.", "error");
      return;
    }
    const done = busy(go, "Writing… about a minute");
    try {
      const s = await api.post("/api/scripts", { idea: { title: title.value.trim(), angle: angle.value.trim(), format: format.value } });
      location.hash = `#/script/${s.id}`;
    } catch (err) {
      toast(err.message, "error");
      done();
    }
  }
  const list = h("div", {});
  main.append(
    pageHead("Scripts", "From idea to ready-to-film", "Generate from any idea here, or from an idea inside a breakdown or your weekly plan."),
    h("form", { class: "composer", onsubmit: submit }, h("label", { class: "field" }, "Your idea"), title, h("label", { class: "field" }, "Details"), angle,
      h("label", { class: "field" }, "Format"), format, h("div", { class: "row" }, go)),
    h("section", { class: "recent" }, h("h2", {}, "Saved scripts"), list));
  const rows = await api.get("/api/scripts");
  if (!rows.length) list.append(empty("No scripts yet", "Your generated scripts are saved here."));
  rows.forEach((s) => list.append(h("a", { class: "list-row", href: `#/script/${s.id}` },
    h("div", { class: "grow" }, h("div", { class: "list-title" }, (s.script && s.script.title) || s.idea.title || "Script"),
      h("div", { class: "small muted" }, [s.script && s.script.format, fmtDate(s.created_at), s.edited_text ? "edited" : null].filter(Boolean).join(" · "))))));
}

const isCarousel = (sc) => sc.type === "carousel";
const tags = (sc) => (sc.hashtags || []).map((t) => `#${String(t).replace(/^#/, "")}`).join(" ");

export function scriptToText(sc) {
  if (isCarousel(sc)) {
    const slides = (sc.slides || []).map((s) => `SLIDE ${s.slide}\nHEADLINE: ${s.headline || ""}${s.body ? `\nTEXT: ${s.body}` : ""}${s.visual ? `\nVISUAL: ${s.visual}` : ""}`).join("\n\n");
    return [sc.title, `${sc.format || "Carousel"} · ${sc.slide_count || (sc.slides || []).length} slides`, "",
      `COVER: ${sc.chosen_hook || ""}`, "", slides, "", sc.cta ? `CTA: ${sc.cta}` : "", "",
      sc.caption ? `CAPTION:\n${sc.caption}\n${tags(sc)}` : "", sc.design_notes ? `\nDESIGN: ${sc.design_notes}` : "",
    ].join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  const beats = (sc.beats || []).map((b) => `[${b.time}]\nSAY: ${b.say || ""}\nSHOW: ${b.show || ""}${b.on_screen_text ? `\nTEXT: ${b.on_screen_text}` : ""}`).join("\n\n");
  return [
    sc.title, `${sc.format || ""}${sc.length_seconds ? ` · about ${sc.length_seconds} s` : ""}`, "",
    `HOOK: ${sc.chosen_hook || ""}`, "", beats, "",
    sc.cta ? `CTA: ${sc.cta}` : "", "",
    sc.shot_list && sc.shot_list.length ? `SHOTS:\n${sc.shot_list.map((s) => `- ${s}`).join("\n")}` : "", "",
    sc.caption ? `CAPTION:\n${sc.caption}\n${(sc.hashtags || []).map((t) => `#${String(t).replace(/^#/, "")}`).join(" ")}` : "",
  ].join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export async function renderScript(main, id) {
  let row = await api.get(`/api/scripts/${id}`);
  const sc = row.script || {};
  const body = h("div", {});

  function view() {
    if (row.edited_text) {
      body.replaceChildren(h("section", { class: "card" }, h("div", { class: "spread" }, h("h2", {}, "Your edited script"), h("div", { class: "row" }, copyButton(row.edited_text), editBtn(), revertBtn())),
        h("div", { class: "template" }, row.edited_text)));
      return;
    }
    const hookCard = h("section", { class: "card hook-card" },
      h("div", { class: "card-head" }, h("h2", {}, isCarousel(sc) ? "Cover" : "Hook"),
        h("div", { class: "row" }, copyButton(() => scriptToText(sc), isCarousel(sc) ? "Copy plan" : "Copy script"), editBtn())),
      h("p", { class: "hook-quote" }, sc.chosen_hook || ""),
      h("ul", { class: "openers" }, (sc.hook_options || []).map((o) => h("li", { class: o.line === sc.chosen_hook ? "chosen" : "" },
        h("span", {}, h("span", { class: "badge" }, o.style), " ", o.line), copyButton(o.line)))));
    if (isCarousel(sc)) {
      body.replaceChildren(hookCard,
        h("section", { class: "card" }, h("h2", {}, "Slides"),
          h("table", { class: "beats-table" }, h("thead", {}, h("tr", {}, ["Slide", "Headline", "Text", "Visual"].map((t) => h("th", {}, t)))),
            h("tbody", {}, (sc.slides || []).map((s) => h("tr", {}, h("td", {}, String(s.slide)), h("td", {}, s.headline || ""), h("td", {}, s.body || ""), h("td", {}, s.visual || "")))))),
        h("div", { class: "two" },
          h("section", { class: "card" }, h("h2", {}, "Design notes"), h("p", {}, sc.design_notes || "–"), sc.cta ? h("p", {}, h("strong", {}, "Call to action: "), sc.cta) : null),
          h("section", { class: "card" }, h("h2", {}, "Caption"), h("p", { class: "template" }, `${sc.caption || ""}\n\n${tags(sc)}`))));
      return;
    }
    body.replaceChildren(
      hookCard,
      h("section", { class: "card" }, h("h2", {}, "Beats"),
        h("table", { class: "beats-table" }, h("thead", {}, h("tr", {}, ["Time", "Say", "Show", "On-screen text"].map((t) => h("th", {}, t)))),
          h("tbody", {}, (sc.beats || []).map((b) => h("tr", {}, h("td", {}, b.time), h("td", {}, b.say), h("td", {}, b.show), h("td", {}, b.on_screen_text || "")))))),
      h("div", { class: "two" },
        h("section", { class: "card" }, h("h2", {}, "Shot list"), h("ul", {}, (sc.shot_list || []).map((s) => h("li", {}, s))),
          sc.filming_notes ? [h("h3", {}, "Filming notes"), h("p", {}, sc.filming_notes)] : null),
        h("section", { class: "card" }, h("h2", {}, "Caption"), h("p", { class: "template" }, `${sc.caption || ""}\n\n${(sc.hashtags || []).map((t) => `#${String(t).replace(/^#/, "")}`).join(" ")}`),
          sc.cta ? h("p", {}, h("strong", {}, "Call to action: "), sc.cta) : null)));
  }

  function editBtn() {
    return h("button", { class: "btn btn-ghost btn-small", onclick: () => {
      const area = h("textarea", { class: "editor" });
      area.value = row.edited_text || scriptToText(sc);
      const save = h("button", { class: "btn btn-signal" }, "Save");
      save.addEventListener("click", async () => {
        const done = busy(save, "Saving…");
        try {
          row = await api.put(`/api/scripts/${id}`, { edited_text: area.value });
          view();
          toast("Saved.");
        } catch (err) {
          toast(err.message, "error");
          done();
        }
      });
      body.replaceChildren(h("section", { class: "card stack" }, h("h2", {}, "Edit"), area, h("div", { class: "row" }, save, h("button", { class: "btn btn-ghost", onclick: view }, "Cancel"))));
      area.focus();
    } }, "Edit");
  }

  function revertBtn() {
    return h("button", { class: "btn btn-ghost btn-small", onclick: async () => {
      row = await api.put(`/api/scripts/${id}`, { edited_text: null });
      view();
    } }, "Back to original");
  }

  const del = h("button", { class: "btn btn-danger btn-small", onclick: async () => {
    if (!confirm("Delete this script?")) return;
    await api.del(`/api/scripts/${id}`);
    location.hash = "#/scripts";
  } }, "Delete");

  main.append(h("header", { class: "report-head" },
    h("div", {}, h("p", { class: "kicker" }, isCarousel(sc) ? `Carousel plan · ${(sc.slides || []).length} slides` : "Script",
      sc.length_seconds ? ` · about ${sc.length_seconds} s` : "", sc.format ? ` · ${sc.format}` : ""),
      h("h1", {}, sc.title || row.idea.title || "Script"),
      row.analysis_id ? h("p", { class: "small" }, h("a", { href: `#/report/${row.analysis_id}` }, "From this breakdown")) : null),
    h("div", { class: "row" }, del)), body);
  view();
}
