// Shared pieces: the contextual save bar, toasts, banners, dialogs, the
// screen-reader live region and the unsaved-changes guard.
import { h, clear } from "./dom.js";
import { icon } from "../icons.js";

// ---- live region -----------------------------------------------------------
let live;
export function announce(msg) {
  if (!live) return;
  live.textContent = "";
  setTimeout(() => { live.textContent = msg; }, 30);
}

// ---- unsaved changes -------------------------------------------------------
let dirtyFn = () => false;
export const guard = {
  set(fn) { dirtyFn = fn || (() => false); },
  dirty() { try { return !!dirtyFn(); } catch (e) { return false; } },
  clear() { dirtyFn = () => false; },
};

// ---- save bar ----------------------------------------------------------------
let bar;
export const savebar = {
  show({ onSave, onDiscard, message = "Unsaved changes" }) {
    if (!bar) return;
    clear(bar);
    const saveBtn = h("button", { class: "btn primary", type: "button", onclick: onSave }, "Save");
    bar.append(h("span", { class: "sb-msg" }, icon("alert", 16), message),
      h("span", { class: "sb-actions" },
        h("button", { class: "btn ghost-light", type: "button", onclick: onDiscard }, "Discard"), saveBtn));
    bar.hidden = false;
    document.body.classList.add("dirty");
  },
  busy(text) {
    if (!bar) return;
    clear(bar);
    bar.append(h("span", { class: "sb-msg" }, h("span", { class: "spinner", "aria-hidden": "true" }), text));
    bar.hidden = false;
    announce(text);
  },
  hide() {
    if (!bar) return;
    bar.hidden = true;
    clear(bar);
    document.body.classList.remove("dirty");
  },
};

// Cmd/Ctrl+S saves whatever screen has a save bar showing.
let saveHandler = null;
export function onSaveKey(fn) { saveHandler = fn; }

// ---- toasts ------------------------------------------------------------------
let toasts;
export function toast(msg, { action, tone } = {}) {
  if (!toasts) return;
  const t = h("div", { class: "toast" + (tone ? " " + tone : ""), role: "status" }, h("span", {}, msg));
  if (action) t.append(h("a", { href: action.href, target: action.external ? "_blank" : null, rel: action.external ? "noopener noreferrer" : null }, action.label));
  toasts.append(t);
  announce(msg);
  setTimeout(() => t.classList.add("out"), 5200);
  setTimeout(() => t.remove(), 5600);
}

// ---- banners -----------------------------------------------------------------
export function banner({ tone = "info", title, items = [], actions = [] }) {
  const el = h("div", { class: "banner " + tone, role: tone === "critical" ? "alert" : "status" },
    h("div", { class: "b-icon" }, icon(tone === "critical" || tone === "warning" ? "alert" : "check", 18)),
    h("div", { class: "b-body" },
      title ? h("p", { class: "b-title" }, title) : null,
      items.length ? h("ul", {}, items.map((i) => h("li", {}, i))) : null,
      actions.length ? h("p", { class: "b-actions" }, actions) : null));
  return el;
}

// ---- dialogs -----------------------------------------------------------------
function dialog(build) {
  return new Promise((resolve) => {
    const d = h("dialog", { class: "dlg" });
    const done = (v) => { d.close(); d.remove(); resolve(v); };
    d.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
    build(d, done);
    document.body.append(d);
    d.showModal();
    const first = d.querySelector("input, select, textarea, button.primary, button");
    if (first) first.focus();
  });
}

export function confirmDialog({ title, body, confirm = "OK", cancel = "Cancel", danger = false }) {
  return dialog((d, done) => {
    d.append(h("h2", {}, title),
      ...(Array.isArray(body) ? body : [body]).filter(Boolean).map((p) => h("p", {}, p)),
      h("div", { class: "dlg-actions" },
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, cancel),
        h("button", { class: "btn " + (danger ? "danger" : "primary"), type: "button", onclick: () => done(true) }, confirm)));
  }).then((v) => v === true);
}

export function choiceDialog({ title, body, choices }) {
  return dialog((d, done) => {
    d.append(h("h2", {}, title), ...(Array.isArray(body) ? body : [body]).filter(Boolean).map((p) => h("p", {}, p)),
      h("div", { class: "dlg-actions" }, choices.map((c) =>
        h("button", { class: "btn " + (c.primary ? "primary" : ""), type: "button", onclick: () => done(c.value) }, c.label))));
  });
}

export function formDialog({ title, body, fields, confirm = "Create" }) {
  return dialog((d, done) => {
    const inputs = {};
    const form = h("form", { class: "dlg-form", onsubmit: (e) => { e.preventDefault(); const out = {}; for (const [k, el] of Object.entries(inputs)) out[k] = el.value.trim(); done(out); } });
    for (const f of fields) {
      const id = "dlg-" + f.name;
      const input = f.options
        ? h("select", { id, class: "input" }, f.options.map((o) => h("option", { value: o.value, selected: o.value === f.value }, o.label)))
        : h("input", { id, class: "input", value: f.value || "", placeholder: f.placeholder || "", required: f.required ? true : null, pattern: f.pattern || null, autocomplete: "off" });
      inputs[f.name] = input;
      form.append(h("div", { class: "field" }, h("label", { for: id }, f.label), input, f.hint ? h("p", { class: "help" }, f.hint) : null));
    }
    form.append(h("div", { class: "dlg-actions" },
      h("button", { class: "btn", type: "button", onclick: () => done(null) }, "Cancel"),
      h("button", { class: "btn primary", type: "submit" }, confirm)));
    d.append(h("h2", {}, title), body ? h("p", {}, body) : null, form);
  });
}

// ---- mounting ----------------------------------------------------------------
export function mountChrome(root) {
  bar = h("div", { class: "savebar", role: "region", "aria-label": "Unsaved changes", hidden: true });
  toasts = h("div", { class: "toasts" });
  live = h("div", { class: "sr-only", "aria-live": "polite" });
  root.append(bar, toasts, live);
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s" && !bar.hidden && saveHandler) {
      e.preventDefault();
      saveHandler();
    }
  });
}
