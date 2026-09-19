// History: every saved version of a product or a document. Local saves are
// the versions the admin kept on this computer each time something was
// saved; committed versions come from the repository's history. A version is
// compared with today's side by side, and "Restore this version" saves it
// like any change: checked, rebuilt, and itself kept in History.
import { api, storeUrl } from "../lib/api.js";
import { h, clear, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, confirmDialog, toast, guard, announce } from "../lib/ui.js";

const SOURCE = { local: "Local save", git: "Committed" };

function when(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "";
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function bytes(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
  if (n >= 1024) return Math.round(n / 1024) + " KB";
  return n + " bytes";
}

// The editor a resource's own screen lives at, so History can link back.
function editorHref(kind, key) {
  if (kind === "products") return "#/products/" + key;
  return key === "settings" ? "#/settings" : "#/content/" + key;
}

export async function render(main, { sub, app }) {
  useCss("history");
  guard.clear();
  // #/history/products/be-mine, or with a version after it to open that one
  const parts = (sub || "").split("/").filter(Boolean);
  if (parts.length < 2) return landing(main, app);
  return timeline(main, app, parts[0], parts[1], parts[2]);
}

// ---- what to look at --------------------------------------------------------

async function landing(main, app) {
  const docs = Object.entries(app.state.schema.resources).filter(([, r]) => r.resource.kind === "document");
  const note = h("div", { class: "msgs" });
  const products = h("ul", { class: "hist-picks hist-products" }, h("li", { class: "muted" }, "Loading products"));
  const backupsCard = h("section", { class: "card" });
  let items = [];
  const search = h("input", { class: "input", type: "search", placeholder: "Search products", "aria-label": "Search products",
    oninput: () => drawProducts() });

  clear(main).append(
    h("div", { class: "page-head" }, h("div", {}, h("h1", { tabindex: "-1" }, "History"),
      h("p", { class: "sub" }, "Every version the admin saved on this computer, and every version committed to the repository. Pick what to look at."))),
    note,
    h("div", { class: "cards two" },
      h("section", { class: "card" }, h("h2", {}, "Pages and settings"),
        h("ul", { class: "hist-picks" }, docs.map(([name, r]) => h("li", {},
          h("a", { href: "#/history/documents/" + name }, icon("clock", 16), r.resource.label))))),
      backupsCard),
    h("section", { class: "card" }, h("h2", {}, "Products"),
      h("label", { class: "hist-search" }, icon("search", 16), search), products));

  function drawProducts() {
    const q = search.value.trim().toLowerCase();
    const list = items.filter((it) => !q || it.id.includes(q) || (it.data.name || "").toLowerCase().includes(q));
    clear(products);
    if (!list.length) { products.append(h("li", { class: "muted" }, "No products match.")); return; }
    list.forEach((it) => products.append(h("li", {}, h("a", { href: "#/history/products/" + it.id },
      icon("clock", 16), h("span", {}, it.data.name || it.id), h("small", {}, it.id),
      it.data.published === false ? h("span", { class: "badge muted" }, "Draft") : null))));
  }

  async function drawBackups() {
    clear(backupsCard).append(h("h2", {}, "Backups on this computer"));
    let st;
    try { st = await api("GET", "history/backups"); } catch (e) { backupsCard.append(banner({ tone: "critical", title: e.message })); return; }
    backupsCard.append(h("p", {}, st.files
      ? st.files + (st.files === 1 ? " saved version, " : " saved versions, ") + bytes(st.bytes) + " in all. The oldest is from " + when(st.oldest) + "."
      : "None yet. Every save keeps the version it replaced here."));
    if (!st.files) return;
    const days = h("input", { id: "hist-days", class: "input", type: "number", min: "1", max: "3650", step: "1", value: "90", inputmode: "numeric" });
    backupsCard.append(
      h("div", { class: "hist-prune" },
        h("div", { class: "field" }, h("label", { class: "f-label", for: "hist-days" }, "Remove backups older than (days)"), days),
        h("button", { class: "btn", type: "button", onclick: () => prune(Math.trunc(Number(days.value))) }, "Remove old backups")),
      h("p", { class: "help" }, "The newest " + st.keep_latest + " of each file are always kept. Nothing is removed unless you ask here."));
  }

  async function prune(n) {
    if (!(n >= 1 && n <= 3650)) { clear(note).append(banner({ tone: "critical", title: "Pick a number of days from 1 to 3650." })); return; }
    const ok = await confirmDialog({ title: "Remove old backups?", confirm: "Remove", danger: true,
      body: ["Backups older than " + n + " days are deleted from this computer for good, except the newest of each file. Committed versions are not affected."] });
    if (!ok) return;
    try {
      const res = await api("POST", "history/prune", { body: { days: n } });
      clear(note);
      toast(res.removed ? "Removed " + res.removed + (res.removed === 1 ? " backup." : " backups.") : "Nothing was old enough to remove.");
      drawBackups();
    } catch (e) {
      clear(note).append(banner({ tone: "critical", title: e.message }));
    }
  }

  drawBackups();
  try {
    const list = await api("GET", "products");
    app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
    items = list.items.slice().sort((a, b) => (a.data.name || a.id).localeCompare(b.data.name || b.id));
    drawProducts();
  } catch (e) {
    clear(products).append(h("li", {}, banner({ tone: "critical", title: e.message })));
  }
}

// ---- one product's or document's versions --------------------------------------

async function timeline(main, app, kind, key, first) {
  const resource = kind + "/" + key;
  const res = app.state.schema.resources[kind === "products" ? "products" : key];
  const fields = (res && res.fields) || [];
  const labelOf = (ptr) => (fields.find((f) => f.path === ptr) || {}).label || ptr.replace(/^\//, "");
  const head = h("div", { class: "page-head" });
  const msgs = h("div", { class: "msgs" });
  const listBox = h("div", { class: "hist-list" });
  const detail = h("div", { class: "hist-detail" });
  clear(main).append(head, msgs, h("div", { class: "hist-layout" }, listBox, detail));
  const buttons = new Map();
  let data = null;
  let picked = null;

  function drawHead() {
    const live = data && data.exists;
    clear(head).append(
      h("div", {},
        h("a", { class: "back", href: "#/history" }, "History"),
        h("h1", { tabindex: "-1" }, (data ? data.label : key) + " history"),
        h("p", { class: "sub" }, "Local saves are the versions kept on this computer each time something was saved. Committed versions come from the repository's history.")),
      h("div", { class: "head-actions" },
        live ? h("a", { class: "btn", href: editorHref(kind, key) }, "Open editor") : null,
        live && kind === "products" ? h("a", { class: "btn", href: storeUrl("product.html?p=" + encodeURIComponent(key)), target: "_blank", rel: "noopener noreferrer" },
          icon("external", 16), "View on store") : null));
  }

  function drawList() {
    buttons.clear();
    const card = h("section", { class: "card flush" }, h("h2", { class: "hist-list-title" }, "Versions"));
    clear(listBox).append(card);
    if (!data.items.length) card.append(h("p", { class: "empty" }, "No earlier versions yet. Every save from now on keeps the version it replaced."));
    else {
      card.append(h("ol", { class: "hist-items" }, data.items.map((it) => {
        const b = h("button", { type: "button", class: "hist-item", "aria-pressed": "false", onclick: () => pick(it) },
          h("span", { class: "hist-top" }, h("span", { class: "hist-when" }, when(it.at)),
            h("span", { class: "badge " + (it.source === "git" ? "gold" : "outline") }, SOURCE[it.source] || it.source)),
          it.subject ? h("span", { class: "hist-subject" }, it.subject) : null,
          h("span", { class: "hist-summary" }, (it.source === "local" ? "Kept when a save changed: " : "Changed: ") + it.summary));
        buttons.set(it.id, b);
        return h("li", {}, b);
      })));
    }
    if (data.more_local) card.append(h("p", { class: "hint" }, "Older saves on this computer are not listed."));
    if (data.git && !data.git.available) card.append(h("p", { class: "hint" }, "This copy of the shop is not a git checkout, so there are no committed versions."));
    if (data.git && data.git.error) card.append(h("p", { class: "hint" }, "Committed versions could not be read: " + data.git.error));
    mark();
  }

  function mark() {
    for (const [id, b] of buttons) {
      const on = !!picked && picked.id === id;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    }
  }

  function idle() {
    clear(detail).append(h("section", { class: "card" }, h("h2", {}, "Compare"),
      h("p", { class: "muted" }, data.items.length ? "Pick a version to compare it with the current one." : "There is nothing to compare yet.")));
  }

  async function pick(it) {
    picked = it;
    mark();
    clear(detail).append(h("section", { class: "card" }, h("p", { class: "muted" }, "Loading this version")));
    let v;
    try {
      v = await api("GET", "history/" + it.id + "?resource=" + encodeURIComponent(resource));
    } catch (e) {
      if (picked === it) clear(detail).append(banner({ tone: "critical", title: e.message }));
      return;
    }
    if (picked === it) drawDetail(it, v);      // unless a later pick replaced this one
  }

  const value = (s) => (s === "" ? h("span", { class: "muted" }, "Empty")
    : s === "not set" ? h("span", { class: "muted" }, "Not set") : h("span", { class: "hist-val" }, s));

  function drawDetail(it, v) {
    const title = it.source === "git" ? "Committed " + when(v.at) : "Before the save of " + when(v.at);
    const rows = v.diff || [];
    const table = rows.length
      ? h("div", { class: "table-wrap" }, h("table", { class: "table hist-diff" },
        h("caption", { class: "sr-only" }, "This version compared with the current one"),
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Field"), h("th", { scope: "col" }, "This version"), h("th", { scope: "col" }, "Now"))),
        h("tbody", {}, rows.map((e) => h("tr", {},
          h("th", { scope: "row" }, e.where && e.where !== data.label ? h("span", { class: "hist-where" }, e.where) : null, e.label),
          h("td", {}, value(e.before)), h("td", {}, value(e.after)))))))
      : h("p", { class: "muted" }, "This version is the same as the current one.");
    const can = !v.blocked && !v.same;
    clear(detail).append(h("section", { class: "card" },
      h("h2", {}, title),
      v.subject ? h("p", { class: "sub" }, v.subject) : null,
      v.blocked ? banner({ tone: "warning", title: "This version cannot be restored from here.", items: [v.blocked] }) : null,
      table,
      v.kept && v.kept.length ? h("div", { class: "hist-note" }, h("p", {}, "Restoring keeps these as they are now:"),
        h("ul", {}, v.kept.map((k) => h("li", {}, k.label + ". " + k.reason)))) : null,
      v.filled && v.filled.length ? h("p", { class: "help" }, "Not in this version, so they get today's value or the default: " + v.filled.map(labelOf).join(", ") + ".") : null,
      h("div", { class: "hist-actions" },
        h("button", { class: "btn primary", type: "button", disabled: !can, onclick: () => restore(it, v) }, "Restore this version"),
        rows.length && v.same && !v.blocked ? h("span", { class: "muted" }, "Restoring would change nothing: every difference is in something kept as it is now.") : null)));
    announce(title);
  }

  async function restore(it, v) {
    const changes = (v.changes || []).map((e) => e.text);
    const body = ["It is saved like any other change and the site rebuilds. The version it replaces stays in History, so this can be undone."];
    if (changes.length) body.push("What changes: " + changes.slice(0, 6).join("; ") + (changes.length > 6 ? "; and " + (changes.length - 6) + " more." : "."));
    if (v.guarded && v.guarded.length) body.push("This includes a change that asks first: " + v.guarded.map((g) => labelOf("/" + g)).join(", ") + ".");
    if (!(await confirmDialog({ title: "Restore this version?", body, confirm: "Restore" }))) return;
    clear(msgs);
    try {
      const res = await api("POST", "history/" + it.id + "/restore", { body: { resource, confirm_guarded: v.guarded || [] }, rev: v.current_rev });
      const secs = res.build && res.build.ms ? (res.build.ms / 1000).toFixed(1) : null;
      toast(secs ? "Restored. The site rebuilt in " + secs + " s." : "Restored.");
      if (res.kept && res.kept.length) msgs.append(banner({ tone: "info", title: "Restored. Kept as they are now:", items: res.kept.map((k) => k.label) }));
      if (res.warnings && res.warnings.length) msgs.append(banner({ tone: "warning", title: "Restored. Something to check:", items: res.warnings.map((w) => w.message) }));
      if (kind === "products" && app.state.products) app.state.products[key] = res.data;
      picked = null;
      await load();
    } catch (e) {
      failed(e, it);
    }
  }

  function failed(e, it) {
    if (e.code === "stale_rev") {
      msgs.append(banner({ tone: "warning", title: "This changed since you opened it, so nothing was restored.",
        items: ["The comparison now shows the current version. Check it and restore again if you still want to."] }));
      load(it.id);
    } else if (e.code === "validation") {
      const items = (Array.isArray(e.details) ? e.details : []).map((d) => (d.label ? d.label + ": " : "") + d.message);
      msgs.append(banner({ tone: "critical", title: e.message, items }));
    } else if (e.code === "build_failed") {
      msgs.append(banner({ tone: "critical", title: e.message, items: ((e.details && e.details.problems) || []).concat(["Everything was put back as it was."]) }));
    } else if (e.code === "busy") {
      toast("Another change is still saving. Try again in a moment.");
    } else {
      msgs.append(banner({ tone: "critical", title: e.message }));
    }
  }

  async function load(keep) {
    try {
      data = await api("GET", "history?resource=" + encodeURIComponent(resource));
    } catch (e) {
      data = null;
      drawHead();
      clear(listBox);
      clear(detail);
      msgs.append(banner({ tone: "critical", title: e.message }));
      return;
    }
    drawHead();
    drawList();
    const again = keep && data.items.find((i) => i.id === keep);
    if (again) pick(again);
    else idle();
  }

  await load(first);
}
