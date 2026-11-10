// S09 Ask: a chat grounded in the library and the creator profile.

import { api } from "../api.js";
import { busy, h, markdown, pageHead, toast } from "../ui.js";

const SUGGESTIONS = [
  "Which of my analysed videos had the strongest hooks, and why?",
  "What do the best performers in my library have in common?",
  "Give me 3 hooks for a video about my main pillar.",
  "Plan 3 videos I can film this weekend.",
];

export async function renderChat(main) {
  const thread = h("div", { class: "chat", "aria-live": "polite" });
  const input = h("textarea", { rows: 2, placeholder: "Ask about your library, hooks, ideas…", "aria-label": "Your question" });
  const send = h("button", { class: "btn btn-signal", type: "submit" }, "Send");
  const clearBtn = h("button", { class: "btn btn-ghost btn-small", type: "button" }, "Clear chat");

  const bubble = (m) => h("div", { class: `bubble ${m.role}` }, m.role === "assistant" ? markdown(m.text) : m.text);

  async function ask(text) {
    const question = text.trim();
    if (!question) return;
    input.value = "";
    thread.append(bubble({ role: "user", text: question }));
    const thinking = h("div", { class: "bubble assistant muted" }, "Thinking… (10-40 s)");
    thread.append(thinking);
    thinking.scrollIntoView({ block: "end", behavior: "smooth" });
    const done = busy(send, "…");
    try {
      const reply = await api.post("/api/chat", { text: question });
      thinking.replaceWith(bubble(reply));
    } catch (err) {
      thinking.replaceWith(h("div", { class: "bubble assistant" }, `Couldn't answer: ${err.message}`));
    } finally {
      done();
      input.focus();
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input.value);
    }
  });
  clearBtn.addEventListener("click", async () => {
    if (!confirm("Clear the whole conversation?")) return;
    try {
      await api.del("/api/chat");
      thread.replaceChildren();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  main.append(
    h("div", { class: "spread" }, pageHead("Ask", "Ask about your content", "Answers come from your library and your voice profile, not generic advice."), clearBtn),
    h("div", { class: "suggest" }, SUGGESTIONS.map((s) => h("button", { type: "button", onclick: () => ask(s) }, s))),
    h("div", { class: "chat recent" }, thread,
      h("form", { class: "chat-input", onsubmit: (e) => (e.preventDefault(), ask(input.value)) }, input, send)));

  try {
    (await api.get("/api/chat")).forEach((m) => thread.append(bubble(m)));
  } catch (err) {
    toast(err.message, "error");
  }
  input.focus();
}
