// Shared UI utilities for the VANIQ Studio: icons, modal dialogs, shared app context.
import { h } from "./legacy.js";

export const app = { view: "home", clipId: null, sourceId: null, clipLabel: "", sourceLabel: "" };

const P = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  studio: "M3 12h2M7 7v10M11 4v16M15 8v8M19 10v4M21 12h0",
  skills: "M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z",
  knowledge: "M4 4h12a4 4 0 014 4v12H8a4 4 0 01-4-4V4zM8 8h8M8 12h8",
  workflow: "M5 5h5v5H5zM14 14h5v5h-5zM10 7.5h4a2 2 0 012 2V14",
  lexicon: "M5 4h10a3 3 0 013 3v13H8a3 3 0 01-3-3V4zM9 9h5M9 13h5",
  dataset: "M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 7v5c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12v5c0 1.7 3.6 3 8 3s8-1.3 8-3v-5",
  eval: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  about: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v5M12 8h0",
  menu: "M4 6h16M4 12h16M4 18h16",
  play: "M7 4l13 8-13 8z", pause: "M8 4v16M16 4v16", loop: "M17 2l4 4-4 4M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 01-3 3H3",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16", send: "M4 12l16-8-6 16-2-7z", close: "M6 6l12 12M18 6L6 18",
  panel: "M4 5h16v14H4zM15 5v14", check: "M5 12l5 5 9-10", plus: "M12 5v14M5 12h14", mic: "M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3zM6 11a6 6 0 0012 0M12 17v4",
};
export function icon(name, size) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "icon"); svg.setAttribute("aria-hidden", "true");
  if (size) { svg.style.width = svg.style.height = size + "px"; }
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", P[name] || P.about); svg.append(p);
  return svg;
}

let activeDialog = null;
export function openDialog(title, body, opts = {}) {
  closeDialog();
  const prev = document.activeElement;
  const dlg = h("div", { class: "dialog" + (opts.palette ? " palette" : ""), role: "dialog", "aria-modal": "true", "aria-label": title, tabindex: "-1" });
  if (!opts.palette) dlg.append(h("div", { class: "row", style: "justify-content:space-between;align-items:center" }, h("h2", {}, title),
    h("button", { class: "btn ghost small", "aria-label": "Close dialog", onclick: () => closeDialog() }, icon("close"))));
  dlg.append(body);
  const scrim = h("div", { class: "scrim", onmousedown: e => { if (e.target === scrim) closeDialog(); } }, dlg);
  scrim.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.stopPropagation(); closeDialog(); }
    if (e.key === "Tab") {                                    // focus trap
      const f = [...dlg.querySelectorAll("button,input,select,textarea,a[href],[tabindex='0']")].filter(x => !x.disabled && x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.body.append(scrim);
  activeDialog = { scrim, prev };
  (dlg.querySelector("[autofocus],input,textarea,button") || dlg).focus();
  return dlg;
}
document.addEventListener("keydown", e => { if (e.key === "Escape" && activeDialog) { e.preventDefault(); closeDialog(); } });
export function closeDialog() {
  if (!activeDialog) return;
  activeDialog.scrim.remove();
  if (activeDialog.prev && activeDialog.prev.focus) activeDialog.prev.focus();
  activeDialog = null;
}
export const dialogOpen = () => !!activeDialog;
export const skeleton = (n = 4) => h("div", { class: "page", "aria-busy": "true", "aria-label": "Loading" }, Array.from({ length: n }, (_, i) => h("div", { class: "skeleton", style: `width:${90 - i * 12}%` })));
export function emptyState(title, text, action) {
  return h("div", { class: "empty" }, h("b", {}, title), text, action ? h("div", { style: "margin-top:10px" }, action) : null);
}
export function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return new Date(iso).toLocaleDateString();
}
