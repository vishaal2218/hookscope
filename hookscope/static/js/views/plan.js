// S11 Weekly plan: patterns across chosen analyses, a do-next checklist and a 7-day calendar.

import { api } from "../api.js";
import { busy, empty, fmtDate, h, pageHead, platformName, toast } from "../ui.js";

const DEFAULT_PICK = 10;

export async function renderPlan(main) {
  const [analyses, plans] = await Promise.all([api.get("/api/analyses"), api.get("/api/plans")]);
  const done = analyses.filter((a) => a.status === "done");
  const out = h("div", { class: "recent" });

  if (!done.length) {
    main.append(pageHead("Weekly plan", "Plan your week", null),
      empty("Nothing to plan from yet", "Analyse a few videos first: competitors you admire and your own posts.", h("a", { class: "btn", href: "#/" }, "Analyse a video")));
    return;
  }

  const boxes = done.map((a, i) => ({ a, box: h("input", { type: "checkbox", checked: i < DEFAULT_PICK }) }));
  const go = h("button", { class: "btn btn-signal", type: "button" }, "Make my plan");
  go.addEventListener("click", async () => {
    const ids = boxes.filter((b) => b.box.checked).map((b) => b.a.id);
    if (!ids.length) {
      toast("Tick at least one video.", "error");
      return;
    }
    const finish = busy(go, "Planning… about a minute");
    try {
      showPlan(await api.post("/api/plans", { analysis_ids: ids }), done);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      finish();
    }
  });

  const history = plans.length > 1 ? h("select", { "aria-label": "Past plans" }, plans.map((p) => h("option", { value: p.id }, `Plan from ${fmtDate(p.created_at)}`))) : null;
  if (history) history.addEventListener("change", () => showPlan(plans.find((p) => p.id === history.value), done));

  function showPlan(plan, list) {
    out.replaceChildren(planView(plan, list));
  }

  main.append(
    pageHead("Weekly plan", "What to post this week, and why", "Pick the videos to learn from. Hookscope finds what repeats in the ones that worked, then plans the next seven days."),
    h("div", { class: "two" },
      h("section", { class: "card" }, h("div", { class: "spread" }, h("h2", {}, `Learn from (${done.length})`), go),
        h("div", { class: "pick-list" }, boxes.map(({ a, box }) => h("label", {}, box,
          h("span", {}, a.title || "Untitled", h("span", { class: "muted small" }, ` · ${platformName(a.platform)}${a.is_mine ? " · mine" : ""}`)))))),
      h("section", { class: "card" }, h("h2", {}, "How it works"),
        h("p", {}, "Mix your own videos and posts (tick \"This is mine\" on their reports) with competitors you admire. More videos means sharper patterns; three or more works best."),
        history ? h("div", { class: "stack" }, h("label", { class: "field" }, "Past plans"), history) : null)),
    out);
  if (plans.length) showPlan(plans[0], done);
}

function planView(plan, analyses) {
  const d = plan.data || {};
  let doneSet = new Set(plan.done || []);
  const titleOf = (id) => (analyses.find((a) => a.id === id) || {}).title;
  const todo = h("ul", { class: "todo" }, (d.do_next || []).map((item, i) => {
    const box = h("input", { type: "checkbox", checked: doneSet.has(i) });
    box.addEventListener("change", async () => {
      doneSet = new Set(box.checked ? [...doneSet, i] : [...doneSet].filter((x) => x !== i));
      try {
        await api.patch(`/api/plans/${plan.id}`, { done: [...doneSet] });
      } catch (err) {
        toast(err.message, "error");
      }
    });
    return h("li", {}, h("label", { class: "check" }, box, h("span", {}, item)));
  }));
  const days = h("div", { class: "days" }, (d.days || []).map((day) => {
    if (!day.title) return h("div", { class: "day rest" }, h("p", { class: "kicker" }, `${day.day} ${day.date || ""}`), h("p", {}, "Rest day"));
    const btn = h("button", { class: "btn btn-small" }, "Generate script");
    btn.addEventListener("click", async () => {
      const finish = busy(btn, "Writing…");
      try {
        const idea = { title: day.title, hook: day.hook, format: day.format || "", angle: `${day.format || ""}. ${day.why || ""}` };
        const s = await api.post("/api/scripts", { idea, analysis_id: day.inspired_by || null });
        location.hash = `#/script/${s.id}`;
      } catch (err) {
        toast(err.message, "error");
        finish();
      }
    });
    return h("div", { class: "day" }, h("p", { class: "kicker" }, `${day.day} ${day.date || ""}`), h("h3", {}, day.title),
      day.hook ? h("p", { class: "small" }, `“${day.hook}”`) : null, h("p", { class: "small muted" }, [day.format, day.why].filter(Boolean).join(". ")),
      day.inspired_by && titleOf(day.inspired_by) ? h("a", { class: "small", href: `#/report/${day.inspired_by}` }, `From: ${titleOf(day.inspired_by)}`) : null, btn);
  }));
  return h("div", { class: "stack" },
    h("p", { class: "kicker" }, `Plan from ${fmtDate(plan.created_at)}`),
    d.headline ? h("h2", {}, d.headline) : null,
    h("div", { class: "two" },
      h("section", { class: "card" }, h("h2", {}, "What keeps working"),
        h("ul", { class: "items" }, (d.findings || []).map((f) => h("li", {}, h("span"), h("div", {}, h("div", { class: "items-title" }, f.finding), h("p", {}, f.evidence)))))),
      h("section", { class: "card" }, h("h2", {}, "Fix next"),
        h("ul", { class: "items" }, (d.improvement_areas || []).map((f) => h("li", {}, h("span"), h("div", {}, h("div", { class: "items-title" }, f.area), h("p", {}, f.detail))))),
        h("h3", {}, "Do this week"), todo)),
    h("h2", {}, "Your next 7 days"), days);
}
