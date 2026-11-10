// Knowledge: human-written, versioned, human-approved project conventions and references (Lindy memory pattern).
import { api, chip, guard, h, requireReviewer, reviewer, toast } from "./legacy.js";
import { emptyState, timeAgo } from "./ui.js";

export async function renderKnowledge(root) {
  let items = await api("/api/knowledge");
  let selId = items.length ? items[0].id : "new";
  const page = h("div", { class: "page" }, h("h1", {}, "Knowledge"),
    h("p", { class: "lede" }, "Project conventions and linguistic references written and approved by people. VANIQ ships none of its own and never invents Ahirani vocabulary or rules. The agent reads only approved entries and cannot create or approve them. Editing an approved entry returns it to draft."));
  const list = h("div", { class: "kn-list" }), editor = h("div", {});
  page.append(h("div", { class: "kn" }, h("div", {}, h("button", { class: "btn primary", style: "width:100%;margin-bottom:8px", onclick: () => { selId = "new"; paint(); } }, "New entry"), list), editor));
  root.replaceChildren(page);

  async function reload(keep) { items = await api("/api/knowledge"); if (keep !== undefined) selId = keep; paint(); }
  function paint() {
    list.replaceChildren(...(items.length ? items.map(i => h("button", { class: "kn-item" + (i.id === selId ? " active" : ""), onclick: () => { selId = i.id; paint(); } },
      h("div", {}, h("b", {}, i.title)), h("div", { class: "hint" }, i.kind, " · v", i.version, " · ", chip(i.status, i.status === "approved" ? "ok" : "warn"))))
      : [emptyState("No entries", "Write the first convention, e.g. how your team spells and documents Ahirani.")]));
    editor.replaceChildren(selId === "new" || !items.find(i => i.id === selId) ? form(null) : form(items.find(i => i.id === selId)));
  }
  function form(item) {
    const title = h("input", { type: "text", value: item ? item.title : "", maxlength: "200", "aria-label": "Title", style: "width:100%" });
    const kind = h("select", { disabled: !!item, "aria-label": "Kind" }, ["convention", "reference", "note"].map(k => h("option", { value: k, selected: item && item.kind === k }, k)));
    const body = h("textarea", { "aria-label": "Body", style: "min-height:220px" }, item ? item.body : "");
    const prov = h("input", { type: "text", value: item ? item.provenance : "", placeholder: "e.g. written by you, or the source document", "aria-label": "Provenance", style: "width:100%", disabled: !!item });
    const versions = h("div", {});
    const save = h("button", { class: "btn primary", onclick: () => guard(async () => {
      if (!requireReviewer()) return;
      const r = item ? await api("/api/knowledge/" + item.id, { method: "PUT", json: { title: title.value, body: body.value, reviewer: reviewer() } })
        : await api("/api/knowledge", { method: "POST", json: { title: title.value, kind: kind.value, body: body.value, provenance: prov.value, reviewer: reviewer() } });
      toast(item ? "New version saved (as draft)" : "Draft created"); await reload(r.id);
    }) }, item ? "Save as new version" : "Create draft");
    const approve = item && item.status === "draft" ? h("button", { class: "btn ok", onclick: () => guard(async () => {
      if (!requireReviewer()) return; await api(`/api/knowledge/${item.id}/approve`, { method: "POST", json: { reviewer: reviewer() } }); toast("Approved"); await reload(item.id);
    }) }, "Approve (visible to the agent)") : null;
    const del = item ? h("button", { class: "btn danger", onclick: () => guard(async () => {
      if (!requireReviewer() || !confirm("Delete this entry and its history?")) return;
      await api(`/api/knowledge/${item.id}?reviewer=${encodeURIComponent(reviewer())}`, { method: "DELETE" }); await reload(null);
    }) }, "Delete") : null;
    if (item) api(`/api/knowledge/${item.id}/versions`).then(vs => versions.replaceChildren(h("h3", {}, "Version history"),
      ...vs.map(v => h("div", { class: "row", style: "align-items:center;margin-bottom:4px" }, h("span", { class: "chip" }, "v" + v.version), h("span", { class: "hint" }, `${v.edited_by} · ${timeAgo(v.edited_at)}`),
        v.version !== item.version ? h("button", { class: "btn small", onclick: () => guard(async () => { if (!requireReviewer()) return; await api(`/api/knowledge/${item.id}/restore`, { method: "POST", json: { version: v.version, reviewer: reviewer() } }); toast("Restored as a new draft version"); await reload(item.id); }) }, "Restore") : h("span", { class: "hint" }, "current")))));
    return h("div", { class: "card" },
      item ? h("div", { class: "row", style: "align-items:center" }, chip(item.status, item.status === "approved" ? "ok" : "warn"), h("span", { class: "hint" }, item.status === "approved" ? `Approved by ${item.approved_by}` : "Draft: not visible to the agent"), h("span", { class: "hint" }, "· ", item.provenance)) : h("h2", {}, "New entry"),
      h("div", { class: "field", style: "margin-top:8px" }, h("label", {}, "Title"), title), item ? null : h("div", { class: "grid2" }, h("div", {}, h("label", {}, "Kind"), kind), h("div", {}, h("label", {}, "Provenance"), prov)),
      h("div", { class: "field", style: "margin-top:8px" }, h("label", {}, "Body (plain text)"), body),
      h("div", { class: "row" }, save, approve, del), versions);
  }
  paint();
}
