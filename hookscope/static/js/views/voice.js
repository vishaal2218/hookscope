// S06 Your voice: the creator profile every report and script is written for.

import { api } from "../api.js";
import { busy, h, pageHead, toast } from "../ui.js";

const listToText = (list) => (list || []).join(", ");
const textToList = (text) => text.split(",").map((s) => s.trim()).filter(Boolean);

export async function renderVoice(main) {
  let profile = await api.get("/api/profile");
  const fields = {
    niche: h("input", { type: "text", placeholder: "e.g. video editing tips for Indian creators" }),
    audience: h("input", { type: "text", placeholder: "e.g. beginner creators, 18-30, mostly on phones" }),
    pillars: h("input", { type: "text", placeholder: "comma separated, e.g. Premiere tricks, captions, storytelling" }),
    tone: h("input", { type: "text", placeholder: "e.g. friendly, quick, a bit of Hinglish humour" }),
    goals: h("textarea", { rows: 2, placeholder: "e.g. grow to 50K, get editing clients" }),
  };
  const factsBox = h("ul", { class: "facts" });
  const learned = h("div", { class: "small muted" });
  const newFact = h("input", { type: "text", placeholder: "Add a fact about how you talk or present" });

  function fill() {
    fields.niche.value = profile.niche || "";
    fields.audience.value = profile.audience || "";
    fields.pillars.value = listToText(profile.pillars);
    fields.tone.value = profile.tone || "";
    fields.goals.value = profile.goals || "";
    drawFacts();
    // Native replaceChildren prints null as the word "null", so drop empty parts first.
    learned.replaceChildren(...[
      profile.strongest_formats && profile.strongest_formats.length ? h("p", {}, h("strong", {}, "Strongest formats: "), listToText(profile.strongest_formats)) : null,
      profile.signature_phrases && profile.signature_phrases.length ? h("p", {}, h("strong", {}, "Phrases you repeat: "), profile.signature_phrases.map((p) => `“${p}”`).join(", ")) : null,
    ].filter(Boolean));
  }

  function drawFacts() {
    factsBox.replaceChildren(...(profile.voice_facts || []).map((fact, i) => {
      const input = h("input", { type: "text", value: fact.text });
      input.addEventListener("change", () => {
        profile = { ...profile, voice_facts: profile.voice_facts.map((f, j) => (j === i ? { ...f, text: input.value.trim() } : f)).filter((f) => f.text) };
      });
      const remove = h("button", { class: "btn btn-ghost btn-small", type: "button", "aria-label": "Remove fact", onclick: () => {
        profile = { ...profile, voice_facts: profile.voice_facts.filter((_, j) => j !== i) };
        drawFacts();
      } }, "Remove");
      return h("li", {}, input, fact.source === "learned" ? h("span", { class: "badge" }, "learned") : null, remove);
    }));
    if (!profile.voice_facts || !profile.voice_facts.length) factsBox.append(h("li", { class: "muted small" }, "No facts yet. Add your own, or learn them from your videos."));
  }

  function collect() {
    return { ...profile, niche: fields.niche.value.trim(), audience: fields.audience.value.trim(), pillars: textToList(fields.pillars.value),
      tone: fields.tone.value.trim(), goals: fields.goals.value.trim() };
  }

  const save = h("button", { class: "btn btn-signal", type: "submit" }, "Save");
  async function onSave(e) {
    e.preventDefault();
    const done = busy(save, "Saving…");
    try {
      profile = await api.put("/api/profile", collect());
      fill();
      toast("Saved. New reports and scripts will use this.");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      done();
    }
  }

  const add = h("button", { class: "btn btn-ghost btn-small", type: "button", onclick: () => {
    const text = newFact.value.trim();
    if (!text) return;
    profile = { ...profile, voice_facts: [...(profile.voice_facts || []), { text, source: "you" }] };
    newFact.value = "";
    drawFacts();
  } }, "Add");

  const learn = h("button", { class: "btn", type: "button" }, "Learn from my videos");
  learn.addEventListener("click", async () => {
    const done = busy(learn, "Listening to your videos…");
    try {
      await api.put("/api/profile", collect());
      profile = await api.post("/api/profile/learn");
      fill();
      toast("Updated from your videos. Check the new facts and remove anything that's off.");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      done();
    }
  });

  const label = (text, el, hint) => [h("label", { class: "field" }, text), el, hint ? h("p", { class: "hint" }, hint) : null];
  main.append(
    pageHead("Your voice", "Who you are on camera", "Every breakdown's ideas, every script and every answer is written for this person. Fill in what you know; Hookscope can learn the rest from videos you mark as yours."),
    h("form", { class: "two", onsubmit: onSave },
      h("div", { class: "card" }, h("h2", {}, "Profile"),
        label("Niche", fields.niche), label("Audience", fields.audience), label("Content pillars", fields.pillars, "The 3-5 themes you keep coming back to."),
        label("Tone", fields.tone), label("Goals", fields.goals), h("div", { class: "row" }, save)),
      h("div", { class: "card" }, h("div", { class: "spread" }, h("h2", {}, "How you talk"), learn),
        h("p", { class: "hint" }, "Analyse a few of your own videos or posts with \"This is mine\" ticked, then press Learn. Edit any fact; changes save with the Save button."),
        factsBox, h("div", { class: "row" }, newFact, add), learned)));
  fill();
}
