/* VANIQ Local frontend. Vanilla JS, no build step.
   All dynamic text is inserted with textContent via h(); never innerHTML (transcripts are untrusted data). */


export const state = { mode: "live", sttConfigured: false, about: null, selectedClip: null, filter: "all" };

// ---------- helpers ----------
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
export const $ = (s, r = document) => r.querySelector(s);
export const reviewer = () => ($("#reviewer").value || "").trim();

export async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); }
  if (opts.form) init.body = opts.form;
  const writes = init.method !== "GET";
  if (writes) window.dispatchEvent(new CustomEvent("vaniq:save", { detail: "saving" }));
  let res;
  try { res = await fetch(path, init); }
  catch (e) { if (writes) window.dispatchEvent(new CustomEvent("vaniq:save", { detail: "failed" })); throw new Error("Cannot reach the VANIQ server. Is it still running?"); }
  let data = null;
  try { data = await res.json(); } catch (_) { /* non-JSON */ }
  if (writes) window.dispatchEvent(new CustomEvent("vaniq:save", { detail: res.ok ? "saved" : "failed" }));
  if (!res.ok) {
    const msg = data && data.error ? data.error.message
      : data && data.detail ? (Array.isArray(data.detail) ? data.detail.map(d => d.msg).join("; ") : data.detail)
      : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}
export function toast(msg, isErr) {
  const t = h("div", { class: isErr ? "err" : "" }, msg);
  $("#toast").append(t);
  setTimeout(() => t.remove(), isErr ? 8000 : 3500);
}
export async function guard(fn) { try { return await fn(); } catch (e) { toast(e.message, true); } }
export const pct = x => (x === null || x === undefined) ? "n/a" : (x * 100).toFixed(1) + "%";
export const dur = s => s === null || s === undefined ? "" : s.toFixed(1) + " s";
export const short = id => id ? id.slice(0, 8) : "";
export function chip(text, kind) { return h("span", { class: "chip " + (kind || "") }, text); }
export function statusChip(s) {
  const map = { verified: "ok", needs_review: "warn", in_review: "info", rejected: "bad", granted: "ok", denied: "bad", UNKNOWN: "warn" };
  return chip(s.replace("_", " "), map[s]);
}
export function requireReviewer() {
  if (!reviewer()) { toast("Enter your reviewer name (bottom of the left menu) first.", true); $("#reviewer").focus(); return false; }
  return true;
}

export function clipTable(clips) {
  if (!clips.length) return h("p", { class: "muted" }, "No clips yet.");
  return h("div", { class: "tablewrap" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Clip", "Recording", "Duration", "Status", "Permission", "Transcripts"].map(x => h("th", {}, x)))),
    h("tbody", {}, clips.map(c => h("tr", {},
      h("td", {}, h("a", { href: "#/studio/" + c.id }, short(c.id))), h("td", {}, c.source_name), h("td", {}, dur(c.duration_s)),
      h("td", {}, statusChip(c.review_status)), h("td", {}, statusChip(c.permission_status)), h("td", {}, c.transcript_count))))));
}

// ---------- upload & record ----------
export async function renderUpload(main) {
  let recorder = null, chunks = [], recordedFile = null, stream = null;
  const fileInput = h("input", { type: "file", id: "file", accept: "audio/*,video/mp4,.m4a,.opus,.webm" });
  const f = {
    speaker: h("input", { type: "text", value: "UNKNOWN", id: "speaker" }),
    dialect: h("input", { type: "text", value: "UNKNOWN", id: "dialect" }),
    url: h("input", { type: "text", value: "UNKNOWN", id: "url" }),
    perm: h("select", { id: "perm" }, ["UNKNOWN", "granted", "denied"].map(v => h("option", { value: v }, v))),
    usage: h("select", { id: "usage" }, ["UNKNOWN", "private_research", "internal_training", "public_release"].map(v => h("option", { value: v }, v))),
    notes: h("textarea", { id: "notes", placeholder: "How and when consent was given, who the speaker is (no personal data needed)." }),
  };
  const result = h("div", {});
  const recStatus = h("span", { class: "muted" }, "");
  const recPreview = h("audio", { controls: true, hidden: true });
  const recBtn = h("button", { onclick: toggleRecord }, "Start recording");
  const upBtn = h("button", { class: "primary", onclick: upload }, "Upload and segment");

  async function toggleRecord() {
    if (recorder && recorder.state === "recording") { recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast("This browser cannot record audio. Upload a file instead.", true); return; }
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { toast("Microphone access was denied or is unavailable.", true); return; }
    chunks = []; recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      const type = recorder.mimeType || "audio/webm";
      const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      recordedFile = new File([new Blob(chunks, { type })], `recording-${Date.now()}.${ext}`, { type });
      recPreview.src = URL.createObjectURL(recordedFile); recPreview.hidden = false;
      recStatus.replaceChildren("Recording ready. Press “Upload and segment”."); recBtn.textContent = "Record again";
    };
    recorder.start(); recBtn.textContent = "Stop recording";
    recStatus.replaceChildren(h("span", { class: "rec-dot" }), "Recording…");
  }
  async function upload() {
    const file = recordedFile || fileInput.files[0];
    if (!file) { toast("Choose a file or record audio first.", true); return; }
    if (f.perm.value !== "granted" && f.usage.value !== "UNKNOWN") { toast("Set permission to “granted” before choosing a permitted usage.", true); return; }
    const form = new FormData();
    form.append("file", file);
    form.append("speaker_id", f.speaker.value || "UNKNOWN"); form.append("dialect_label", f.dialect.value || "UNKNOWN");
    form.append("source_url", f.url.value || "UNKNOWN"); form.append("permission_status", f.perm.value);
    form.append("permitted_usage", f.usage.value); form.append("consent_notes", f.notes.value); form.append("reviewer", reviewer());
    upBtn.disabled = true; upBtn.textContent = "Processing…";
    await guard(async () => {
      const r = await api("/api/sources", { method: "POST", form });
      showResult(r);
    });
    upBtn.disabled = false; upBtn.textContent = "Upload and segment";
  }
  function showResult(r) {
    const kids = [];
    if (r.duplicate) kids.push(h("div", { class: "notice" }, "This exact file was already uploaded; showing the existing record."));
    if (r.segmentation_status === "no_speech")
      kids.push(h("div", { class: "notice warn" }, "No audio activity was detected above the energy threshold, so no clips were created. Check the recording level or lower VANIQ_SEG_ENERGY_THRESHOLD."));
    else kids.push(h("div", { class: "notice ok" }, `Created ${r.clips.length} clip(s) from ${r.source.original_name} (${dur(r.source.duration_s)}).`));
    if (r.clips.length) kids.push(clipTable(r.clips));
    result.replaceChildren(h("h2", {}, "Result"), ...kids);
  }

  const dz = h("div", { class: "dropzone" }, h("p", {}, "Choose an audio file (wav, mp3, m4a, flac, ogg, opus, webm)."), fileInput);
  dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", e => { e.preventDefault(); dz.classList.remove("drag"); if (e.dataTransfer.files[0]) { const dt = new DataTransfer(); dt.items.add(e.dataTransfer.files[0]); fileInput.files = dt.files; recordedFile = null; } });
  fileInput.addEventListener("change", () => { recordedFile = null; });

  main.replaceChildren(
    h("h1", {}, "Upload & record"),
    h("p", { class: "lede" }, "Audio is validated, converted to 16 kHz mono WAV, and split into clips at pauses. Provenance fields stay UNKNOWN until you set them; unknown permission is never treated as consent."),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", {}, "Audio"), dz,
        h("h3", {}, "Or record in the browser"), h("div", { class: "row" }, recBtn, recStatus), recPreview),
      h("div", { class: "card" }, h("h2", {}, "Provenance & permission"),
        h("div", { class: "grid2" },
          h("div", {}, h("label", { for: "speaker" }, "Speaker ID"), f.speaker),
          h("div", {}, h("label", { for: "dialect" }, "Dialect label (your assertion)"), f.dialect),
          h("div", {}, h("label", { for: "perm" }, "Permission status"), f.perm),
          h("div", {}, h("label", { for: "usage" }, "Permitted usage"), f.usage)),
        h("label", { for: "url", style: "margin-top:.6rem" }, "Source URL or description"), f.url,
        h("label", { for: "notes", style: "margin-top:.6rem" }, "Consent notes"), f.notes)),
    h("div", { class: "row" }, upBtn), result);
}

export async function loadClip(box, clipId, opts = {}) {
  const ws = await api("/api/clips/" + clipId);
  const clip = ws.clip;
  const reload = () => loadClip(box, clipId, opts);
  const kids = [];

  if (!opts.hideHeader) kids.push(h("div", { class: "card" },
    h("div", { class: "row" }, h("h2", { style: "margin:0" }, "Clip " + short(clip.id)), statusChip(clip.review_status), statusChip(clip.permission_status),
      clip.is_demo ? chip("synthetic demo", "warn") : null, ...clip.quality_flags.map(q => chip(q.replace("_", " "), "warn"))),
    h("p", { class: "hint" }, `${clip.source_name} · ${dur(clip.duration_s)} · speaker ${clip.speaker_id} · dialect label ${clip.dialect_label} · level ${clip.rms_dbfs} dBFS, silence ${(clip.silence_ratio * 100).toFixed(0)}%`),
    h("audio", { controls: true, src: `/api/clips/${clip.id}/audio`, style: "width:100%" })));

  // transcribe / import
  const baseline = (state.about && state.about.baseline_settings) || {};
  const lang = h("input", { type: "text", value: "indic-auto", list: "langs", id: "lang", style: "width:9rem" });
  const langs = h("datalist", { id: "langs" }, Object.entries(baseline).map(([v, d]) => h("option", { value: v, label: "STT baseline setting: " + d })));
  const canTranscribe = state.mode === "demo" || state.sttConfigured;
  const tBtn = h("button", { class: "primary", disabled: !canTranscribe, onclick: () => guard(async () => {
    tBtn.disabled = true; tBtn.textContent = "Transcribing…";
    try { await api(`/api/clips/${clip.id}/transcribe`, { method: "POST", json: { language_code: lang.value, reviewer: reviewer() } }); toast("Transcript added"); }
    finally { await reload(); }
  }) }, state.mode === "demo" ? "Create demo placeholder transcript" : "Run STT baseline (Gnani Prisma)");
  const impText = h("textarea", { placeholder: "Paste a transcript produced by another tool or an earlier experiment (stored verbatim and labelled “imported”)." });
  const impLabel = h("input", { type: "text", value: "external", style: "width:12rem", "aria-label": "Source label" });
  kids.push(h("div", { class: "card" }, h("h3", {}, "Get a transcript"),
    !canTranscribe ? h("div", { class: "notice warn" }, "STT is not configured (no GNANI_API_KEY). Import a transcript instead, or configure the key and restart.") : null,
    state.mode === "demo" ? h("div", { class: "notice warn" }, "Demo provider: returns fixed placeholder text unrelated to the audio.") : null,
    h("div", { class: "row" }, h("div", {}, h("label", { for: "lang" }, "STT baseline experiment setting (language code sent to the provider)"), lang, langs), tBtn),
    h("div", { class: "notice" }, h("b", {}, "These are baseline experiment settings, not Ahirani. "),
      "mr-IN requests Marathi; indic-auto asks the provider to detect the language. Neither establishes that the speech is Ahirani, and results are never reported as Ahirani performance. The speaker’s declared dialect is set on the recording and is not changed by provider output."),
    h("details", {}, h("summary", {}, "Import an existing transcript"), impText,
      h("div", { class: "row", style: "margin-top:.4rem" }, impLabel, h("button", { onclick: () => guard(async () => {
        await api(`/api/clips/${clip.id}/transcripts/import`, { method: "POST", json: { text: impText.value, label: impLabel.value, language_code: lang.value, reviewer: reviewer() } });
        toast("Transcript imported"); reload();
      }) }, "Import")))));

  for (const t of ws.transcripts) kids.push(transcriptCard(t, reload, clip.dialect_label));
  if (!ws.transcripts.length) kids.push(h("p", { class: "muted" }, "No transcripts yet."));

  kids.push(referenceCard(clip, ws.transcripts, reload));
  box.replaceChildren(...kids);
  if (opts.onLoaded) opts.onLoaded(ws);
  return ws;
}

export function transcriptCard(t, reload, clipDialect) {
  const active = { id: null };
  const sugEls = new Map(), markEls = new Map();
  function focusSug(id) {
    active.id = id;
    sugEls.forEach((el, k) => el.classList.toggle("active", k === id));
    markEls.forEach((el, k) => el.classList.toggle("active", k === id));
    if (sugEls.get(id)) sugEls.get(id).scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  const rawBox = h("div", { class: "textbox indic" }, t.segments.length ? t.segments.map(s => {
    if (!s.suggestion_id) return s.text;
    const m = h("mark", { class: "sg " + s.status, tabindex: "0", title: `${s.status}: → ${s.replacement}`, onclick: () => focusSug(s.suggestion_id), onkeydown: e => { if (e.key === "Enter") focusSug(s.suggestion_id); } }, s.text);
    markEls.set(s.suggestion_id, m); return m;
  }) : t.transcript_raw);

  const head = h("div", { class: "row" },
    h("h3", { style: "margin:0" }, `Transcript #${t.id}`),
    chip(t.provider === "demo-mock" ? "demo placeholder" : t.provider, t.is_synthetic ? "warn" : "info"),
    t.model ? chip(t.model) : null,
    chip(t.experiment_role === "baseline" ? "STT baseline experiment" : (t.experiment_role_label || t.experiment_role), t.experiment_role === "baseline" ? "warn" : "info"),
    t.language_code_requested ? chip("baseline setting: " + t.language_code_requested) : null,
    t.detected_language_code ? chip("provider-detected: " + t.detected_language_code) : null,
    t.script ? chip("script: " + t.script) : null);
  const meta = [];
  if (t.is_synthetic) meta.push(h("div", { class: "notice warn" }, "DEMO PLACEHOLDER: this text is not a transcription of the audio."));
  if (t.provider === "imported") meta.push(h("p", { class: "hint" }, `Imported from “${t.provider_label}”. VANIQ did not produce this text.`));
  meta.push(h("dl", { class: "hint", style: "margin:.4rem 0" },
    h("div", {}, h("b", {}, "Provider-detected language: "), t.detected_language_code || "none reported",
      " (the provider’s own detection; not the speaker’s declared dialect and not dialect identification)"),
    h("div", {}, h("b", {}, "Declared dialect of this recording: "), clipDialect, " (set by a person on the recording; never changed by provider output)"),
    h("div", {}, h("b", {}, "Experiment role: "), t.experiment_role_label || t.experiment_role)));
  if (t.provider_response !== null && t.provider_response !== undefined)
    meta.push(h("details", {}, h("summary", {}, "Provider response (raw JSON as returned; credentials are never stored here)"),
      h("pre", { class: "textbox", style: "overflow:auto;font-size:.82rem" }, JSON.stringify(t.provider_response, null, 2))));
  else if (t.provider === "imported") meta.push(h("p", { class: "hint" }, "No provider response: this transcript was imported."));

  const sugList = t.suggestions.map(s => suggestionRow(s, reload, sugEls, focusSug));
  const pend = t.pending_count;

  // manual correction via selection in a read-only copy
  const sel = h("textarea", { readonly: true, class: "indic", rows: 2, "aria-label": "Select the text to correct" }, t.transcript_raw);
  const rep = h("input", { type: "text", placeholder: "Replacement text", style: "min-width:14rem" });
  const info = h("span", { class: "hint" }, "Select the words to correct in the box above.");
  sel.addEventListener("select", () => { const a = sel.selectionStart, b = sel.selectionEnd; info.textContent = b > a ? `Selected: “${t.transcript_raw.slice(a, b)}”` : ""; });
  const addBtn = h("button", { onclick: () => guard(async () => {
    if (!requireReviewer()) return;
    const a = sel.selectionStart, b = sel.selectionEnd;
    if (b <= a) { toast("Select the words to correct first.", true); return; }
    await api(`/api/transcripts/${t.id}/corrections`, { method: "POST", json: { start_char: a, end_char: b, replacement: rep.value, expected_original: t.transcript_raw.slice(a, b), reviewer: reviewer() } });
    toast("Correction recorded"); reload();
  }) }, "Add correction");

  return h("div", { class: "card" }, head, ...meta,
    h("div", { class: "grid2", style: "margin-top:.6rem" },
      h("div", {}, h("label", {}, "Original STT output (never edited)"), rawBox),
      h("div", {}, h("label", {}, "Corrected (accepted corrections only)"), h("div", { class: "textbox indic" }, t.corrected_text))),
    pend ? h("p", { class: "hint" }, `If every pending suggestion were accepted: `, h("span", { class: "indic" }, t.preview_if_all_accepted)) : null,
    h("h3", {}, `Suggested corrections (${t.suggestions.length})`),
    t.suggestions.length ? sugList : h("p", { class: "muted" }, "No suggestions. The lexicon has no matching entries for this text, and that is expected until verified entries are added (Dialect lexicon page)."),
    h("details", {}, h("summary", {}, "Add your own correction"), sel, h("div", { class: "row", style: "margin-top:.4rem" }, rep, addBtn, info)),
    h("div", { class: "row", style: "margin-top:.6rem" }, h("button", { onclick: () => guard(async () => { await api(`/api/transcripts/${t.id}/propose`, { method: "POST" }); toast("Suggestions refreshed"); reload(); }) }, "Re-run suggestions"),
      h("span", { class: "hint" }, "Re-running keeps every decision you already made.")));
}

export function suggestionRow(s, reload, sugEls, focusSug) {
  const final = h("input", { type: "text", value: s.final_replacement || s.replacement, "aria-label": "Modified replacement", class: "indic" });
  const decide = (decision, withFinal) => guard(async () => {
    if (!requireReviewer()) return;
    await api(`/api/suggestions/${s.id}/decision`, { method: "POST", json: { decision, reviewer: reviewer(), final_replacement: withFinal ? final.value : null } });
    reload();
  });
  const conf = s.confidence === null ? null : h("span", { title: s.confidence_basis },
    h("span", { class: "meter" }, h("i", { style: `width:${Math.round(s.confidence * 100)}%` })), ` ${Math.round(s.confidence * 100)}% heuristic`);
  const statusKind = { accepted: "ok", modified: "ok", rejected: "bad", pending: "warn" }[s.status];
  const row = h("div", { class: "sug", onclick: () => focusSug(s.id) },
    h("div", { class: "head" },
      h("span", { class: "indic" }, s.original), h("span", { class: "arrow" }, "→"),
      h("span", { class: "indic" }, s.status === "modified" ? s.final_replacement : s.replacement),
      chip(s.kind), chip(s.status, statusKind), s.uncertain ? chip("uncertain", "warn") : null, conf),
    h("div", { class: "why" }, s.explanation, s.decided_by ? ` Decided by ${s.decided_by}.` : ""),
    h("div", { class: "acts" },
      h("button", { class: "small ok", disabled: s.status === "accepted", onclick: () => decide("accepted") }, "Accept"),
      h("button", { class: "small danger", disabled: s.status === "rejected", onclick: () => decide("rejected") }, "Reject"),
      final, h("button", { class: "small", onclick: () => decide("modified", true) }, "Accept modified"),
      s.status !== "pending" ? h("button", { class: "small", onclick: () => decide("pending") }, "Undo") : null,
      (s.status === "accepted" || s.status === "modified") && s.kind !== "normalization" ? h("button", { class: "small", title: "Adds a candidate (unverified) lexicon entry", onclick: () => guard(async () => { if (!requireReviewer()) return; await api(`/api/suggestions/${s.id}/promote`, { method: "POST", json: { reviewer: reviewer() } }); toast("Added to lexicon as a candidate"); }) }, "Add to lexicon") : null));
  sugEls.set(s.id, row);
  return row;
}

export function referenceCard(clip, transcripts, reload) {
  // The reference is the human's independent transcription. It starts empty; STT text is shown only on explicit opt-in.
  let sttViewed = false;
  const ta = h("textarea", { class: "indic", "aria-label": "Reference transcript", placeholder: "Listen to the clip and type what was said, in your chosen spelling." }, clip.reference_transcript || "");
  const sttBox = h("div", { hidden: true });
  const last = transcripts[transcripts.length - 1];
  const showBtn = h("button", { class: "small", onclick: () => {
    if (!last) { toast("There is no STT transcript for this clip yet.", true); return; }
    sttViewed = true; sttBox.hidden = false; showBtn.hidden = true;
    sttBox.replaceChildren(
      h("div", { class: "notice warn" }, "Showing STT output can bias your transcription. Use it only if you need it."),
      h("label", {}, "Original STT output (baseline)"), h("div", { class: "textbox indic" }, last.transcript_raw),
      h("label", { style: "margin-top:.4rem" }, "Corrected text (accepted corrections only)"), h("div", { class: "textbox indic" }, last.corrected_text),
      h("div", { class: "row", style: "margin-top:.4rem" },
        h("button", { class: "small", onclick: () => { ta.value = last.transcript_raw; ta.focus(); } }, "Copy original STT into the box"),
        h("button", { class: "small", onclick: () => { ta.value = last.corrected_text; ta.focus(); } }, "Copy corrected text into the box")));
  } }, "Show STT transcript (optional)");
  const kids = [h("h3", {}, "Human-verified reference"),
    h("p", { class: "hint" }, "Write what was actually said after listening. This text is the ground truth for evaluation and is independent of any STT output.")];
  if (clip.reference_transcript) kids.push(h("div", { class: "notice ok" }, `Verified by ${clip.reference_by} on ${clip.reference_at.slice(0, 10)} (${clip.reference_script}).`));
  kids.push(ta, h("div", { class: "row", style: "margin-top:.5rem" }, showBtn), sttBox, h("div", { class: "row", style: "margin-top:.5rem" },
    h("button", { class: "primary", onclick: () => guard(async () => { if (!requireReviewer()) return; await api(`/api/clips/${clip.id}/verify`, { method: "POST", json: { reference: ta.value, reviewer: reviewer(), stt_viewed: sttViewed } }); toast("Clip verified"); reload(); }) }, clip.reference_transcript ? "Update verified reference" : "Verify as reference"),
    clip.reference_transcript ? h("button", { onclick: () => guard(async () => { await api(`/api/clips/${clip.id}/unverify`, { method: "POST", json: { reviewer: reviewer() } }); reload(); }) }, "Remove verification") : null,
    clip.review_status !== "rejected" ? h("button", { class: "danger", onclick: () => guard(async () => { if (!requireReviewer()) return; await api(`/api/clips/${clip.id}/reject`, { method: "POST", json: { reviewer: reviewer(), notes: "Unusable clip" } }); reload(); }) }, "Mark clip unusable") : null));
  return h("div", { class: "card" }, kids);
}

// ---------- lexicon ----------
export async function renderLexicon(main) {
  const rows = await api("/api/lexicon");
  const f = {
    src: h("input", { type: "text", id: "lx-src" }), tgt: h("input", { type: "text", id: "lx-tgt" }),
    kind: h("select", { id: "lx-kind" }, ["lexical", "spelling"].map(v => h("option", { value: v }, v))),
    prev: h("input", { type: "text", id: "lx-prev" }), next: h("input", { type: "text", id: "lx-next" }),
    status: h("select", { id: "lx-status" }, ["candidate", "verified"].map(v => h("option", { value: v }, v))),
    prov: h("input", { type: "text", id: "lx-prov", placeholder: "Who verified it, or the source" }),
    notes: h("input", { type: "text", id: "lx-notes" }),
  };
  const add = h("button", { class: "primary", onclick: () => guard(async () => {
    if (!requireReviewer()) return;
    await api("/api/lexicon", { method: "POST", json: { source_form: f.src.value, target_form: f.tgt.value, kind: f.kind.value, context_prev: f.prev.value, context_next: f.next.value, status: f.status.value, provenance: f.prov.value, notes: f.notes.value, reviewer: reviewer() } });
    toast("Entry added"); refresh();
  }) }, "Add entry");
  const imp = h("input", { type: "file", accept: "application/json", "aria-label": "Import lexicon JSON" });
  imp.addEventListener("change", () => guard(async () => {
    if (!requireReviewer()) { imp.value = ""; return; }
    const arr = JSON.parse(await imp.files[0].text());
    if (!Array.isArray(arr)) throw new Error("The file must contain a JSON list of entries.");
    for (const e of arr) await api("/api/lexicon", { method: "POST", json: { ...e, reviewer: reviewer() } });
    toast(`Imported ${arr.length} entries`); refresh();
  }));
  main.replaceChildren(h("h1", {}, "Dialect lexicon"),
    h("p", { class: "lede" }, "The correction engine proposes only changes that exist here. VANIQ ships with no Ahirani vocabulary; every entry comes from you or your community reviewers. This is a rule-based lookup, not a trained model."),
    h("div", { class: "card" }, h("h2", {}, "Add an entry"),
      h("div", { class: "grid3" },
        h("div", {}, h("label", { for: "lx-src" }, "Form to find (as STT writes it)"), f.src), h("div", {}, h("label", { for: "lx-tgt" }, "Proposed replacement"), f.tgt), h("div", {}, h("label", { for: "lx-kind" }, "Kind"), f.kind),
        h("div", {}, h("label", { for: "lx-prev" }, "Only when previous word is (optional)"), f.prev), h("div", {}, h("label", { for: "lx-next" }, "Only when next word is (optional)"), f.next), h("div", {}, h("label", { for: "lx-status" }, "Status"), f.status),
        h("div", {}, h("label", { for: "lx-prov" }, "Provenance"), f.prov), h("div", {}, h("label", { for: "lx-notes" }, "Notes"), f.notes)),
      h("p", { class: "hint" }, "Mark an entry “verified” only after a fluent speaker or linguist has confirmed it; provenance is required. Candidates are proposed with lower confidence and flagged as unverified."),
      h("div", { class: "row" }, add, h("div", {}, h("label", {}, "Or import a JSON list"), imp))),
    h("h2", {}, `Entries (${rows.length})`),
    rows.length ? h("div", { class: "tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Find", "Replace with", "Context", "Kind", "Status", "Provenance", "Reviews (accepted / rejected / modified)", "Active", ""].map(x => h("th", {}, x)))),
      h("tbody", {}, rows.map(r => h("tr", {},
        h("td", { class: "indic" }, r.source_form), h("td", { class: "indic" }, r.target_form),
        h("td", {}, [r.context_prev && `after “${r.context_prev}”`, r.context_next && `before “${r.context_next}”`].filter(Boolean).join(", ") || "any"),
        h("td", {}, r.kind), h("td", {}, chip(r.status, r.status === "verified" ? "ok" : "warn")), h("td", {}, r.provenance),
        h("td", {}, `${r.review_stats.accepted} / ${r.review_stats.rejected} / ${r.review_stats.modified}`),
        h("td", {}, h("input", { type: "checkbox", checked: !!r.enabled, "aria-label": "Enabled", onchange: e => guard(async () => { await api("/api/lexicon/" + r.id, { method: "PATCH", json: { enabled: e.target.checked, reviewer: reviewer() } }); }) })),
        h("td", {}, h("button", { class: "small danger", onclick: () => guard(async () => { if (!confirm("Delete this entry?")) return; await api(`/api/lexicon/${r.id}?reviewer=${encodeURIComponent(reviewer())}`, { method: "DELETE" }); refresh(); }) }, "Delete")))))))
      : h("p", { class: "muted" }, "No entries yet. Without entries the engine only offers built-in hygiene fixes (Unicode form, repeated spaces)."));
}

// ---------- datasets ----------
export async function renderDatasets(main) {
  const [sources, clips, exports] = await Promise.all([api("/api/sources"), api("/api/clips"), api("/api/exports")]);
  const permSel = (s) => {
    const p = h("select", { "aria-label": "Permission" }, ["UNKNOWN", "granted", "denied"].map(v => h("option", { value: v, selected: v === s.permission_status }, v)));
    const u = h("select", { "aria-label": "Permitted usage" }, ["UNKNOWN", "private_research", "internal_training", "public_release"].map(v => h("option", { value: v, selected: v === s.permitted_usage }, v)));
    const save = h("button", { class: "small", onclick: () => guard(async () => {
      await api("/api/sources/" + s.id, { method: "PATCH", json: { permission_status: p.value, permitted_usage: u.value, reviewer: reviewer() } }); toast("Permission updated"); refresh();
    }) }, "Save");
    return h("div", { class: "row" }, p, u, save);
  };
  const vis = h("select", { id: "vis" }, [["public", "Public (granted + public_release only)"], ["internal", "Internal (granted only)"]].map(([v, t]) => h("option", { value: v }, t)));
  const unk = h("input", { type: "checkbox", id: "unk" });
  const unkRow = h("div", { hidden: true }, h("label", {}, unk, " Also include unknown-permission clips (internal use only; recorded in the manifest)"));
  vis.addEventListener("change", () => { unkRow.hidden = vis.value !== "internal"; if (vis.value !== "internal") unk.checked = false; });
  const ver = h("input", { type: "checkbox", id: "ver", checked: true });
  const out = h("div", {});
  const exBtn = h("button", { class: "primary", onclick: () => guard(async () => {
    const r = await api("/api/exports", { method: "POST", json: { visibility: vis.value, include_unknown_internal: unk.checked, require_verified: ver.checked } });
    const m = r.manifest;
    out.replaceChildren(h("div", { class: m.clip_count ? "notice ok" : "notice warn" }, `${m.clip_count} clip(s) exported. `, m.clip_count ? h("a", { href: r.download }, "Download zip") : "Nothing matched the selection rules."),
      h("p", { class: "hint" }, "Excluded: " + Object.entries(m.excluded_counts).filter(([, v]) => v).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join(", ") || "none"));
  }) }, "Create export");

  main.replaceChildren(h("h1", {}, "Datasets"),
    h("p", { class: "lede" }, "Manage provenance and permissions, then export. Unknown or denied permissions never appear in a public export."),
    h("div", { class: "card" }, h("h2", {}, "Export"),
      h("div", { class: "row" }, h("div", {}, h("label", { for: "vis" }, "Visibility"), vis), exBtn),
      unkRow, h("div", {}, h("label", {}, ver, " Only clips with a human-verified reference")), out,
      exports.length ? h("p", { class: "hint" }, "Previous exports: ", exports.map(n => h("a", { href: "/api/exports/download/" + n, style: "margin-right:.75rem" }, n.replace(".zip", "")))) : null),
    h("h2", {}, `Recordings (${sources.length})`),
    sources.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Recording", "Speaker", "Dialect label", "Clips", "Permission and usage"].map(x => h("th", {}, x)))),
      h("tbody", {}, sources.map(s => h("tr", {}, h("td", {}, s.original_name, s.is_demo ? " " : "", s.is_demo ? chip("demo", "warn") : null), h("td", {}, s.speaker_id), h("td", {}, s.dialect_label), h("td", {}, s.clip_count), h("td", {}, permSel(s)))))))
      : h("p", { class: "muted" }, "No recordings yet."),
    h("h2", {}, `Clips (${clips.length})`), clipTable(clips));
}

// ---------- evaluation ----------
export async function renderEvaluation(main) {
  const runs = await api("/api/evaluations");
  const lang = h("input", { type: "text", id: "ev-lang", placeholder: "any", style: "width:8rem" });
  const syn = h("input", { type: "checkbox", id: "ev-syn", checked: state.mode === "demo", disabled: state.mode === "demo" });
  const out = h("div", {});
  const run = h("button", { class: "primary", onclick: () => guard(async () => {
    const r = await api("/api/evaluate", { method: "POST", json: { language_code: lang.value || null, include_synthetic: state.mode === "demo" ? true : syn.checked } });
    out.replaceChildren(evalView(r));
  }) }, "Run evaluation");
  main.replaceChildren(h("h1", {}, "Evaluation"),
    h("p", { class: "lede" }, "WER and CER against human-verified references, before and after accepted corrections. Samples where reference and hypothesis use different scripts are excluded rather than compared."),
    h("div", { class: "card" }, h("div", { class: "row" },
      h("div", {}, h("label", { for: "ev-lang" }, "Only transcripts requested with language code"), lang),
      h("div", {}, h("label", {}, syn, " Include synthetic/demo transcripts")), run)),
    out,
    runs.length ? h("p", { class: "hint" }, `${runs.length} earlier run(s) are stored. The latest is shown after you run again.`) : null);
  if (runs.length) out.replaceChildren(evalView(runs[0].results));
}
export function evalView(r) {
  const kids = [];
  r.warnings.forEach(w => kids.push(h("div", { class: "notice warn" }, w)));
  kids.push(h("p", {}, `Scored ${r.sample_count_scored} of ${r.sample_count_total} verified clip(s). `,
    Object.keys(r.excluded_by_reason).length ? "Excluded: " + Object.entries(r.excluded_by_reason).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join(", ") + ". " : "",
    Object.values(r.pre_scoring_skipped || {}).some(v => v) ? "Not considered: " + Object.entries(r.pre_scoring_skipped).filter(([, v]) => v).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join(", ") + "." : ""));
  const claims = r.claims || {};
  kids.push(h("div", { class: "notice warn" }, h("b", {}, "Ahirani performance claim: not allowed. "), claims.statement || ""));
  const groups = r.by_role || {};
  const roleOrder = Object.keys(groups);
  if (!roleOrder.length) kids.push(h("p", { class: "muted" }, "No scored samples."));
  for (const role of roleOrder) {
    const g = groups[role], a = g.aggregate;
    if (!a) continue;
    kids.push(h("div", { class: "card" },
      h("h2", {}, `${g.label} (n = ${a.n})`),
      g.language_codes_requested.length ? h("p", { class: "hint" }, "Baseline settings used: " + g.language_codes_requested.join(", ")) : null,
      h("table", {}, h("thead", {}, h("tr", {}, ["", "WER", "CER", "Word errors / reference words"].map(x => h("th", {}, x)))),
        h("tbody", {},
          h("tr", {}, h("td", {}, "Raw output"), h("td", {}, pct(a.before.wer)), h("td", {}, pct(a.before.cer)), h("td", {}, `${a.before.word_errors} / ${a.before.ref_words}`)),
          h("tr", {}, h("td", {}, "After accepted corrections"), h("td", {}, pct(a.after.wer)), h("td", {}, pct(a.after.cer)), h("td", {}, `${a.after.word_errors} / ${a.after.ref_words}`)),
          h("tr", {}, h("td", {}, "Change"), h("td", {}, pct(a.delta_wer)), h("td", {}, pct(a.delta_cer)), h("td", {}, `${a.samples_changed_by_corrections} clip(s) changed by corrections`)))),
      a.bootstrap_ci ? h("p", { class: "hint" }, `Bootstrap 95% interval for WER change: ${pct(a.bootstrap_ci.low)} to ${pct(a.bootstrap_ci.high)} (${a.bootstrap_ci.note})`) : h("p", { class: "hint" }, "Fewer than 10 scored clips: no confidence interval is computed."),
      h("p", { class: "hint" }, "Corpus-level rates (total errors ÷ total reference units); character error rate counts spaces.")));
  }
  kids.push(h("h2", {}, "Per-clip results"));
  kids.push(h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Clip", "Role", "Reference", "Raw", "Corrected", "WER before → after", "Notes"].map(x => h("th", {}, x)))),
    h("tbody", {}, r.samples.map(s => h("tr", {}, h("td", {}, short(s.clip_id), s.is_synthetic ? " " : "", s.is_synthetic ? chip("synthetic", "warn") : null),
      h("td", {}, chip(s.experiment_role === "baseline" ? "baseline" : s.experiment_role, s.experiment_role === "baseline" ? "warn" : "info"), s.language_code_requested ? h("div", { class: "hint" }, s.language_code_requested) : null),
      h("td", { class: "indic" }, s.reference), h("td", { class: "indic" }, s.raw), h("td", { class: "indic" }, s.corrected),
      h("td", {}, s.before ? `${pct(s.before.wer)} → ${pct(s.after.wer)}` : "not scored"),
      h("td", {}, s.excluded_reason ? chip(s.excluded_reason.replaceAll("_", " "), "bad") : null, ...s.warnings.map(w => h("div", { class: "hint" }, w)))))))));
  kids.push(h("details", {}, h("summary", {}, "Method and limitations"),
    h("h3", {}, "Normalization applied before scoring"), h("ul", {}, r.normalization.map(x => h("li", {}, x))),
    h("p", {}, r.script_policy), h("h3", {}, "Limitations"), h("ul", {}, r.limitations.map(x => h("li", {}, x)))));
  return h("div", {}, kids);
}

// ---------- about ----------
export async function renderAbout(main) {
  const a = state.about || await api("/api/about");
  const kind = { implemented: "ok", "implemented-needs-credentials": "info", "demo-only": "warn", "not-implemented": "bad" };
  main.replaceChildren(h("h1", {}, a.product.edition), h("p", { class: "lede" }, `${a.product.tagline} Current target: ${a.product.target_language}. Version ${a.product.version}, running in ${a.mode} mode.`),
    h("div", { class: "card" }, h("h2", {}, "What is real, demo, or missing"),
      h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Feature", "Status", "Notes"].map(x => h("th", {}, x)))),
        h("tbody", {}, a.capabilities.map(c => h("tr", {}, h("td", {}, c.feature), h("td", {}, chip(c.status.replaceAll("-", " "), kind[c.status])), h("td", {}, c.note))))))),
    h("div", { class: "card" }, h("h2", {}, "Known limitations"), h("ul", {}, a.limitations.map(l => h("li", {}, l)))));
}


export function refresh() { window.dispatchEvent(new Event("vaniq:refresh")); }
