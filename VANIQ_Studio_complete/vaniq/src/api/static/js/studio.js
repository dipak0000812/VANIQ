// Voice-data studio (RetailSync-pattern editor shell): recordings | canvas (waveform + tracks) | inspector.
import { api, chip, clipTable, dur, guard, h, loadClip, renderUpload, short, state, statusChip, toast, reviewer } from "./legacy.js";
import { app, closeDialog, emptyState, icon, openDialog } from "./ui.js";
import { askAgent } from "./agent.js";

const REASON = {
  permission_unknown: "permission or permitted usage is unknown", permission_denied: "permission is denied", usage_not_public: "permitted usage is not public release",
  not_verified: "no human-verified reference yet", rejected_clip: "clip is marked unusable", missing: "clip missing",
};

// ---------------------------------------------------------------- waveform
function waveform(source, clips, getSelected, onSelect) {
  const url = `/api/sources/${source.id}/audio`;
  const audio = new Audio(); audio.preload = "auto"; audio.src = url;
  let peaksData = null, pps = 120, segEnd = null, loop = false, duration = source.duration_s || 1;
  const canvas = h("canvas", { "aria-label": "Waveform of the recording", role: "img" });
  const inner = h("div", { style: "position:relative" }, canvas);
  const playhead = h("div", { style: "position:absolute;top:0;bottom:0;width:2px;background:#c0392b;pointer-events:none;left:0" });
  const scroll = h("div", { class: "wave-scroll" }, inner);
  const status = h("div", { class: "hint", style: "padding:6px" }, "Decoding audio…");
  const time = h("span", { class: "time", "aria-live": "off" }, "0.0 / " + duration.toFixed(1) + " s");
  const playBtn = h("button", { class: "btn small", "aria-label": "Play or pause", onclick: () => (audio.paused ? (segEnd = null, audio.play()) : audio.pause()) }, icon("play", 15), "Play");
  const segBtn = h("button", { class: "btn small", onclick: () => playSegment() }, "Play segment");
  const loopCb = h("input", { type: "checkbox", id: "wf-loop", onchange: e => { loop = e.target.checked; } });
  const zoom = h("input", { type: "range", min: "40", max: "600", value: String(pps), "aria-label": "Zoom (pixels per second)", oninput: e => { pps = +e.target.value; layout(); } });
  const regionsEl = h("div", { class: "regions", role: "group", "aria-label": "Segments" });
  const overlay = [];

  function playSegment() {
    const c = clips.find(x => x.id === getSelected());
    if (!c) { toast("Select a segment first.", true); return; }
    audio.currentTime = c.start_s; segEnd = c.end_s; audio.play();
  }
  function layout() {
    const w = Math.max(scroll.clientWidth || 600, Math.ceil(duration * pps)), hgt = 132, dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = hgt * dpr; canvas.style.width = w + "px"; canvas.style.height = hgt + "px";
    inner.style.width = w + "px"; inner.style.height = hgt + "px";
    const g = canvas.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, hgt);
    g.fillStyle = "#2f7f86"; g.globalAlpha = .9;
    if (peaksData) {
      const { ch, n } = peaksData, mid = hgt / 2, per = n / w;
      for (let x = 0; x < w; x++) {
        let mn = 1, mx = -1;
        const a = Math.floor(x * per), b = Math.min(n, Math.floor((x + 1) * per) + 1);
        for (let i = a; i < b; i++) { const v = ch[i]; if (v < mn) mn = v; if (v > mx) mx = v; }
        if (mx < mn) continue;
        g.fillRect(x, mid - mx * mid * .95, 1, Math.max(1, (mx - mn) * mid * .95));
      }
    }
    g.globalAlpha = 1; g.fillStyle = "#b9c9cb"; g.fillRect(0, hgt / 2, w, .5);
    overlay.forEach(o => o.remove()); overlay.length = 0;
    clips.forEach((c, i) => {
      const b = h("button", { class: "region", "data-clip": c.id, "aria-label": `Segment ${i + 1}, ${c.start_s.toFixed(2)} to ${c.end_s.toFixed(2)} seconds`,
        style: `position:absolute;top:0;bottom:0;left:${c.start_s * w / duration}px;width:${Math.max(4, (c.end_s - c.start_s) * w / duration)}px;border:0;border-left:2px solid #2b44d1;border-right:2px solid #2b44d1;background:rgba(43,68,209,.10);border-radius:0;padding:0;cursor:pointer;text-align:left;font-size:11px;color:#2b44d1;font-weight:700`,
        onclick: ev => { ev.stopPropagation(); audio.currentTime = c.start_s; onSelect(c.id); } }, " " + (i + 1));
      inner.append(b); overlay.push(b);
    });
    inner.append(playhead);
    paintSelection();
  }
  function paintSelection() {
    const sel = getSelected();
    overlay.forEach(b => { const on = b.dataset.clip === sel; b.style.background = on ? "rgba(43,68,209,.26)" : "rgba(43,68,209,.10)"; b.setAttribute("aria-pressed", String(on)); });
    regionsEl.replaceChildren(...clips.map((c, i) => h("button", { class: "region-chip" + (c.id === sel ? " active" : ""), onclick: () => { audio.currentTime = c.start_s; onSelect(c.id); } },
      `${i + 1} · ${c.duration_s.toFixed(1)} s`)));
  }
  function tick() {
    const w = inner.clientWidth || 1;
    playhead.style.left = (audio.currentTime / duration * w) + "px";
    time.textContent = `${audio.currentTime.toFixed(1)} / ${duration.toFixed(1)} s`;
    if (segEnd !== null && audio.currentTime >= segEnd) {
      if (loop) { const c = clips.find(x => x.id === getSelected()); audio.currentTime = c ? c.start_s : 0; } else { audio.pause(); segEnd = null; }
    }
    if (!audio.paused) requestAnimationFrame(tick);
  }
  audio.addEventListener("play", () => { playBtn.replaceChildren(icon("pause", 15), "Pause"); requestAnimationFrame(tick); });
  audio.addEventListener("pause", () => { playBtn.replaceChildren(icon("play", 15), "Play"); tick(); });
  audio.addEventListener("ended", () => { playBtn.replaceChildren(icon("play", 15), "Play"); });
  audio.addEventListener("seeked", tick);
  inner.addEventListener("click", e => {
    const r = inner.getBoundingClientRect(), t = (e.clientX - r.left) / r.width * duration;
    audio.currentTime = t; const c = clips.find(x => t >= x.start_s && t <= x.end_s); if (c) onSelect(c.id); tick();
  });
  (async () => {
    try {
      const buf = await (await fetch(url)).arrayBuffer();
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ac = new Ctx(); const dec = await ac.decodeAudioData(buf); ac.close && ac.close();
      peaksData = { ch: dec.getChannelData(0), n: dec.length }; duration = dec.duration;
      status.textContent = `${dec.sampleRate} Hz, ${dec.duration.toFixed(1)} s. Click the waveform to seek; click a segment to select it.`;
    } catch (e) { status.textContent = "Waveform preview unavailable in this browser; playback and segments still work."; }
    layout();
  })();
  const ro = new ResizeObserver(() => { if (peaksData) layout(); }); ro.observe(scroll);
  const el = h("div", { class: "wave-card", "data-testid": "waveform" }, scroll, status,
    h("div", { class: "transport" }, playBtn, segBtn, h("label", { for: "wf-loop", style: "display:flex;gap:4px;align-items:center;margin:0" }, loopCb, "Loop segment"),
      h("span", { style: "margin-left:auto;display:flex;gap:6px;align-items:center" }, h("span", { class: "hint" }, "Zoom"), zoom), time), regionsEl);
  layout();
  return { el, paintSelection, destroy() { audio.pause(); audio.src = ""; ro.disconnect(); }, audio };
}

// ---------------------------------------------------------------- inspector
function field(k, v, note) { return h("div", { class: "field" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v), note ? h("div", { class: "note" }, note) : null); }

async function inspector(ws, source, reload) {
  const clip = ws.clip, last = ws.transcripts[ws.transcripts.length - 1];
  const [pub, int] = await Promise.all([api("/api/datasets/eligibility?visibility=public"), api("/api/datasets/eligibility?visibility=internal")]);
  const el = (list) => list.clips.find(c => c.clip_id === clip.id);
  const elig = (list, label) => { const r = el(list); return h("div", {}, chip(r && r.eligible ? "eligible" : "not eligible", r && r.eligible ? "ok" : "bad"), " ", label,
    r && !r.eligible ? h("div", { class: "note" }, REASON[r.reason] || r.reason) : null); };

  const dialect = h("input", { type: "text", value: source.dialect_label, "aria-label": "Declared dialect" });
  const perm = h("select", { "aria-label": "Permission status" }, ["UNKNOWN", "granted", "denied"].map(v => h("option", { value: v, selected: v === source.permission_status }, v)));
  const use = h("select", { "aria-label": "Permitted usage" }, ["UNKNOWN", "private_research", "internal_training", "public_release"].map(v => h("option", { value: v, selected: v === source.permitted_usage }, v)));
  const speaker = h("input", { type: "text", value: source.speaker_id, "aria-label": "Speaker pseudonym" });
  const save = h("button", { class: "btn small primary", onclick: () => guard(async () => {
    await api("/api/sources/" + source.id, { method: "PATCH", json: { dialect_label: dialect.value, speaker_id: speaker.value, permission_status: perm.value, permitted_usage: use.value, reviewer: reviewer() } });
    toast("Recording details saved"); reload();
  }) }, "Save details");

  return h("div", {},
    h("div", { class: "insp-sec" }, h("h3", {}, "Speaker and dialect"),
      h("div", { class: "field" }, h("div", { class: "k" }, "Speaker pseudonym"), speaker),
      h("div", { class: "field" }, h("div", { class: "k" }, "Declared dialect (set by a person)"), dialect,
        h("div", { class: "note" }, "A declaration, never inferred from provider output.")), save),
    h("div", { class: "insp-sec" }, h("h3", {}, "Provider output (baseline)"),
      field("Provider-detected language", last ? (last.detected_language_code || "none reported") : "no transcript yet", "The provider’s own detection; not dialect identification."),
      field("Transcript script", last ? (last.script || "unknown") : "no transcript yet", "Detected from characters; not evidence of language."),
      field("Orthographic convention", "Not recorded yet", "Needs a documented convention (planned P1 field)."),
      field("STT provider and model", last ? `${last.provider === "demo-mock" ? "demo placeholder" : last.provider}${last.model ? " · " + last.model : ""}` : "none"),
      field("Experiment role", last ? (last.experiment_role_label || last.experiment_role) : "none")),
    h("div", { class: "insp-sec" }, h("h3", {}, "Recording"),
      field("File", source.original_name), field("Segment", `${clip.start_s.toFixed(2)}–${clip.end_s.toFixed(2)} s (${dur(clip.duration_s)})`),
      field("Level / peak", `${clip.rms_dbfs} / ${clip.peak_dbfs} dBFS`), field("Silence ratio", `${(clip.silence_ratio * 100).toFixed(0)}%`),
      clip.quality_flags.length ? h("div", {}, clip.quality_flags.map(q => chip(q.replace("_", " "), "warn"))) : field("Quality flags", "none")),
    h("div", { class: "insp-sec" }, h("h3", {}, "Consent and permission"),
      h("div", { class: "field" }, h("div", { class: "k" }, "Permission"), perm), h("div", { class: "field" }, h("div", { class: "k" }, "Permitted usage"), use),
      source.consent_notes ? field("Consent notes", source.consent_notes) : null, h("div", { class: "note" }, "Use “Save details” above to store changes.")),
    h("div", { class: "insp-sec" }, h("h3", {}, "Verification and export"),
      h("div", { class: "field" }, statusChip(clip.review_status),
        clip.reference_by ? h("div", { class: "note" }, `Reference by ${clip.reference_by}, ${(clip.reference_at || "").slice(0, 10)}`) : h("div", { class: "note" }, "No human reference yet.")),
      elig(pub, "public export"), elig(int, "internal export")));
}

// ---------------------------------------------------------------- view
export async function renderStudio(root, args) {
  const [sources, clips] = await Promise.all([api("/api/sources"), api("/api/clips")]);
  const byId = Object.fromEntries(clips.map(c => [c.id, c]));
  let sel = args[0] || app.clipId;
  let srcId = null;
  if (sel && sel.startsWith("source:")) { srcId = sel.slice(7); sel = null; }
  if (sel && !byId[sel]) sel = null;
  if (sel) srcId = byId[sel].source_id;
  if (!srcId && sources.length) srcId = sources[0].id;
  const srcClips = () => clips.filter(c => c.source_id === srcId).sort((a, b) => a.start_s - b.start_s);
  if (!sel && srcId) sel = (srcClips()[0] || {}).id || null;
  const source = sources.find(s => s.id === srcId) || null;
  app.clipId = sel; app.sourceId = srcId; app.sourceLabel = source ? source.original_name : ""; app.clipLabel = sel ? short(sel) : "";
  document.getElementById("crumb-view").textContent = source ? `Studio / ${source.original_name}` : "Studio";

  const studio = h("div", { class: "studio" });
  const filter = h("input", { type: "search", placeholder: "Filter recordings", "aria-label": "Filter recordings", style: "width:100%;margin-bottom:6px" });
  const list = h("div", { role: "list" });
  const paintList = () => {
    const q = filter.value.trim().toLowerCase();
    const rows = sources.filter(s => !q || s.original_name.toLowerCase().includes(q));
    list.replaceChildren(...(rows.length ? rows.map(s => h("button", { class: "rec" + (s.id === srcId ? " active" : ""), role: "listitem", "data-source": s.id,
      onclick: () => { const first = clips.filter(c => c.source_id === s.id).sort((a, b) => a.start_s - b.start_s)[0]; location.hash = first ? "#/studio/" + first.id : "#/studio/source:" + s.id; } },
      h("div", { class: "n" }, s.original_name), h("div", { class: "m" }, `${s.clip_count} clip${s.clip_count === 1 ? "" : "s"}`, " · ", dur(s.duration_s), " ", statusChip(s.permission_status), s.is_demo ? chip("demo", "warn") : null)))
      : [emptyState(sources.length ? "No match" : "No recordings yet", sources.length ? "Try a different filter." : "Upload or record audio to start.")]));
  };
  filter.addEventListener("input", paintList); paintList();
  const upBtn = h("button", { class: "btn small primary", onclick: () => openUpload() }, icon("upload", 15), "Add audio");
  const left = h("section", { class: "panel-l", "aria-label": "Recordings" }, h("div", { class: "panel-h" }, "Recordings", h("span", { style: "margin-left:auto" }, upBtn)),
    h("div", { class: "panel-b" }, filter, list));

  function openUpload() {
    const body = h("div", {}); renderUpload(body);
    body.append(h("div", { class: "row", style: "margin-top:12px" }, h("button", { class: "btn", onclick: () => { closeDialog(); window.dispatchEvent(new Event("vaniq:refresh")); } }, "Done")));
    openDialog("Add audio", body);
  }

  const center = h("div", { class: "canvas-wrap" });
  const insp = h("aside", { class: "inspector", "aria-label": "Inspector" });
  const tracksBox = h("div", { class: "tracks" });
  let wf = null;

  async function selectClip(id) {
    sel = id; app.clipId = id; app.clipLabel = short(id);
    history.replaceState(null, "", "#/studio/" + id);
    window.dispatchEvent(new CustomEvent("vaniq:context"));
    if (wf) wf.paintSelection();
    await loadTracks();
  }
  async function loadTracks() {
    if (!sel) { tracksBox.replaceChildren(emptyState("No segment selected", source && source.segmentation_status === "no_speech" ? "No audio activity was detected in this recording, so no segments were created. Check the level or lower VANIQ_SEG_ENERGY_THRESHOLD." : "Select a segment on the waveform.")); insp.replaceChildren(emptyState("Nothing selected", "Select a segment to inspect it.")); return; }
    tracksBox.setAttribute("aria-busy", "true");
    await guard(() => loadClip(tracksBox, sel, { hideHeader: true, onLoaded: async ws => { insp.replaceChildren(await inspector(ws, source, () => window.dispatchEvent(new Event("vaniq:refresh")))); } }));
    tracksBox.removeAttribute("aria-busy");
  }

  if (!source) {
    center.append(h("div", { class: "canvas-scroll" }, emptyState("No recordings yet", "Add audio to open it on the canvas, or load the demo data from Home.", h("button", { class: "btn primary", onclick: openUpload }, "Add audio"))));
    studio.append(left, center, insp);
    insp.replaceChildren(emptyState("Inspector", "Properties of the selected segment appear here."));
    root.replaceChildren(studio);
    return;
  }

  const ai = (label, msg) => h("button", { class: "btn agent small", onclick: () => askAgent(msg, true), title: "Asks the VANIQ agent with this clip as context" }, label);
  const inspToggle = h("button", { class: "btn small", "aria-label": "Toggle inspector", onclick: () => { studio.classList.toggle("insp-c"); studio.classList.toggle("insp-open"); } }, icon("panel", 15), "Inspector");
  center.append(
    h("div", { class: "canvas-top" }, h("b", {}, source.original_name), h("span", { class: "hint" }, `${dur(source.duration_s)} · ${srcClips().length} segment(s)`),
      h("span", { style: "margin-left:auto;display:flex;gap:6px;flex-wrap:wrap" }, h("span", { class: "hint", style: "align-self:center" }, "Ask VANIQ:"),
        ai("Run STT baseline (mr-IN)", "run baseline mr-IN on this clip"), ai("Check mismatch", "check transcript mismatch for this clip"),
        ai("Propose corrections", "propose corrections for this clip"), ai("Eligibility", "check dataset eligibility"), inspToggle)),
    h("div", { class: "canvas-scroll" }, srcClips().length ? (wf = waveform(source, srcClips(), () => sel, selectClip)).el
      : emptyState("No segments", source.segmentation_status === "no_speech" ? "No audio activity was detected, so nothing was segmented." : "This recording has no clips."),
      h("h2", {}, "Tracks"), h("p", { class: "hint", style: "margin-top:-4px" }, "Original STT output is read-only. Corrections are proposals until a person accepts them. The human reference starts empty."), tracksBox));
  studio.append(left, center, insp);
  if (window.innerWidth < 1200) studio.classList.add("insp-c");
  root.replaceChildren(studio);
  const obs = new MutationObserver(() => { if (!root.isConnected) { if (wf) wf.destroy(); obs.disconnect(); } });
  obs.observe(document.getElementById("main"), { childList: true });
  await loadTracks();
}
