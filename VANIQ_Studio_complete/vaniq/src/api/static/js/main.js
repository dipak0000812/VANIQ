// VANIQ Studio shell: router, toolbar, navigation, agent drawer, command palette.
import { api, guard, h, state, toast, reviewer } from "./legacy.js";
import { app, closeDialog, dialogOpen, icon, openDialog, skeleton } from "./ui.js";
import { renderHome } from "./home.js";
import { renderStudio } from "./studio.js";
import { renderSkills } from "./skills.js";
import { renderKnowledge } from "./knowledge.js";
import { renderWorkflows } from "./workflows.js";
import { renderDatasets, renderEvaluationView, renderLexiconView, renderAboutView } from "./data.js";
import { mountAgentDrawer, askAgent } from "./agent.js";

const NAV = [
  ["home", "Home", "home"], ["studio", "Studio", "studio"], ["skills", "Skills", "skills"], ["knowledge", "Knowledge", "knowledge"],
  ["workflows", "Workflows", "workflow"], ["lexicon", "Lexicon", "lexicon"], ["datasets", "Datasets", "dataset"],
  ["evaluation", "Evaluation", "eval"], ["about", "About & limits", "about"],
];
const VIEWS = { home: renderHome, studio: renderStudio, skills: renderSkills, knowledge: renderKnowledge, workflows: renderWorkflows,
  lexicon: renderLexiconView, datasets: renderDatasets, evaluation: renderEvaluationView, about: renderAboutView };
const TITLES = Object.fromEntries(NAV.map(([k, t]) => [k, t]));
let drawer = null, routeToken = 0, rendered = null;

function buildNav() {
  const nav = document.getElementById("nav");
  nav.replaceChildren(
    ...NAV.slice(0, 5).map(navLink), h("div", { class: "grp" }, "Data"), ...NAV.slice(5, 8).map(navLink), h("div", { class: "grp" }, "Project"), navLink(NAV[8]),
    h("div", { class: "nav-foot" }, h("div", { class: "who" }, h("label", { for: "reviewer" }, "Reviewer name"),
      h("input", { id: "reviewer", type: "text", maxlength: "60", placeholder: "Your name", autocomplete: "name" }),
      h("div", { class: "hint", style: "margin-top:4px" }, "Recorded with every decision. No login."))));
  const r = document.getElementById("reviewer");
  r.value = localStorage.getItem("vaniq.reviewer") || "";
  r.addEventListener("change", e => localStorage.setItem("vaniq.reviewer", e.target.value.trim()));
}
function navLink([key, label, ic]) {
  return h("a", { href: "#/" + key, "data-route": key, title: label }, icon(ic), h("span", {}, label));
}

export async function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "home").split("/");
  const name = VIEWS[parts[0]] ? parts[0] : "home";
  app.view = name;
  document.querySelectorAll(".nav a").forEach(a => { const on = a.dataset.route === name; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
  document.getElementById("crumb-view").textContent = TITLES[name];
  document.title = `${TITLES[name]} · VANIQ Studio`;
  const main = document.getElementById("main");
  const token = ++routeToken;
  document.body.dataset.route = name; document.body.dataset.ready = "0";      // markers for automation and tests
  main.replaceChildren(skeleton());
  try {
    const node = document.createElement("div");
    node.className = "view"; node.style.height = "100%";
    await VIEWS[name](node, parts.slice(1));
    if (token !== routeToken) return;
    main.replaceChildren(node);
    rendered = name;
  } catch (e) {
    if (token === routeToken) main.replaceChildren(h("div", { class: "page" }, h("div", { class: "notice bad" }, e.message), h("button", { class: "btn", onclick: route }, "Retry")));
  }
  if (token === routeToken) document.body.dataset.ready = "1";
  refreshExport();
  window.dispatchEvent(new CustomEvent("vaniq:context"));
}

async function refreshExport() {
  const b = document.getElementById("tb-export");
  try {
    const [pub, int] = await Promise.all([api("/api/datasets/eligibility?visibility=public"), api("/api/datasets/eligibility?visibility=internal")]);
    const n = Math.max(pub.eligible_count, int.eligible_count);
    b.disabled = n === 0;
    b.title = n === 0 ? "No clips are eligible for export yet. Check consent, permitted usage and human verification (Datasets)."
      : `${pub.eligible_count} eligible for a public export, ${int.eligible_count} for an internal export`;
    b.onclick = () => { location.hash = "#/datasets"; };
  } catch (_) { b.disabled = true; b.title = "Eligibility unavailable"; }
}

function wireToolbar() {
  const appEl = document.getElementById("app"), tog = document.getElementById("nav-toggle");
  tog.append(icon("menu"));
  const setNav = c => { appEl.classList.toggle("nav-c", c); tog.setAttribute("aria-expanded", String(!c)); localStorage.setItem("vaniq.nav", c ? "c" : "o"); };
  setNav(localStorage.getItem("vaniq.nav") === "c" || window.innerWidth < 1100);
  tog.addEventListener("click", () => setNav(!appEl.classList.contains("nav-c")));
  document.getElementById("open-palette").addEventListener("click", openPalette);
  const ag = document.getElementById("tb-agent");
  ag.addEventListener("click", () => drawer.toggle());
  window.addEventListener("vaniq:drawer", e => { ag.setAttribute("aria-pressed", String(e.detail)); });
  const ss = document.getElementById("save-state");
  window.addEventListener("vaniq:save", e => {
    const t = ss.querySelector("span"); ss.className = "save-state " + e.detail;
    t.textContent = e.detail === "saving" ? "Saving…" : e.detail === "saved" ? "Saved " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Save failed";
  });
  window.addEventListener("vaniq:refresh", () => route());
  window.addEventListener("hashchange", route);
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); dialogOpen() ? closeDialog() : openPalette(); }
  });
}

function openPalette() {
  const input = h("input", { type: "text", placeholder: "Go to a view, run a skill, or ask VANIQ…", "aria-label": "Command bar", autofocus: true, role: "combobox", "aria-expanded": "true", "aria-controls": "pal-list" });
  const list = h("ul", { id: "pal-list", role: "listbox" });
  let items = [], sel = 0, tools = [];
  const base = () => [...NAV.map(([k, t, ic]) => ({ label: "Go to " + t, hint: "view", ic, run: () => { location.hash = "#/" + k; } })),
    ...tools.filter(t => !t.requires_approval).map(t => ({ label: "Run skill: " + t.title, hint: "agent", ic: "skills", run: () => askAgent(commandFor(t), true) }))];
  const commandFor = t => ({ list_work: "what needs doing", validate_audio: "validate audio", detect_transcript_mismatch: "check transcript mismatch",
    reference_workflow_status: "who needs a human reference", check_dataset_eligibility: "check dataset eligibility", list_knowledge: "show knowledge",
    run_evaluation: "run evaluation", propose_corrections: "propose corrections" }[t.name] || t.title);
  function paint() {
    const q = input.value.trim().toLowerCase();
    items = base().filter(i => !q || i.label.toLowerCase().includes(q)).slice(0, 9);
    if (q) items.push({ label: `Ask VANIQ: “${input.value.trim()}”`, hint: "agent", ic: "send", run: () => askAgent(input.value.trim(), true) });
    sel = Math.min(sel, items.length - 1);
    list.replaceChildren(...items.map((it, i) => h("li", { role: "option", "aria-selected": String(i === sel), onclick: () => choose(i) }, icon(it.ic), it.label, h("small", {}, it.hint))));
  }
  const choose = i => { const it = items[i]; closeDialog(); if (it) it.run(); };
  input.addEventListener("input", () => { sel = 0; paint(); });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = (sel + 1) % items.length; paint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = (sel - 1 + items.length) % items.length; paint(); }
    else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
  });
  openDialog("Command bar", h("div", {}, input, list, h("div", { class: "hint", style: "padding:8px 14px;border-top:1px solid var(--line)" },
    state.mode === "demo" || true ? "Command mode: VANIQ understands a fixed set of commands. Consequential actions always ask for approval." : "")), { palette: true });
  api("/api/agent/tools").then(t => { tools = t; paint(); }).catch(() => paint());
  paint();
}

async function init() {
  buildNav(); wireToolbar();
  drawer = mountAgentDrawer(document.getElementById("drawer"));
  try {
    state.about = await api("/api/about");
    state.mode = state.about.mode; state.sttConfigured = state.about.stt.configured;
    if (state.mode === "demo") {
      const b = document.getElementById("mode-banner"); b.hidden = false; document.body.classList.add("has-banner");
      b.textContent = "Demo mode: audio, transcripts and lexicon entries are synthetic and say nothing about real STT or Ahirani accuracy.";
    }
  } catch (e) { toast(e.message, true); }
  route();
}
init();
