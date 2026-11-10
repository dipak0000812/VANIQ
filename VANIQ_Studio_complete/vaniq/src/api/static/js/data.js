// Lexicon, Datasets, Evaluation, About inside the Studio shell (ported views) + live export eligibility.
import { api, chip, guard, h, renderAbout, renderDatasets as legacyDatasets, renderEvaluation, renderLexicon, short } from "./legacy.js";

const REASON = { permission_unknown: "permission or permitted usage unknown", permission_denied: "permission denied", usage_not_public: "usage is not public release",
  not_verified: "no human-verified reference", rejected_clip: "clip marked unusable" };

async function wrap(root, fn) {
  const box = h("div", { class: "page" });
  root.replaceChildren(box);
  await fn(box);
  return box;
}
export const renderLexiconView = (root) => wrap(root, renderLexicon);
export const renderEvaluationView = (root) => wrap(root, renderEvaluation);
export const renderAboutView = (root) => wrap(root, renderAbout);

export async function renderDatasets(root) {
  const box = await wrap(root, legacyDatasets);
  const vis = h("select", { id: "el-vis", "aria-label": "Export visibility" }, [["public", "Public"], ["internal", "Internal"]].map(([v, t]) => h("option", { value: v }, t)));
  const unk = h("input", { type: "checkbox", id: "el-unk" });
  const unkRow = h("label", { for: "el-unk", style: "display:none;margin:0" }, unk, " include unknown-permission clips (internal only)");
  const out = h("div", {});
  async function paint() {
    unkRow.style.display = vis.value === "internal" ? "flex" : "none";
    if (vis.value !== "internal") unk.checked = false;
    const r = await guard(() => api(`/api/datasets/eligibility?visibility=${vis.value}&include_unknown_internal=${unk.checked}`));
    if (!r) return;
    out.replaceChildren(
      h("p", {}, h("b", {}, `${r.eligible_count} of ${r.total_clips}`), ` clip(s) eligible for a ${r.visibility} export. `,
        Object.entries(r.excluded_by_reason).map(([k, v]) => chip(`${v} ${REASON[k] || k}`, "warn")).flatMap(c => [c, " "])),
      r.total_clips ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Clip", "Recording", "Eligible", "Reason"].map(x => h("th", {}, x)))),
        h("tbody", {}, r.clips.map(c => h("tr", {}, h("td", {}, h("a", { href: "#/studio/" + c.clip_id }, short(c.clip_id))), h("td", {}, c.source_name),
          h("td", {}, chip(c.eligible ? "yes" : "no", c.eligible ? "ok" : "bad")), h("td", {}, c.reason ? (REASON[c.reason] || c.reason) : ""))))))
        : h("p", { class: "muted" }, "No clips yet."));
  }
  vis.addEventListener("change", paint); unk.addEventListener("change", paint);
  const card = h("div", { class: "card" }, h("h2", {}, "Eligibility"),
    h("p", { class: "hint" }, "Computed by the same server-side rules the export uses. Unknown or denied permissions are never eligible for a public export."),
    h("div", { class: "row" }, h("div", {}, h("label", { for: "el-vis" }, "Visibility"), vis), unkRow), out);
  const first = box.querySelector(".card");
  first ? first.before(card) : box.append(card);
  await paint();
}
