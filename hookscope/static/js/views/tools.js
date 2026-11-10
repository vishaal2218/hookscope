// S10 Quick tools: seven one-box text tools.

import { api } from "../api.js";
import { busy, copyButton, h, markdown, pageHead, toast } from "../ui.js";

export async function renderTools(main) {
  const tools = await api.get("/api/tools");
  let current = tools[0];
  const pick = h("div", { class: "tool-pick", role: "group", "aria-label": "Choose a tool" });
  const label = h("label", { class: "field", for: "tool-input" });
  const input = h("textarea", { id: "tool-input", rows: 5 });
  const run = h("button", { class: "btn btn-signal", type: "submit" }, "Run");
  const output = h("div", {});

  function select(tool) {
    current = tool;
    pick.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === tool.key)));
    label.textContent = tool.label;
    output.replaceChildren();
    input.focus();
  }
  tools.forEach((t) => pick.append(h("button", { type: "button", dataset: { key: t.key }, onclick: () => select(t) }, t.name)));

  async function submit(e) {
    e.preventDefault();
    if (!input.value.trim()) {
      toast("Type something first.", "error");
      return;
    }
    const done = busy(run, "Working…");
    try {
      const result = await api.post(`/api/tools/${current.key}`, { text: input.value });
      output.replaceChildren(h("section", { class: "card" }, h("div", { class: "spread" }, h("h2", {}, result.name), copyButton(result.output)), markdown(result.output)));
    } catch (err) {
      toast(err.message, "error");
    } finally {
      done();
    }
  }

  main.append(
    pageHead("Quick tools", "One box, one job", "Hooks, scripts, ideas, captions and bios, written for your voice profile."),
    pick,
    h("form", { class: "composer", onsubmit: submit }, label, input, h("div", { class: "row" }, run)),
    h("div", { class: "recent" }, output));
  select(current);
}
