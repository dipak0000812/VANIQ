// VANIQ agent UI: plan cards, approval, live progress, results. Everything shown comes from stored backend runs.
import { api, chip, guard, h, requireReviewer, reviewer, toast, short } from "./legacy.js";
import { app, emptyState, icon, timeAgo } from "./ui.js";

const IMPACT = { read: ["Reads only", ""], record: ["Writes records", "info"], consequential: ["Needs approval", "agent"] };
const STATUS = { awaiting_approval: ["Waiting for approval", "agent"], ready: ["Starting", "info"], running: ["Running", "warn"], completed: ["Completed", "ok"],
  failed: ["Failed", "bad"], rejected: ["Rejected", "bad"], unsupported: ["Not supported", "bad"], needs_input: ["Needs more input", "warn"] };

export function currentContext() {
  return { view: app.view, clip_id: app.clipId || undefined, source_id: app.sourceId || undefined };
}

export async function askAgent(message, reveal = true) {
  const run = await guard(() => api("/api/agent/plan", { method: "POST", json: { message, context: currentContext(), reviewer: reviewer() } }));
  window.dispatchEvent(new Event("vaniq:agent-updated"));
  if (reveal && app.view !== "home") window.dispatchEvent(new CustomEvent("vaniq:open-drawer"));
  return run;
}

// ---------- result rendering (generic, driven by the real result object) ----------
function renderResult(result) {
  if (result === null || result === undefined) return null;
  const box = h("div", { class: "res" });
  const scalars = Object.entries(result).filter(([, v]) => v === null || ["string", "number", "boolean"].includes(typeof v) );
  const dl = h("dl", { class: "kv" });
  for (const [k, v] of scalars) {
    if (k === "download") { dl.append(h("dt", {}, "download"), h("dd", {}, h("a", { href: v }, "Download export"))); continue; }
    dl.append(h("dt", {}, k.replaceAll("_", " ")), h("dd", {}, String(v)));
  }
  if (scalars.length) box.append(dl);
  for (const [k, v] of Object.entries(result)) {
    if (Array.isArray(v) && v.length && typeof v[0] === "object") {
      const cols = Object.keys(v[0]).slice(0, 4);
      box.append(h("div", { class: "hint", style: "margin-top:6px" }, `${k.replaceAll("_", " ")} (${v.length})`),
        h("div", { class: "tablewrap" }, h("table", { class: "result-table" }, h("thead", {}, h("tr", {}, cols.map(c => h("th", {}, c)))),
          h("tbody", {}, v.slice(0, 8).map(r => h("tr", {}, cols.map(c => h("td", {}, fmt(r[c]))))))),
        v.length > 8 ? h("div", { class: "hint" }, `+ ${v.length - 8} more`) : null));
    } else if (Array.isArray(v) && v.length) {
      box.append(h("div", { class: "hint", style: "margin-top:6px" }, `${k.replaceAll("_", " ")} (${v.length})`), h("div", { class: "hint" }, v.slice(0, 10).map(x => short(String(x))).join(", ") + (v.length > 10 ? " …" : "")));
    } else if (v && typeof v === "object" && !Array.isArray(v)) {
      box.append(h("details", {}, h("summary", { class: "hint" }, k.replaceAll("_", " ")), h("pre", { class: "textbox", style: "font-size:11.5px;overflow:auto" }, JSON.stringify(v, null, 2))));
    }
  }
  return box;
}
const fmt = v => v === null || v === undefined ? "" : typeof v === "object" ? (Array.isArray(v) ? v.join("; ") : JSON.stringify(v)) : String(v);

export function runCard(run, reload) {
  const [stLabel, stKind] = STATUS[run.status] || [run.status, ""];
  const steps = run.steps || [];
  const consequential = steps.filter(s => s.requires_approval);
  const me = h("div", { class: "msg" }, h("div", { class: "avatar me" }, (run.actor || "Y")[0].toUpperCase()),
    h("div", { class: "bubble" }, h("div", { class: "who-line" }, run.actor, " · ", timeAgo(run.created_at)), h("div", { class: "text" }, run.message)));
  const planEl = steps.length ? h("div", { class: "plan", "aria-label": "Execution plan" },
    h("div", { class: "ph" }, icon("workflow"), `Plan · ${steps.length} step${steps.length > 1 ? "s" : ""}`, h("span", { style: "margin-left:auto" }, chip(stLabel, stKind))),
    steps.map(s => h("div", { class: "step", "data-step-status": s.status },
      h("span", { class: "dot " + s.status, title: s.status }, s.status === "done" ? "✓" : s.status === "failed" ? "!" : ""),
      h("div", {}, h("div", {}, h("b", {}, s.title), " ", chip(IMPACT[s.impact][0], IMPACT[s.impact][1])),
        h("div", { class: "args" }, JSON.stringify(s.args)),
        s.error ? h("div", { class: "notice bad", style: "margin:6px 0" }, `${s.error.message} (${s.error.code})`) : null),
      h("span", { class: "hint" }, s.status),
      s.result ? renderResult(s.result) : null)),
    run.status === "awaiting_approval" ? h("div", { class: "approval" },
      h("span", {}, h("b", {}, "Needs your approval. "), `${consequential.length} step(s) have outside impact (STT provider call or export). Nothing has run yet.`),
      h("span", { style: "margin-left:auto;display:flex;gap:8px" },
        h("button", { class: "btn ok small", onclick: () => guard(async () => { if (!requireReviewer()) return; await api(`/api/agent/runs/${run.id}/approve`, { method: "POST", json: { reviewer: reviewer() } }); reload(); }) }, "Approve and run"),
        h("button", { class: "btn danger small", onclick: () => guard(async () => { await api(`/api/agent/runs/${run.id}/reject`, { method: "POST", json: { reviewer: reviewer() } }); reload(); }) }, "Reject"))) : null,
    run.status === "failed" ? h("div", { class: "approval", style: "background:var(--bad-soft);border-color:#e3b9b1" },
      h("span", {}, h("b", { style: "color:var(--bad)" }, "Stopped. "), "Nothing after the failed step ran."),
      h("button", { class: "btn small", style: "margin-left:auto", onclick: () => guard(async () => { await api("/api/agent/plan", { method: "POST", json: { steps: steps.map(s => ({ tool: s.tool, args: s.args })), reviewer: reviewer(), context: currentContext() } }); reload(); }) }, "Retry as a new run")) : null) : null;
  const reply = h("div", { class: "msg" }, h("div", { class: "avatar agent" }, "V"),
    h("div", { class: "bubble" }, h("div", { class: "who-line" }, "VANIQ agent · command mode"),
      run.note ? h("div", { class: "text" }, run.note) : null,
      !steps.length ? h("div", { style: "margin-top:6px" }, chip(stLabel, stKind)) : null, planEl,
      run.approved_by ? h("div", { class: "hint", style: "margin-top:4px" }, `Approved by ${run.approved_by}`) : null));
  return h("div", { class: "thread", style: "margin:0", "data-run": run.id }, me, reply);
}

export function mountThread(container, { limit = 20 } = {}) {
  let timer = null, alive = true, loadedOnce = false;
  async function load() {
    clearTimeout(timer);
    // The container may not be attached yet on the first call (views attach after they resolve); only stop once it was shown and then removed.
    if (!alive || (loadedOnce && !container.isConnected)) return;
    loadedOnce = true;
    let runs;
    try { runs = (await api("/api/agent/runs?limit=" + limit)).reverse(); }
    catch (e) { container.replaceChildren(h("div", { class: "notice bad" }, e.message)); return; }
    const top = container.scrollTop;
    container.replaceChildren(...(runs.length ? runs.map(r => runCard(r, load)) : [emptyState("Nothing has run yet", "Ask VANIQ for a job, or open Skills to run one. Safe reads run immediately; anything with outside impact waits for your approval.")]));
    container.scrollTop = top;
    if (runs.some(r => r.status === "running" || r.status === "ready")) timer = setTimeout(load, 800);
  }
  const onUpd = () => load();
  window.addEventListener("vaniq:agent-updated", onUpd);
  load();
  return { reload: load, destroy() { alive = false; clearTimeout(timer); window.removeEventListener("vaniq:agent-updated", onUpd); } };
}

export function composer({ onSent } = {}) {
  const ta = h("textarea", { placeholder: "Hand VANIQ a job, e.g. “run baseline mr-IN on this clip” or “check dataset eligibility”", "aria-label": "Message to the VANIQ agent", rows: "2" });
  const ctxChip = h("span", { class: "ctx-chip", "aria-label": "Current context" });
  const send = h("button", { class: "btn primary small", "aria-label": "Send to agent" }, icon("send", 15), "Send");
  const paint = () => { ctxChip.textContent = app.clipId ? `Context: recording clip ${short(app.clipId)}` : app.view === "studio" ? "Context: Studio (no clip selected)" : `Context: ${app.view}`; };
  const submit = async () => { const m = ta.value.trim(); if (!m) return; ta.value = ""; send.disabled = true; await askAgent(m, false); send.disabled = false; if (onSent) onSent(); };
  send.addEventListener("click", submit);
  ta.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
  window.addEventListener("vaniq:context", paint); paint();
  return { el: h("div", { class: "composer" }, ta, h("div", { class: "bar" }, ctxChip, h("span", { style: "margin-left:auto" }, send))), ta };
}

export const modeNote = () => h("div", { class: "mode-note", role: "note" }, icon("about"),
  h("div", {}, h("b", {}, "Command mode. "), "No language model is configured, so VANIQ understands a fixed set of commands and says so when it can't help. Nothing is simulated: every result below comes from a real backend operation."));

export function mountAgentDrawer(el) {
  let thread = null;
  const dh = h("div", { class: "dh" }, h("span", { class: "avatar agent" }, "V"), "VANIQ agent",
    h("button", { class: "btn ghost small", style: "margin-left:auto", "aria-label": "Close agent", onclick: () => api_close() }, icon("close")));
  const body = h("div", { class: "db" });
  const comp = composer({ onSent: () => { body.scrollTop = body.scrollHeight; } });
  el.replaceChildren(dh, body, h("div", { class: "df" }, comp.el));
  const open = () => { el.classList.add("open"); el.setAttribute("aria-hidden", "false"); window.dispatchEvent(new CustomEvent("vaniq:drawer", { detail: true }));
    if (!thread) { body.append(modeNote()); const t = h("div", { style: "margin-top:12px" }); body.append(t); thread = mountThread(t, { limit: 8 }); } else thread.reload();
    setTimeout(() => comp.ta.focus(), 50); };
  function api_close() { el.classList.remove("open"); el.setAttribute("aria-hidden", "true"); window.dispatchEvent(new CustomEvent("vaniq:drawer", { detail: false })); }
  window.addEventListener("vaniq:open-drawer", open);
  el.addEventListener("keydown", e => { if (e.key === "Escape") api_close(); });
  return { open, close: api_close, toggle: () => (el.classList.contains("open") ? api_close() : open()) };
}
