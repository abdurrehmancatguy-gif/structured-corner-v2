// Import and export: the catalogue, or the products a filter picks, as a CSV
// file a spreadsheet opens; and a CSV file checked row by row on the server
// before anything changes, then applied in one save, or dropped.
import { api, download } from "../lib/api.js";
import { h, clear, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast, confirmDialog, guard, announce } from "../lib/ui.js";
import { categories, productField, failure, builtIn, plural } from "../lib/bulk.js";

// The server's cap on the file's text (csvio.MAX_BYTES), checked here first
// so a file that large is not read into the page for nothing.
const MAX_BYTES = 5 * 1024 * 1024;
const ACTIONS = { create: "To create", update: "To change", unchanged: "Unchanged", error: "Errors" };
const BADGES = { create: ["gold", "New"], update: ["green", "Changes"], unchanged: ["", "Unchanged"], error: ["red", "Error"] };

function readText(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(file, "utf-8");
  });
}

// A CSV cell as the check reports it: empty cells say so, and the TRUE and
// FALSE of a yes-or-no column read as on and off.
const word = (v) => (v === "TRUE" ? "on" : v === "FALSE" ? "off" : v);
const cellText = (v) => (v === "" || v === null || v === undefined ? h("span", { class: "muted" }, "empty") : String(v));

export async function render(main, { app }) {
  useCss("import");
  guard.clear();
  const cats = categories(app);
  const f = { q: "", category: "", status: "" };
  let items = [];
  let text = "", fileName = "";
  let plan = null;       // the server's check, kept until it is applied or dropped
  let only = "all";      // which rows of the check the table shows
  const note = h("div", { class: "msgs" });
  const count = h("p", { class: "imp-count", role: "status" });
  const exportThese = h("button", { class: "btn", type: "button", disabled: true,
    onclick: () => exportIds(matching().map((it) => it.id)) }, "Export these");
  const steps = h("ol", { class: "imp-steps", "aria-label": "Import steps" });
  const body = h("div", { class: "imp-body" });
  const filter = (k) => (e) => { f[k] = k === "q" ? e.target.value.trim().toLowerCase() : e.target.value; drawCount(); };

  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("a", { class: "back", href: "#/products" }, "Products"),
      h("h1", { tabindex: "-1" }, "Import and export"),
      h("p", { class: "sub" }, "Products as a CSV file, one row per product. An import is checked first and changes nothing until you apply it."))),
    note,
    h("section", { class: "card flush", "aria-labelledby": "imp-export" },
      h("div", { class: "imp-head" }, h("h2", { id: "imp-export" }, "Export"),
        h("p", { class: "sub" }, "The file has the columns the import reads, so an exported file can be edited in a spreadsheet and imported again.")),
      h("div", { class: "toolbar" },
        h("label", { class: "search" }, icon("search", 16),
          h("input", { class: "input", type: "search", placeholder: "Search products", "aria-label": "Search products", oninput: filter("q") })),
        h("select", { class: "input", "aria-label": "Category", onchange: filter("category") },
          h("option", { value: "" }, "All categories"), Object.entries(cats).map(([k, v]) => h("option", { value: k }, v))),
        h("select", { class: "input", "aria-label": "Status", onchange: filter("status") },
          h("option", { value: "" }, "Active and draft"), h("option", { value: "active" }, "Active"), h("option", { value: "draft" }, "Draft"))),
      h("div", { class: "imp-actions" }, count,
        h("button", { class: "btn", type: "button", onclick: () => exportIds(null) }, "Export all products"), exportThese)),
    h("section", { class: "card", "aria-labelledby": "imp-import" },
      h("h2", { id: "imp-import" }, "Import"), steps, body));

  function matching() {
    return items.filter(({ id, data: d }) => {
      const active = d.published !== false;
      if (f.category && d.category !== f.category) return false;
      if (f.status === "active" && !active) return false;
      if (f.status === "draft" && active) return false;
      if (f.q && !id.includes(f.q) && !(d.name || "").toLowerCase().includes(f.q)) return false;
      return true;
    });
  }

  function drawCount() {
    const n = matching().length;
    const filtered = !!(f.q || f.category || f.status);
    count.textContent = filtered ? n + " of " + plural(items.length, "product") + " match." : plural(items.length, "product") + " in all.";
    exportThese.disabled = !filtered || !n;
    exportThese.textContent = filtered && n ? "Export these " + n : "Export these";
  }

  async function exportIds(ids) {
    clear(note);
    try {
      await download("products/export.csv" + (ids ? "?ids=" + ids.map(encodeURIComponent).join(",") : ""), "bgs-products.csv");
      toast("Exported " + plural(ids ? ids.length : items.length, "product") + ".");
    } catch (e) {
      const b = failure(e);
      if (b) note.append(b);
    }
  }

  function drawSteps(n) {
    clear(steps).append(...["Choose a file", "Review the check", "Apply or cancel"].map((t, i) =>
      h("li", { class: i + 1 === n ? "on" : i + 1 < n ? "done" : null, "aria-current": i + 1 === n ? "step" : null }, t)));
  }

  // Step one. Dropping a check keeps the file's text, so "Check the file
  // again" after an expired or outdated check needs no second pick.
  function drawChoose() {
    plan = null;
    guard.clear();
    drawSteps(1);
    clear(body).append(h("div", { class: "field" },
      h("label", { class: "f-label", for: "imp-file" }, "CSV file"),
      h("input", { type: "file", id: "imp-file", class: "imp-file", accept: ".csv,text/csv", "aria-describedby": "imp-file-help", onchange: pick }),
      h("p", { class: "help", id: "imp-file-help" },
        "A file exported here and edited in a spreadsheet, saved as CSV (UTF-8). Columns the file leaves out keep their values. ",
        "A row with a new handle adds a product at the end of the list, as a draft unless its Status says active.")));
  }

  async function pick(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    clear(note);
    if (file.size > MAX_BYTES) {
      note.append(banner({ tone: "critical", title: "This file is larger than " + MAX_BYTES / (1024 * 1024) + " MB, the most one import takes.",
        items: ["Split it into smaller files and import them one at a time."] }));
      e.target.value = "";
      return;
    }
    try {
      text = await readText(file);
      fileName = file.name;
    } catch (err) {
      note.append(banner({ tone: "critical", title: "The file could not be read. Choose it again." }));
      e.target.value = "";
      return;
    }
    await check();
  }

  const summary = (c) => [c.create + " to create", c.update + " to change", c.unchanged + " unchanged", plural(c.error, "error")].join(", ");
  const todoOf = (c) => c.create + c.update;
  const guardedLabels = (needs) => [...new Set(Object.values(needs).flat())].map((k) => productField(app, "/" + k).label).join(" and ");
  const nameOf = (id) => { const it = items.find((x) => x.id === id); return (it && it.data.name) || id; };
  // Yes-or-no columns hold TRUE and FALSE in the file; they read as on and off.
  const boolCols = new Set(app.state.schema.resources.products.fields.filter((x) => x.type === "bool").map((x) => x.label));
  const shownCell = (field, v) => cellText(boolCols.has(field) ? word(v) : v);

  // Step two: the server checks the file against the shop and keeps the
  // result as a plan; nothing is written until it is applied.
  async function check() {
    clear(note);
    drawSteps(2);
    clear(body).append(h("p", { class: "muted", role: "status" }, "Checking " + fileName + " against the shop."));
    try {
      plan = await api("POST", "products/import", { body: { csv: text, mode: "dry-run" } });
    } catch (e) {
      drawChoose();
      const b = e.code === "bad_csv" || e.code === "too_large"
        ? banner({ tone: "critical", title: "This file cannot be imported.", items: [e.message] }) : failure(e);
      if (b) note.append(b);
      return;
    }
    only = plan.counts.error ? "error" : "all";
    guard.set(() => !!plan && todoOf(plan.counts) > 0);
    drawPlan();
    announce("Checked " + fileName + ": " + summary(plan.counts) + ".");
  }

  function drawPlan() {
    const c = plan.counts;
    const todo = todoOf(c);
    const ready = todo > 0 && !c.error;
    drawSteps(ready ? 3 : 2);
    const out = [h("p", { class: "imp-checked" }, "Checked ", h("b", {}, fileName), ": " + summary(c) + ".")];
    if (c.error) {
      out.push(banner({ tone: "critical", title: plural(c.error, "row has", "rows have") + " errors, so this file cannot be applied.",
        items: ["Fix those rows in the file, then choose it again. Nothing has changed."] }));
    } else if (!todo) {
      out.push(banner({ tone: "info", title: "Nothing to apply: every row matches the shop as it is." }));
    }
    if ((plan.ignored_columns || []).length) {
      out.push(banner({ tone: "info", title: "These columns are not ones the import reads, so they were left out:", items: plan.ignored_columns }));
    }
    const needs = plan.needs_confirm || {};
    if (Object.keys(needs).length && ready) {
      out.push(banner({ tone: "warning", title: guardedLabels(needs) + " changes for " + plural(Object.keys(needs).length, "product") + ".",
        items: ["You are asked to confirm them on their own before anything is applied."] }));
    }
    out.push(h("div", { class: "imp-filters", role: "group", "aria-label": "Show rows" },
      [["all", "All", plan.rows.length]].concat(Object.entries(ACTIONS).map(([k, l]) => [k, l, c[k]])).map(([k, l, n]) =>
        h("button", { class: "btn small", type: "button", "aria-pressed": only === k ? "true" : "false",
          onclick: () => { only = k; drawPlan(); const on = body.querySelector('.imp-filters [aria-pressed="true"]'); if (on) on.focus(); } },
        l + " " + n))));
    const list = plan.rows.filter((r) => only === "all" || r.action === only);
    out.push(list.length ? h("div", { class: "table-wrap" }, h("table", { class: "table imp-table" },
      h("thead", {}, h("tr", {}, ["Line", "Handle", "Result", "What the row does"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, list.map(rowView)))) : h("p", { class: "empty" }, "No rows here."));
    const parts = [];
    if (c.create) parts.push("creates " + plural(c.create, "product"));
    if (c.update) parts.push("changes " + plural(c.update, "product"));
    const minutes = Math.floor((plan.expires_in || 0) / 60);
    out.push(h("div", { class: "imp-apply" },
      h("p", { class: "help" }, ready
        ? "Applying " + parts.join(" and ") + " in one save, and the site rebuilds once. If any product fails, nothing changes."
          + (minutes ? " This check is kept for " + minutes + " minutes." : "")
        : c.error ? "Nothing changes until the file checks without errors." : "Nothing will change."),
      h("div", { class: "head-actions" },
        h("button", { class: "btn", type: "button", onclick: cancel }, ready ? "Cancel" : "Choose another file"),
        ready ? h("button", { class: "btn primary", type: "button", onclick: apply }, "Apply to " + plural(todo, "product")) : null)));
    clear(body).append(...out);
  }

  function rowView(r) {
    const [tone, label] = BADGES[r.action] || ["", r.action];
    const known = items.some((it) => it.id === r.id);
    return h("tr", {},
      h("td", { class: "num" }, String(r.line)),
      h("td", {}, known ? h("a", { href: "#/products/" + r.id, class: "t-name" }, r.id) : h("span", { class: "t-name" }, r.id || "No handle")),
      h("td", {}, h("span", { class: "badge " + tone }, label), " ", r.confirm ? h("span", { class: "badge gold" }, "Asks first") : null),
      h("td", {}, details(r)));
  }

  function details(r) {
    const out = [];
    const item = (x) => h("li", {}, x.column ? h("b", {}, x.column + ": ") : null, x.message);
    if (r.errors.length) out.push(h("ul", { class: "imp-errors" }, r.errors.map(item)));
    if (r.changes.length) {
      out.push(h("table", { class: "imp-changes" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Column"), h("th", { scope: "col" }, "Before"), h("th", { scope: "col" }, "After"))),
        h("tbody", {}, r.changes.map((x) => h("tr", {},
          h("th", { scope: "row" }, x.field), h("td", {}, shownCell(x.field, x.before)), h("td", {}, shownCell(x.field, x.after)))))));
    }
    if (r.warnings.length) out.push(h("ul", { class: "imp-warnings" }, r.warnings.map(item)));
    if (!out.length) out.push(h("span", { class: "muted" }, r.action === "unchanged" ? "Same as the shop." : "Nothing to show."));
    return out;
  }

  // Step three. Never discounted changes (the guarded fields) get their own
  // confirmation first, product by product, before the plan is applied.
  async function apply() {
    const needs = plan.needs_confirm || {};
    const ids = Object.keys(needs);
    if (ids.length) {
      const keys = [...new Set(Object.values(needs).flat())];
      const lines = ids.map((id) => {
        const row = plan.rows.find((r) => r.id === id && r.action !== "error");
        return nameOf(id) + ": " + needs[id].map((k) => {
          const label = productField(app, "/" + k).label;
          const ch = row && row.changes.find((x) => x.field === label);
          return label + (ch ? (ch.before ? " from " + word(ch.before) + " to " : " ") + word(ch.after) : " changes");
        }).join(", ");
      });
      const ok = await confirmDialog({ title: "Confirm " + guardedLabels(needs) + " for " + plural(ids.length, "product"),
        body: keys.map((k) => productField(app, "/" + k).help).filter(Boolean).concat(lines), confirm: "Confirm", cancel: "Back to the check" });
      if (!ok) return;
    }
    body.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    clear(note).append(h("p", { class: "muted", role: "status" }, "Applying and rebuilding the site."));
    try {
      const res = await api("POST", "products/import", { body: { plan_id: plan.plan_id, mode: "apply", confirm_guarded: needs } });
      applied(res);
    } catch (e) {
      clear(note);
      applyFailed(e);
    }
  }

  function applied(res) {
    const created = res.created || [], updated = res.updated || [];
    const said = [created.length ? plural(created.length, "product") + " created" : "",
      updated.length ? plural(updated.length, "product") + " changed" : ""].filter(Boolean).join(" and ");
    text = "";
    drawChoose();
    clear(note).append(banner({ tone: "info", title: "Imported: " + said + "." + builtIn(res),
      items: created.length ? [h("span", {}, "New: ", created.map((id, i) => [i ? ", " : "", h("a", { href: "#/products/" + id }, id)]))] : [] }));
    toast("Imported." + builtIn(res));
    app.state.products = null;
    loadItems();
  }

  function applyFailed(e) {
    if (e.code === "plan_not_found" || e.code === "stale_rev") {
      drawChoose();
      note.append(banner({ tone: "warning",
        title: e.code === "stale_rev" ? "Products changed since the file was checked." : "That check has expired or was already applied.",
        items: ["This import applied nothing. Check the file again to see what it would do to the shop as it is now."],
        actions: [h("button", { class: "btn", type: "button", onclick: check }, "Check the file again")] }));
      return;
    }
    drawPlan();
    let b;
    if (e.code === "build_failed") {
      b = banner({ tone: "critical", title: "Not imported: the site would not build with these changes.",
        items: ((e.details && e.details.problems) || []).concat(["Everything was put back as it was."]) });
    } else if (e.code === "plan_has_errors" || e.code === "guarded_field") {
      b = banner({ tone: "critical", title: e.message });
    } else {
      b = failure(e);
    }
    if (b) note.append(b);
  }

  function cancel() {
    const had = !!plan && todoOf(plan.counts) > 0;
    text = "";
    clear(note);
    drawChoose();
    announce(had ? "Import cancelled. Nothing changed." : "Choose a file to import.");
    const input = body.querySelector("#imp-file");
    if (input) input.focus();
  }

  async function loadItems() {
    try {
      const list = await api("GET", "products");
      items = list.items;
      app.state.products = Object.fromEntries(items.map((it) => [it.id, it.data]));
      drawCount();
    } catch (e) {
      note.append(banner({ tone: "critical", title: e.message }));
    }
  }

  drawChoose();
  await loadItems();
}
