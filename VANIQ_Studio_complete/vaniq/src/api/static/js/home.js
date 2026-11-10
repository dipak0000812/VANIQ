// Home: Lindy-pattern agent workspace (composer, thread, plan/approval cards, activity).
import { api, h, state, short } from "./legacy.js";
import { composer, mountThread, modeNote, askAgent } from "./agent.js";
import { emptyState, timeAgo } from "./ui.js";

const SUGGEST = ["What needs doing?", "Check dataset eligibility", "Validate audio", "Who needs a human reference?", "Run evaluation", "Run baseline mr-IN on all untranscribed clips"];

export async function renderHome(root) {
  const [dash, status] = await Promise.all([api("/api/dashboard"), api("/api/agent/status")]);
  const c = dash.counts;
  const hr = new Date().getHours();
  const greeting = hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
  const comp = composer();
  const threadBox = h("div", { class: "thread", "aria-live": "polite" });
  const page = h("div", { class: "home" });
  const main = h("div", {},
    h("div", { class: "greet" }, h("h1", {}, `${greeting}.`), h("p", { class: "lede" }, "VANIQ is a voice-data workspace for underrepresented languages, starting with Ahirani. Ask it to prepare work, check data, or run baselines. It does the lookups and waits for your approval on anything with outside impact.")),
    comp.el,
    h("div", { class: "suggest" }, SUGGEST.map(s => h("button", { onclick: () => askAgent(s, false) }, s))),
    status.llm_available ? null : modeNote(), threadBox);
  const side = h("aside", {}, h("h2", { style: "margin-top:0" }, "Workspace"),
    h("dl", { class: "kv" }, ...[["Recordings", c.sources], ["Clips", c.clips], ["Transcripts", c.transcripts + c.synthetic_transcripts], ["Corrections pending", c.pending_suggestions],
      ["Human-verified", c.verified_clips], ["Lexicon entries", c.lexicon_entries]].flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, String(v))])),
    c.unknown_permission_clips ? h("div", { class: "notice", style: "margin-top:12px" }, `${c.unknown_permission_clips} clip(s) have unknown or incomplete permission and are excluded from public exports.`) : null,
    state.mode === "live" && !state.sttConfigured ? h("div", { class: "notice warn", style: "margin-top:12px" }, "No STT provider configured. Baseline runs will fail honestly until GNANI_API_KEY is set.") : null,
    c.sources === 0 && state.mode === "demo" ? h("button", { class: "btn primary", style: "margin-top:12px", onclick: async () => { await api("/api/demo/seed", { method: "POST" }); window.dispatchEvent(new Event("vaniq:refresh")); } }, "Load demo data") : null,
    h("h2", {}, "Activity"),
    dash.audit.length ? h("div", { class: "feed" }, dash.audit.slice(0, 8).map(a => h("div", { class: "it" }, `${a.action.replaceAll("_", " ")}`, h("small", {}, `${a.actor} · ${timeAgo(a.ts)} · ${short(a.entity_id)}`))))
      : emptyState("No activity yet", "Decisions, approvals and runs appear here."));
  page.append(main, side);
  root.replaceChildren(page);
  mountThread(threadBox);
}
