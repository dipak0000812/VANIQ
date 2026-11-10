// Workflows: Lindy routines pattern (trigger -> steps) on a RetailSync-style canvas. Nodes are real operations and
// edges are real, type-checked data flow executed by src/workflows/engine.py.
import { api, chip, guard, h, requireReviewer, reviewer, toast } from "./legacy.js";
import { closeDialog, emptyState, icon, openDialog, timeAgo } from "./ui.js";

const NODE_W = 196;
const STATUS_CHIP = { awaiting_approval: ["Waiting for approval", "agent"], ready: ["Starting", "info"], running: ["Running", "warn"], completed: ["Completed", "ok"], failed: ["Failed", "bad"], rejected: ["Rejected", "bad"] };

export async function renderWorkflows(root, args) {
  const [types, wfs] = await Promise.all([api("/api/workflows/node-types"), api("/api/workflows")]);
  if (args[0]) {
    const wf = wfs.find(w => w.id === args[0]);
    if (!wf) { root.replaceChildren(h("div", { class: "page" }, h("div", { class: "notice bad" }, "Workflow not found."), h("a", { href: "#/workflows" }, "Back to workflows"))); return; }
    return editor(root, wf, types);
  }
  return gallery(root, wfs, types);
}

// ---------------------------------------------------------------- gallery
async function gallery(root, wfs, types) {
  const runs = await api("/api/workflow-runs");
  const cats = ["All", ...new Set(wfs.map(w => w.category))];
  let cat = "All";
  const grid = h("div", { class: "gallery" });
  const filters = h("div", { class: "suggest", role: "group", "aria-label": "Filter by category" });
  const mini = w => h("div", { class: "mini" }, w.graph.nodes.flatMap((n, i) => [i ? h("u", {}) : null, h("i", { title: n.type })]));
  function paint() {
    filters.replaceChildren(...cats.map(c => h("button", { class: c === cat ? "primary" : "", style: "border-radius:99px", onclick: () => { cat = c; paint(); } }, c)));
    const rows = wfs.filter(w => cat === "All" || w.category === cat);
    grid.replaceChildren(...(rows.length ? rows.map(w => h("div", { class: "tpl", "data-workflow": w.id },
      mini(w), h("div", {}, h("b", {}, w.name), " ", w.is_template ? chip("template", "info") : chip("yours")), h("div", { class: "hint" }, w.description || w.category),
      h("div", { class: "row", style: "margin-top:auto" },
        w.is_template ? h("button", { class: "btn primary small", onclick: () => guard(async () => { const c = await api(`/api/workflows/${w.id}/duplicate`, { method: "POST" }); location.hash = "#/workflows/" + c.id; }) }, "Use template") : h("a", { class: "btn primary small", href: "#/workflows/" + w.id }, "Open"),
        w.is_template ? h("a", { class: "btn small", href: "#/workflows/" + w.id }, "View") : h("button", { class: "btn danger small", onclick: () => guard(async () => { if (!confirm("Delete this workflow?")) return; await api("/api/workflows/" + w.id, { method: "DELETE" }); window.dispatchEvent(new Event("vaniq:refresh")); }) }, "Delete"))))
      : [emptyState("No workflows in this category", "Pick another category or start a blank workflow.")]));
  }
  paint();
  root.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Workflows"),
    h("p", { class: "lede" }, "Chain real VANIQ operations. A connection is real data flow: the clips a node outputs are exactly what the next node receives. Steps with outside impact (STT provider calls, exports) wait for your approval before a run starts."),
    h("div", { class: "row", style: "margin-bottom:10px" }, h("button", { class: "btn primary", onclick: () => guard(async () => {
      const c = await api("/api/workflows", { method: "POST", json: { name: "Untitled workflow", category: "Custom", description: "", graph: { nodes: [{ id: "n1", type: "select_clips", config: {}, x: 40, y: 60 }], edges: [] } } });
      location.hash = "#/workflows/" + c.id; }) }, icon("plus", 15), "New workflow")),
    filters, grid, h("h2", {}, "Recent runs"),
    runs.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Workflow", "Status", "By", "When"].map(x => h("th", {}, x)))),
      h("tbody", {}, runs.slice(0, 10).map(r => { const w = wfs.find(x => x.id === r.workflow_id); const [l, k] = STATUS_CHIP[r.status] || [r.status, ""];
        return h("tr", {}, h("td", {}, h("a", { href: "#/workflows/" + r.workflow_id }, w ? w.name : r.workflow_id)), h("td", {}, chip(l, k)), h("td", {}, r.actor), h("td", {}, timeAgo(r.created_at))); }))))
      : emptyState("No runs yet", "Open a template and press Run.")));
}

// ---------------------------------------------------------------- editor
function editor(root, wf, types) {
  const T = Object.fromEntries(types.map(t => [t.type, t]));
  const readOnly = !!wf.is_template;
  const g = JSON.parse(JSON.stringify(wf.graph));
  g.nodes.forEach((n, i) => { n.x = n.x ?? 40 + i * 230; n.y = n.y ?? 60; n.config = n.config || {}; });
  let sel = null, selEdge = null, dirty = false, armed = null, currentRun = null, pollTimer = null, valTimer = null, validation = { valid: true, errors: [] };
  const nodeEls = {};
  const accepts = (cons, prod) => cons !== null && (cons === prod || (cons === "clips" && prod === "transcripts"));

  const name = h("input", { type: "text", value: wf.name, maxlength: "120", "aria-label": "Workflow name", disabled: readOnly, style: "font-weight:650;min-width:220px", oninput: () => mark() });
  const saveBtn = h("button", { class: "btn small", disabled: readOnly, onclick: save }, "Save");
  const runBtn = h("button", { class: "btn primary small", onclick: run }, icon("play", 14), "Run");
  const valChip = h("span", {}), dirtyChip = h("span", { class: "hint" });
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("class", "wf-svg");
  const inner = h("div", { class: "wf-inner" }, svg);
  const canvas = h("div", { class: "wf-canvas", tabindex: "-1", "data-testid": "wf-canvas" }, inner);
  const side = h("aside", { class: "wf-side" });
  const pal = h("aside", { class: "wf-pal", "aria-label": "Node library" });
  const sideToggle = h("button", { class: "btn small", onclick: () => side.classList.toggle("open"), "aria-label": "Toggle details panel" }, icon("panel", 15), "Details");

  function mark() { dirty = true; dirtyChip.textContent = "Unsaved changes"; runBtn.disabled = true; scheduleValidate(); }
  function scheduleValidate() { clearTimeout(valTimer); valTimer = setTimeout(validate, 200); }
  async function validate() {
    try { validation = await api("/api/workflows/validate", { method: "POST", json: { graph: cleanGraph() } }); } catch (e) { validation = { valid: false, errors: [e.message] }; }
    valChip.replaceChildren(chip(validation.valid ? "Valid" : `${validation.errors.length} problem(s)`, validation.valid ? "ok" : "bad"));
    drawEdges(); paintSide();
  }
  const cleanGraph = () => ({ nodes: g.nodes.map(({ id, type, config, x, y }) => ({ id, type, config: pruned(type, config), x, y })), edges: g.edges.map(e => ({ from: e.from, to: e.to })) });
  const pruned = (type, cfg) => Object.fromEntries(Object.entries(cfg).filter(([k]) => k in (T[type] ? T[type].config : {})));

  async function save() {
    await guard(async () => { const w = await api("/api/workflows/" + wf.id, { method: "PUT", json: { name: name.value || "Untitled workflow", category: wf.category, description: wf.description, graph: cleanGraph() } });
      wf = w; dirty = false; dirtyChip.textContent = ""; runBtn.disabled = !validation.valid; toast("Workflow saved"); });
  }

  // ----- nodes
  function addNode(type) {
    if (readOnly) return;
    let id = 1; while (g.nodes.some(n => n.id === "n" + id)) id++;
    const x = 40 + (g.nodes.length % 5) * 230, y = 60 + Math.floor(g.nodes.length / 5) * 170;
    const cfg = {}; Object.entries(T[type].config).forEach(([k, s]) => { cfg[k] = s.default; });
    g.nodes.push({ id: "n" + id, type, config: cfg, x, y }); sel = "n" + id; selEdge = null; drawNodes(); mark();
  }
  function drawNodes() {
    Object.values(nodeEls).forEach(e => e.remove()); for (const k in nodeEls) delete nodeEls[k];
    g.nodes.forEach(n => {
      const t = T[n.type] || { title: n.type, description: "", accepts: null, produces: "clips" };
      const el = h("div", { class: "node" + (n.id === sel ? " sel" : ""), "data-node": n.id, "data-type": n.type, style: `left:${n.x}px;top:${n.y}px`, tabindex: "0", role: "group", "aria-label": `${t.title} node` },
        h("div", { class: "nh" }, t.title, t.consequential ? chip("approval", "agent") : null),
        h("div", { class: "nd" }, `${t.accepts ? "in: " + t.accepts : "source"} → out: ${t.produces}`),
        t.accepts !== null ? h("span", { class: "port in", role: "button", tabindex: "0", "data-port": "in", "aria-label": `Input of ${t.title}`, onpointerup: ev => finishLink(ev, n.id), onclick: ev => { ev.stopPropagation(); if (armed) connect(armed, n.id); }, onkeydown: ev => { if (ev.key === "Enter" && armed) connect(armed, n.id); } }) : null,
        h("span", { class: "port out" + (armed === n.id ? " armed" : ""), role: "button", tabindex: "0", "data-port": "out", "aria-label": `Output of ${t.title}. Press Enter, then choose an input.`,
          onpointerdown: ev => startLink(ev, n.id), onclick: ev => { ev.stopPropagation(); armed = armed === n.id ? null : n.id; drawNodes(); }, onkeydown: ev => { if (ev.key === "Enter") { armed = armed === n.id ? null : n.id; drawNodes(); } } }),
        h("div", { class: "ns", "data-state": "" }, ""));
      el.querySelector(".ns").style.display = "none";
      el.addEventListener("pointerdown", ev => dragStart(ev, n, el));
      el.addEventListener("click", ev => { ev.stopPropagation(); sel = n.id; selEdge = null; for (const e of Object.values(nodeEls)) e.classList.toggle("sel", e.dataset.node === sel); paintSide(); drawEdges(); });
      el.addEventListener("keydown", ev => { if ((ev.key === "Delete" || ev.key === "Backspace") && ev.target === el) removeNode(n.id); });
      inner.append(el); nodeEls[n.id] = el;
    });
    paintRun(); drawEdges(); paintSide();
  }
  function removeNode(id) {
    if (readOnly) return;
    g.nodes = g.nodes.filter(n => n.id !== id); g.edges = g.edges.filter(e => e.from !== id && e.to !== id); sel = null; drawNodes(); mark();
  }
  function dragStart(ev, n, el) {
    if (readOnly || ev.target.classList.contains("port") || ev.button !== 0) return;
    const sx = ev.clientX, sy = ev.clientY, ox = n.x, oy = n.y; let moved = false;
    const move = e => { moved = true; n.x = Math.max(0, Math.round(ox + e.clientX - sx)); n.y = Math.max(0, Math.round(oy + e.clientY - sy)); el.style.left = n.x + "px"; el.style.top = n.y + "px"; drawEdges(); };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); if (moved) mark(); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }
  // ----- edges
  let linking = null;
  function startLink(ev, from) {
    if (readOnly) return;
    ev.stopPropagation(); ev.preventDefault();
    linking = { from, x: 0, y: 0 };
    const move = e => { const r = inner.getBoundingClientRect(); linking.x = e.clientX - r.left; linking.y = e.clientY - r.top; drawEdges(); };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); setTimeout(() => { linking = null; drawEdges(); }, 0); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); move(ev);
  }
  function finishLink(ev, to) { if (linking) { const from = linking.from; linking = null; connect(from, to); } }
  function connect(from, to) {
    armed = null;
    if (readOnly || from === to) { drawNodes(); return; }
    const a = g.nodes.find(n => n.id === from), b = g.nodes.find(n => n.id === to);
    const pa = T[a.type], pb = T[b.type];
    if (!accepts(pb.accepts, pa.produces)) { toast(`Cannot connect ${pa.title} (outputs ${pa.produces}) to ${pb.title} (${pb.accepts ? "expects " + pb.accepts : "takes no input"}).`, true); drawNodes(); return; }
    g.edges = g.edges.filter(e => e.to !== to);                      // one input per node
    g.edges.push({ from, to }); drawNodes(); mark();
  }
  function portPos(id, side) {
    const el = nodeEls[id]; if (!el) return null;
    return { x: el.offsetLeft + (side === "out" ? el.offsetWidth : 0), y: el.offsetTop + el.offsetHeight / 2 };
  }
  function drawEdges() {
    svg.replaceChildren();
    const bad = new Set(); (validation.errors || []).forEach(e => g.edges.forEach(x => { if (e.includes(`${x.from}→${x.to}`)) bad.add(x.from + ">" + x.to); }));
    const curve = (a, b) => `M${a.x},${a.y} C${a.x + 70},${a.y} ${b.x - 70},${b.y} ${b.x},${b.y}`;
    g.edges.forEach(e => {
      const a = portPos(e.from, "out"), b = portPos(e.to, "in"); if (!a || !b) return;
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", curve(a, b));
      const live = currentRun && currentRun.node_states[e.from] && currentRun.node_states[e.from].status === "done";
      p.setAttribute("class", (live ? "live " : "") + (selEdge === e.from + ">" + e.to ? "sel" : "")); p.setAttribute("data-edge", `${e.from}>${e.to}`);
      svg.append(p);
      if (!readOnly) {                                                   // wide invisible hit target to select an edge
        const hit = document.createElementNS("http://www.w3.org/2000/svg", "path"); hit.setAttribute("d", curve(a, b));
        hit.setAttribute("style", "stroke:transparent;stroke-width:14;pointer-events:stroke;cursor:pointer"); hit.setAttribute("data-edge-hit", `${e.from}>${e.to}`);
        hit.addEventListener("click", () => { selEdge = e.from + ">" + e.to; sel = null; paintSide(); drawEdges(); }); svg.append(hit);
      }
    });
    if (linking) { const a = portPos(linking.from, "out"); if (a) { const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", curve(a, { x: linking.x, y: linking.y })); p.setAttribute("class", "live"); svg.append(p); } }
  }
  canvas.addEventListener("click", () => { sel = null; selEdge = null; armed = null; for (const e of Object.values(nodeEls)) e.classList.remove("sel"); paintSide(); drawEdges(); });

  // ----- side panel
  function paintSide() {
    const kids = [];
    if (readOnly) kids.push(h("div", { class: "notice" }, "This is a read-only template. Use “Use template” in the gallery to make an editable copy; you can still run it."));
    if (selEdge) {
      const [a, b] = selEdge.split(">");
      kids.push(h("h3", {}, "Connection"), h("div", { class: "hint" }, `${a} → ${b}`), readOnly ? null : h("button", { class: "btn danger small", style: "margin-top:8px", onclick: () => { g.edges = g.edges.filter(e => e.from + ">" + e.to !== selEdge); selEdge = null; drawNodes(); mark(); } }, "Remove connection"));
    } else if (sel) {
      const n = g.nodes.find(x => x.id === sel), t = n && T[n.type];
      if (n) {
        kids.push(h("h3", {}, t.title), h("div", { class: "hint" }, t.description), h("div", { style: "margin:6px 0" }, chip(`in: ${t.accepts || "none (source)"}`), " ", chip(`out: ${t.produces}`), " ", t.consequential ? chip("needs approval", "agent") : null));
        for (const [k, spec] of Object.entries(t.config)) {
          let ctl; const val = n.config[k] ?? spec.default;
          if (spec.type === "select") ctl = h("select", { disabled: readOnly, "aria-label": k }, spec.options.map(o => h("option", { value: o, selected: o === val }, o)));
          else if (spec.type === "boolean") ctl = h("input", { type: "checkbox", checked: !!val, disabled: readOnly, "aria-label": k });
          else ctl = h("input", { type: "text", value: val ?? "", disabled: readOnly, "aria-label": k });
          ctl.addEventListener("change", () => { n.config[k] = spec.type === "boolean" ? ctl.checked : ctl.value; mark(); });
          kids.push(h("div", { class: "field" }, h("label", {}, k.replaceAll("_", " ")), ctl));
        }
        if (!readOnly) kids.push(h("button", { class: "btn danger small", style: "margin-top:8px", onclick: () => removeNode(n.id) }, "Delete node"));
      }
    } else {
      kids.push(h("h3", {}, "Checks"), validation.errors && validation.errors.length ? h("ul", { class: "errlist" }, validation.errors.map(e => h("li", {}, e))) : h("div", { class: "notice ok" }, "The workflow is valid. Every connection is type-checked."),
        validation.consequential_nodes && validation.consequential_nodes.length ? h("div", { class: "notice warn" }, `A run will ask for approval first because of: ${validation.consequential_nodes.join(", ")}.`) : null);
    }
    if (currentRun) kids.push(runPanel());
    side.replaceChildren(...kids);
  }
  function runPanel() {
    const r = currentRun, [l, k] = STATUS_CHIP[r.status] || [r.status, ""];
    return h("div", { style: "margin-top:14px;border-top:1px solid var(--line);padding-top:10px", "data-testid": "run-panel" },
      h("h3", {}, "Run ", chip(l, k)), r.error ? h("div", { class: "notice bad" }, r.error) : null,
      r.approved_by ? h("div", { class: "hint" }, `Approved by ${r.approved_by}`) : null,
      r.status === "awaiting_approval" ? h("div", { class: "notice warn" }, h("b", {}, "Needs your approval. "), "Nothing has run. Approving lets this workflow call the STT provider and/or create an export.",
        h("div", { class: "row", style: "margin-top:8px" },
          h("button", { class: "btn ok small", onclick: () => guard(async () => { if (!requireReviewer()) return; currentRun = await api(`/api/workflow-runs/${r.id}/approve`, { method: "POST", json: { reviewer: reviewer() } }); startPoll(); paintRun(); paintSide(); }) }, "Approve and run"),
          h("button", { class: "btn danger small", onclick: () => guard(async () => { currentRun = await api(`/api/workflow-runs/${r.id}/reject`, { method: "POST", json: { reviewer: reviewer() } }); paintRun(); paintSide(); }) }, "Reject"))) : null,
      h("div", {}, g.nodes.map(n => { const s = r.node_states[n.id] || { status: "pending" }; return h("div", { class: "hint", style: "margin:4px 0" }, h("b", {}, `${n.id} ${T[n.type] ? T[n.type].title : n.type}: `), s.status, s.summary ? " · " + s.summary : "", s.error ? " · " + s.error.message : "",
        s.output_ref && s.output_ref.download ? h("span", {}, " · ", h("a", { href: s.output_ref.download }, "download")) : null); })));
  }
  function paintRun() {
    g.nodes.forEach(n => {
      const el = nodeEls[n.id]; if (!el) return; const s = currentRun && currentRun.node_states[n.id];
      ["running", "done", "failed", "skipped"].forEach(c => el.classList.remove(c));
      const ns = el.querySelector(".ns");
      if (s && s.status !== "pending") { el.classList.add(s.status); ns.style.display = ""; ns.textContent = s.summary || (s.error ? s.error.message : s.status); ns.setAttribute("data-state", s.status); } else ns.style.display = "none";
    });
    drawEdges();
  }
  function startPoll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      if (!currentRun || !root.isConnected) return;
      try { currentRun = await api("/api/workflow-runs/" + currentRun.id); } catch (_) { return; }
      paintRun(); paintSide();
      if (["running", "ready"].includes(currentRun.status)) startPoll();
    }, 700);
  }
  async function run() {
    if (dirty) { toast("Save the workflow before running it.", true); return; }
    await guard(async () => {
      currentRun = await api(`/api/workflows/${wf.id}/run`, { method: "POST", json: { reviewer: reviewer() } });
      side.classList.add("open"); paintRun(); paintSide();
      if (["running", "ready"].includes(currentRun.status)) startPoll();
    });
  }

  // ----- palette
  const cats = {}; types.forEach(t => (cats[t.category] = cats[t.category] || []).push(t));
  pal.append(h("h3", { style: "margin-top:0" }, "Nodes"), h("p", { class: "hint" }, readOnly ? "Templates are read-only." : "Click to add. Drag from an output dot to an input dot to connect (or press Enter on an output, then on an input)."));
  for (const [c, list] of Object.entries(cats)) pal.append(h("div", { class: "hint", style: "margin:8px 0 4px" }, c), ...list.map(t => h("button", { class: "pal-item", disabled: readOnly, "data-add": t.type, onclick: () => addNode(t.type) }, h("b", {}, t.title), t.consequential ? " " : "", t.consequential ? chip("approval", "agent") : null, h("small", {}, t.description))));

  root.replaceChildren(h("div", { style: "height:100%;display:flex;flex-direction:column;min-height:0" },
    h("div", { class: "wf-bar" }, h("a", { class: "btn ghost small", href: "#/workflows" }, "← Workflows"), name, readOnly ? chip("template", "info") : null, valChip, dirtyChip,
      h("span", { style: "margin-left:auto;display:flex;gap:8px" }, sideToggle, saveBtn, runBtn)),
    h("div", { class: "wf-shell", style: "flex:1" }, pal, canvas, side)));
  drawNodes();
  validate().then(() => { runBtn.disabled = !validation.valid; });
  api("/api/workflow-runs?workflow_id=" + wf.id).then(rs => { const live = rs.find(r => ["awaiting_approval", "running", "ready"].includes(r.status)); if (live) { currentRun = live; paintRun(); paintSide(); if (["running", "ready"].includes(live.status)) startPoll(); } });
}
