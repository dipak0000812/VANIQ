// Skills: reusable VANIQ capabilities backed by real services (Lindy skills pattern).
import { api, chip, guard, h, reviewer } from "./legacy.js";
import { app } from "./ui.js";
import { runCard } from "./agent.js";

const IMPACT = { read: ["Reads only", ""], record: ["Writes records", "info"], consequential: ["Needs approval", "agent"] };

export async function renderSkills(root) {
  const tools = await api("/api/agent/tools");
  const groups = {};
  tools.forEach(t => (groups[t.skill] = groups[t.skill] || []).push(t));
  const page = h("div", { class: "page" }, h("h1", {}, "Skills"),
    h("p", { class: "lede" }, "Reusable capabilities the VANIQ agent can use. Each one runs a real backend operation with validated arguments. When you ask in plain language, the agent picks the matching skill and shows it in its plan. Skills never write human references, decide corrections, or approve knowledge."));
  for (const [grp, list] of Object.entries(groups)) {
    page.append(h("h2", {}, grp), h("div", { class: "skills-grid" }, list.map(skillCard)));
  }
  root.replaceChildren(page);
}

function skillCard(t) {
  const inputs = {};
  const form = h("div", { class: "args" });
  for (const [name, spec] of Object.entries(t.args_schema)) {
    const req = t.required.includes(name);
    let ctl;
    if (spec.enum) ctl = h("select", {}, spec.enum.map(v => h("option", { value: v, selected: v === spec.default }, v)));
    else if (spec.type === "boolean") ctl = h("input", { type: "checkbox", checked: !!spec.default });
    else if (spec.type === "integer") ctl = h("input", { type: "text", inputmode: "numeric", value: "" });
    else {
      const pre = name === "clip_id" ? app.clipId : name === "source_id" ? app.sourceId : name === "language_code" ? "mr-IN" : "";
      ctl = h("input", { type: "text", value: spec.default && typeof spec.default === "string" ? spec.default : (pre || ""), placeholder: spec.description || (req ? "required" : "optional") });
    }
    ctl.setAttribute("aria-label", name); inputs[name] = [ctl, spec];
    form.append(h("div", {}, h("label", {}, name.replaceAll("_", " "), req ? " *" : ""), ctl));
  }
  const out = h("div", { class: "out" });
  async function watch(id) {
    const run = await api("/api/agent/runs/" + id);
    out.replaceChildren(runCard(run, () => watch(id)));
    if (run.status === "running" || run.status === "ready") setTimeout(() => out.isConnected && watch(id), 700);
  }
  const run = h("button", { class: "btn primary small", onclick: () => guard(async () => {
    const args = {};
    for (const [name, [ctl, spec]] of Object.entries(inputs)) {
      if (spec.type === "boolean") args[name] = ctl.checked;
      else if (ctl.value !== "") args[name] = spec.type === "integer" ? Number(ctl.value) : ctl.value;
    }
    const r = await api("/api/agent/plan", { method: "POST", json: { steps: [{ tool: t.name, args }], reviewer: reviewer(), context: { view: "skills" } } });
    await watch(r.id);
  }) }, t.requires_approval ? "Plan this skill" : "Run");
  const [il, ik] = IMPACT[t.impact];
  return h("div", { class: "skill", "data-skill": t.name }, h("div", {}, h("h3", {}, t.title), h("div", { class: "grp" }, t.skill)),
    h("div", { class: "hint" }, t.description), h("div", {}, chip(il, ik)), form.children.length ? form : null, h("div", {}, run), out);
}
