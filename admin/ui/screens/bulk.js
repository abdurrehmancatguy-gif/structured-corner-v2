// The bulk editor: the products in one grid, edited like a spreadsheet and
// saved together through products/bulk, all or nothing. Arrow keys move,
// Enter or F2 edits, Tab goes to the next cell, Esc puts a cell back, Cmd or
// Ctrl+Z steps back, and a block copied from a spreadsheet pastes from the
// cell in focus. Each cell is checked as it lands; the server checks again.
import { api } from "../lib/api.js";
import { h, clear, copy, same, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast, savebar, guard, onSaveKey, announce } from "../lib/ui.js";
import { categories, productField, textProblem, saveProducts, failure, builtIn, plural, warningsBanner } from "../lib/bulk.js";

const UNDO_STEPS = 200;

// Tab-separated text as spreadsheets put it on the clipboard: a cell holding
// a tab, a line break or a quote comes wrapped in quotes, with quotes doubled.
export function parseTsv(text) {
  const out = [];
  let row = [], cell = "", quoted = false;
  const s = String(text).replace(/\r\n?/g, "\n");
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (quoted) {
      if (ch !== '"') cell += ch;
      else if (s[i + 1] === '"') { cell += '"'; i++; }
      else quoted = false;
    } else if (ch === '"' && cell === "") quoted = true;
    else if (ch === "\t") { row.push(cell); cell = ""; }
    else if (ch === "\n") { row.push(cell); out.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); out.push(row); }
  return out;
}

export async function render(main, { app }) {
  useCss("bulk");
  const cats = categories(app);
  const F = (p) => productField(app, p);
  let rows = [];        // every product: {id, rev, data, edits: {key: record}, server: {key: message}, stale}
  let shown = [];       // the rows the filter lets through, in the grid's order
  let cols = [];
  let cells = [];       // cells[r][c]: the grid's cell elements, for the rows shown
  let at = { r: 0, c: 0 };
  let editing = null;   // {row, col, el, input} while a cell's editor is open
  const undo = [], redo = [];
  const f = { q: "", category: "" };

  // The columns. Category and position are shown, not edited: the category
  // decides which fields a product has, and the position follows the schema,
  // which keeps it read-only while reordering is the way to move a product.
  function columns(sizes) {
    const name = F("/name"), price = F("/price"), stock = F("/stock"), order = F("/order");
    const sizePrice = (F("/sizes").fields || []).find((x) => x.path === "/price") || price;
    const out = [
      { key: "name", label: name.label, kind: "text", field: name, get: (d) => d.name || "", put: (d, v) => { d.name = v; } },
      { key: "published", label: "Status", kind: "status", get: (d) => d.published !== false, put: (d, v) => { d.published = v; } },
      { key: "category", label: F("/category").label, kind: "fixed", get: (d) => d.category, text: (v) => cats[v] || v,
        why: "Change the category on the product page: it decides which fields the product has." },
      { key: "price", label: price.label, kind: "money", field: price, get: (d) => d.price, put: (d, v) => { d.price = v; } },
    ];
    for (let i = 0; i < sizes; i++) {
      out.push({ key: "size" + i, label: "Size " + (i + 1) + " (AED)", kind: "money", field: sizePrice,
        applies: (d) => d.category === "attars" && Array.isArray(d.sizes) && i < d.sizes.length,
        why: "Only attars have sizes. Add or remove sizes on the product page.",
        get: (d) => d.sizes[i].price, put: (d, v) => { d.sizes[i].price = v; }, note: (d) => d.sizes[i].label });
    }
    out.push({ key: "stock", label: stock.label, kind: "stock", field: stock,
      get: (d) => (d.stock === undefined ? null : d.stock), put: (d, v) => { d.stock = v; } });
    out.push(order.readonly || order.locked
      ? { key: "order", label: order.label, kind: "fixed", get: (d) => d.order, text: (v) => (v === undefined ? "" : String(v)), why: order.readonly || order.locked }
      : { key: "order", label: order.label, kind: "int", field: order, get: (d) => d.order, put: (d, v) => { d.order = v; } });
    return out;
  }

  // What a typed or pasted cell holds: {raw, value}, or {raw, error} with the
  // message the cell shows. Empty stock means the product does not track it.
  function parse(col, raw) {
    const s = String(raw === null || raw === undefined ? "" : raw);
    const t = s.trim();
    const fd = col.field || {};
    if (col.kind === "text") {
      const p = textProblem(t);
      if (p) return { raw: s, error: p };
      if (!t) return { raw: s, error: fd.label + " is required." };
      if (fd.maxLength && t.length > fd.maxLength) return { raw: s, error: "Keep this under " + fd.maxLength + " characters." };
      return { raw: s, value: t };
    }
    if (col.kind === "status") {
      const w = t.toLowerCase();
      if (w === "active") return { raw: s, value: true };
      if (w === "draft") return { raw: s, value: false };
      return { raw: s, error: "Type Active or Draft." };
    }
    const n = t.replace(/^aed\s*/i, "").replace(/,/g, "");
    if (col.kind === "stock" && (n === "" || /^not tracked$/i.test(n))) return { raw: s, value: null };
    if (n === "") return { raw: s, error: col.kind === "money" ? "Enter a price." : "Enter a number." };
    if (!/^\d+(\.0+)?$/.test(n)) return { raw: s, error: col.kind === "money" ? "Enter a whole number of dirhams." : "Enter a whole number." };
    const v = Math.trunc(Number(n));
    const lo = fd.min !== undefined ? fd.min : col.kind === "money" ? 1 : null;
    if (lo !== null && v < lo) return { raw: s, error: "The lowest allowed is " + lo + "." };
    if (fd.max !== undefined && fd.max !== null && v > fd.max) return { raw: s, error: "The highest allowed is " + fd.max + "." };
    return { raw: s, value: v };
  }

  const has = (row, col) => Object.prototype.hasOwnProperty.call(row.edits, col.key);
  const applies = (row, col) => !col.applies || col.applies(row.data);
  const editable = (row, col) => col.kind !== "fixed" && applies(row, col);
  const saved = (row, col) => (applies(row, col) ? col.get(row.data) : undefined);
  const value = (row, col) => (has(row, col) ? row.edits[col.key].value : saved(row, col));
  const editError = (row, col) => (has(row, col) ? row.edits[col.key].error || null : null);
  const name = (row) => row.data.name || row.id;
  const names = () => Object.fromEntries(rows.map((r) => [r.id, name(r)]));
  const count = () => rows.reduce((n, r) => n + Object.keys(r.edits).length, 0);

  // An attar's price is the size its card shows first, so it has to be one
  // of its sizes' prices; the server refuses a save where it is not. Checked
  // only once the price or a size price was touched here.
  function crossError(row, col) {
    if (col.key !== "price" || row.data.category !== "attars" || !Array.isArray(row.data.sizes)) return null;
    const sizeCols = cols.filter((c) => c.key.startsWith("size"));
    if (!has(row, col) && !sizeCols.some((c) => has(row, c))) return null;
    const prices = row.data.sizes.map((s, i) => {
      const c = sizeCols.find((x) => x.key === "size" + i);
      return c && has(row, c) && !editError(row, c) ? row.edits[c.key].value : s.price;
    });
    return prices.includes(value(row, col)) ? null : "The price must be one of the sizes' prices: it is the size the card shows first.";
  }

  const cellError = (row, col) => editError(row, col) || row.server[col.key] || crossError(row, col);

  // The text a cell gives the clipboard and its editor starts from: the value
  // as it would be typed, so a copied block pastes back as it was.
  function rawText(row, col) {
    if (editError(row, col)) return row.edits[col.key].raw;
    const v = value(row, col);
    if (col.kind === "status") return v ? "Active" : "Draft";
    if (v === null || v === undefined) return "";
    return col.text ? col.text(v) : String(v);
  }

  const note = h("div", { class: "msgs" });
  const staleBox = h("div", { class: "msgs bulk-stale" });
  const wrap = h("div", { class: "bulk-wrap" });
  const status = h("p", { class: "bulk-status", role: "status" });
  const saveBtn = h("button", { class: "btn primary", type: "button", disabled: true, onclick: () => save() }, "Save changes");
  clear(main).append(
    h("div", { class: "page-head" },
      h("div", {},
        h("a", { class: "back", href: "#/products" }, "Products"),
        h("h1", { tabindex: "-1" }, "Bulk editor"),
        h("p", { class: "sub" }, "Edit many products like a spreadsheet, then save them together: every change is saved, or none is.")),
      h("div", { class: "head-actions" }, saveBtn)),
    note, staleBox,
    h("section", { class: "card flush" },
      h("div", { class: "toolbar" },
        h("label", { class: "search" }, icon("search", 16),
          h("input", { class: "input", type: "search", placeholder: "Search products", "aria-label": "Search products",
            oninput: (e) => { f.q = e.target.value.trim().toLowerCase(); refilter(); } })),
        h("select", { class: "input", "aria-label": "Category", onchange: (e) => { f.category = e.target.value; refilter(); } },
          h("option", { value: "" }, "All categories"), Object.entries(cats).map(([k, v]) => h("option", { value: k }, v)))),
      h("p", { class: "bulk-keys", id: "bulk-keys" },
        "Arrow keys move, Enter or F2 edits, Tab goes to the next cell, Esc puts a cell back and Cmd or Ctrl+Z undoes. ",
        "Paste cells copied from a spreadsheet to fill the grid from the cell in focus."),
      status, wrap));

  // A filter hides rows but keeps their changes: the save sends them all.
  function refilter() {
    if (editing) commit();
    drawGrid();
  }

  function drawGrid() {
    shown = rows.filter((row) => (!f.category || row.data.category === f.category)
      && (!f.q || row.id.includes(f.q) || (row.data.name || "").toLowerCase().includes(f.q)));
    clear(wrap);
    cells = [];
    if (!shown.length) {
      wrap.append(h("p", { class: "empty" }, rows.length ? "No products match." : "There are no products yet."));
      return;
    }
    at = { r: Math.min(at.r, shown.length - 1), c: Math.min(at.c, cols.length - 1) };
    const head = h("tr", { role: "row", "aria-rowindex": "1" }, cols.map((c, j) => h("th", {
      role: "columnheader", scope: "col", "aria-colindex": String(j + 1), class: "g-h g-" + c.kind + (j === 0 ? " g-first" : "") }, c.label)));
    const body = shown.map((row, i) => {
      const tr = h("tr", { role: "row", "aria-rowindex": String(i + 2), class: row.stale ? "stale" : null });
      cells[i] = cols.map((col, j) => {
        const el = h(j === 0 ? "th" : "td", { role: j === 0 ? "rowheader" : "gridcell", scope: j === 0 ? "row" : null,
          "aria-colindex": String(j + 1), tabindex: i === at.r && j === at.c ? "0" : "-1", dataset: { r: String(i), c: String(j) } });
        fillCell(el, row, col);
        tr.append(el);
        return el;
      });
      return tr;
    });
    wrap.append(h("table", { class: "grid", role: "grid", "aria-label": "Products", "aria-rowcount": String(shown.length + 1),
      "aria-colcount": String(cols.length), "aria-describedby": "bulk-keys",
      onkeydown: onKey, onpaste: onPaste, oncopy: onCopy, onfocusin: onFocusIn,
      ondblclick: (e) => { if (!e.target.closest("button, input, select")) startEdit(); } },
    h("thead", {}, head), h("tbody", {}, body)));
  }

  function fillCell(el, row, col) {
    clear(el);
    const first = cols[0] === col;
    const ok = applies(row, col);
    const err = ok ? cellError(row, col) : null;
    const edited = has(row, col) && !editError(row, col);
    el.className = "g-cell g-" + col.kind + (first ? " g-first" : "") + (edited ? " changed" : "") + (err ? " invalid" : "")
      + (editable(row, col) ? "" : " ro");
    for (const a of ["aria-invalid", "aria-describedby", "aria-readonly", "title"]) el.removeAttribute(a);
    if (!editable(row, col)) {
      el.setAttribute("aria-readonly", "true");
      if (col.why) el.title = col.why;
    }
    if (!ok) {
      el.append(h("span", { class: "sr-only" }, "Not used by this product"));
      return;
    }
    const v = value(row, col);
    if (col.kind === "status" && !editError(row, col)) el.append(h("span", { class: "badge" + (v ? " green" : " muted") }, v ? "Active" : "Draft"));
    else if (col.kind === "stock" && v === null && !editError(row, col)) el.append(h("span", { class: "g-val muted" }, "Not tracked"));
    else el.append(h("span", { class: "g-val" }, rawText(row, col)));
    if (col.note) el.append(h("span", { class: "g-note" }, col.note(row.data)));
    if (first) {
      el.append(h("span", { class: "g-id" }, row.id));
      // The row's own button is for the mouse; the banner above the grid
      // has a Reload button per row that the keyboard reaches.
      if (row.stale) el.append(h("span", { class: "g-stale" }, h("span", { class: "badge red" }, "Changed elsewhere"),
        h("button", { class: "btn small", type: "button", tabindex: "-1", onclick: () => reload(row) }, "Reload row")));
      if (row.server._row) el.append(h("span", { class: "g-err" }, row.server._row.join(" ")));
    }
    if (err) {
      const id = "g-err-" + row.id + "-" + col.key;
      el.append(h("span", { class: "g-err", id }, err));
      el.setAttribute("aria-invalid", "true");
      el.setAttribute("aria-describedby", id);
    }
    if (edited) el.append(h("span", { class: "sr-only" }, " (changed)"));
  }

  // One cell of the grid is in the tab order at a time (a roving tabindex),
  // and focus follows the arrow keys, Tab and the mouse.
  function go(r, c) {
    if (!cells.length) return;
    r = Math.max(0, Math.min(shown.length - 1, r));
    c = Math.max(0, Math.min(cols.length - 1, c));
    const old = cells[at.r] && cells[at.r][at.c];
    if (old) old.tabIndex = -1;
    at = { r, c };
    cells[r][c].tabIndex = 0;
    cells[r][c].focus();
  }

  // Tab and Shift+Tab walk the cells in reading order, row after row.
  function next(d) {
    let r = at.r, c = at.c + d;
    if (c >= cols.length) { c = 0; r++; } else if (c < 0) { c = cols.length - 1; r--; }
    go(r, c);
  }

  function onFocusIn(e) {
    if (editing || !e.target.dataset || e.target.dataset.r === undefined) return;
    const r = Number(e.target.dataset.r), c = Number(e.target.dataset.c);
    if (r === at.r && c === at.c) return;
    const old = cells[at.r] && cells[at.r][at.c];
    if (old) old.tabIndex = -1;
    at = { r, c };
    e.target.tabIndex = 0;
  }

  function onKey(e) {
    if (editing || !cells.length || e.target.closest("input, select, button")) return;
    const k = e.key, mod = e.metaKey || e.ctrlKey;
    if (mod && !e.altKey && (k === "z" || k === "Z")) { e.preventDefault(); if (e.shiftKey) step(redo, undo, "after"); else step(undo, redo, "before"); return; }
    if (mod && (k === "y" || k === "Y")) { e.preventDefault(); step(redo, undo, "after"); return; }
    if (mod && k === "Home") { e.preventDefault(); go(0, 0); return; }
    if (mod && k === "End") { e.preventDefault(); go(shown.length - 1, cols.length - 1); return; }
    if (mod || e.altKey) return;
    const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1], PageUp: [-10, 0], PageDown: [10, 0] };
    if (moves[k]) { e.preventDefault(); go(at.r + moves[k][0], at.c + moves[k][1]); }
    else if (k === "Home") { e.preventDefault(); go(at.r, 0); }
    else if (k === "End") { e.preventDefault(); go(at.r, cols.length - 1); }
    else if (k === "Tab") {
      // From the first or last cell Tab leaves the grid, as it does a form.
      const edge = e.shiftKey ? at.r === 0 && at.c === 0 : at.r === shown.length - 1 && at.c === cols.length - 1;
      if (!edge) { e.preventDefault(); next(e.shiftKey ? -1 : 1); }
    }
    else if (k === "Enter" || k === "F2") { e.preventDefault(); startEdit(); }
    else if (k === "Escape") { e.preventDefault(); revert(); }
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); clearCell(); }
    else if (k.length === 1) { e.preventDefault(); startEdit(k); }
  }

  // Enter or F2 opens the cell's editor with its value selected; typing a
  // character opens it with that character, as a spreadsheet does.
  function startEdit(seed) {
    const row = shown[at.r], col = cols[at.c];
    if (!row) return;
    if (!editable(row, col)) {
      announce(applies(row, col) ? col.why || "This cell cannot be edited here." : "This product does not use " + col.label + ".");
      return;
    }
    const el = cells[at.r][at.c];
    const label = col.label + ", " + name(row);
    let input;
    if (col.kind === "status") {
      const w = seed ? seed.toLowerCase() : "";
      input = h("select", { class: "g-input", "aria-label": label }, h("option", { value: "Active" }, "Active"), h("option", { value: "Draft" }, "Draft"));
      input.value = w === "a" ? "Active" : w === "d" ? "Draft" : value(row, col) ? "Active" : "Draft";
      input.addEventListener("change", () => { if (editing && editing.input === input) { commit(); go(at.r, at.c); } });
    } else {
      input = h("input", { class: "g-input", type: "text", "aria-label": label, autocomplete: "off", spellcheck: "false",
        inputmode: col.kind === "text" ? null : "numeric", value: seed !== undefined ? seed : rawText(row, col) });
    }
    editing = { row, col, el, input };
    clear(el).append(input);
    el.classList.add("editing");
    input.addEventListener("keydown", onEditKey);
    input.addEventListener("blur", () => { if (editing && editing.input === input) commit(); });
    input.focus();
    if (input.tagName === "INPUT") {
      if (seed === undefined) input.select();
      else input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  function onEditKey(e) {
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); commit(); go(at.r + (e.shiftKey ? -1 : 1), at.c); }
    else if (e.key === "Tab") { e.preventDefault(); e.stopPropagation(); commit(); next(e.shiftKey ? -1 : 1); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); }
  }

  // Closes the open editor, keeping what it holds. Focus stays where it is:
  // the caller moves it, or the click that closed the editor already did.
  function commit() {
    if (!editing) return;
    const { row, col, el, input } = editing;
    editing = null;
    el.classList.remove("editing");
    const entry = setCell(row, col, parse(col, input.value));
    if (entry) change([entry]);
    else fillCell(el, row, col);
  }

  function cancel() {
    if (!editing) return;
    const { row, col, el } = editing;
    editing = null;
    fillCell(el, row, col);
    el.focus();
  }

  // A cell's new state: an edit record, or undefined for its saved value.
  // Returns the undo entry, or null when nothing changes.
  function setCell(row, col, rec) {
    if (rec && !rec.error && same(rec.value, saved(row, col))) rec = undefined;
    const before = has(row, col) ? row.edits[col.key] : undefined;
    if (sig(before) === sig(rec)) return null;
    if (rec === undefined) delete row.edits[col.key];
    else row.edits[col.key] = rec;
    delete row.server[col.key];
    return { id: row.id, key: col.key, before, after: rec };
  }
  const sig = (rec) => (rec === undefined ? "saved" : JSON.stringify(rec.error ? ["error", rec.raw] : ["value", rec.value]));

  // Every change is one undo step: a typed cell, a revert, or a whole paste.
  function change(entries) {
    const list = entries.filter(Boolean);
    if (!list.length) return;
    undo.push(list);
    if (undo.length > UNDO_STEPS) undo.shift();
    redo.length = 0;
    refresh(list, false);
  }

  // Undo and redo move one step between the stacks, putting back the side of
  // each entry they are asked for, and bring its first cell into focus.
  function step(from, to, side) {
    const list = from.pop();
    if (!list) { announce(side === "before" ? "Nothing to undo." : "Nothing to redo."); return; }
    for (const en of list) {
      const row = rows.find((x) => x.id === en.id);
      if (!row) continue;
      if (en[side] === undefined) delete row.edits[en.key];
      else row.edits[en.key] = en[side];
      delete row.server[en.key];
    }
    to.push(list);
    refresh(list, true);
    announce((side === "before" ? "Undone: " : "Redone: ") + plural(list.length, "cell") + ".");
  }

  // Redraws every cell of the rows a change touched: an attar's price cell
  // depends on its size cells, so a whole row is the unit.
  function refresh(list, focus) {
    const ids = new Set(list.map((en) => en.id));
    shown.forEach((row, i) => { if (ids.has(row.id)) cols.forEach((col, j) => fillCell(cells[i][j], row, col)); });
    if (focus) {
      const i = shown.findIndex((row) => row.id === list[0].id);
      const j = cols.findIndex((col) => col.key === list[0].key);
      if (i >= 0 && j >= 0) go(i, j);
    }
    update();
  }

  const spoken = (row, col) => (col.kind === "stock" && value(row, col) === null ? "Not tracked" : rawText(row, col) || "empty");

  function revert() {
    const row = shown[at.r], col = cols[at.c];
    if (!row || !has(row, col)) return;
    change([setCell(row, col, undefined)]);
    announce(col.label + " is back to " + spoken(row, col) + ".");
  }

  function clearCell() {
    const row = shown[at.r], col = cols[at.c];
    if (!row || !editable(row, col)) return;
    change([setCell(row, col, parse(col, ""))]);
  }

  // A block pasted from a spreadsheet fills the grid from the focused cell
  // right and down. Every cell is checked on its own and kept even when it
  // is wrong, marked, so the owner sees what arrived; read-only cells, cells
  // a product does not use and cells past the edge are skipped and counted.
  function onPaste(e) {
    if (editing || !cells.length) return;
    const text = e.clipboardData ? e.clipboardData.getData("text/plain") : "";
    if (!text) return;
    e.preventDefault();
    const entries = [];
    let placed = 0, skipped = 0;
    parseTsv(text).forEach((line, i) => line.forEach((raw, j) => {
      const row = shown[at.r + i], col = cols[at.c + j];
      if (!row || !col || !editable(row, col)) { skipped++; return; }
      placed++;
      entries.push(setCell(row, col, parse(col, raw)));
    }));
    change(entries);
    const bad = invalid().length;
    status.textContent = ["Pasted " + plural(placed, "cell") + "."]
      .concat(bad ? [plural(bad, "cell") + " in the grid " + (bad === 1 ? "needs" : "need") + " attention, marked in red."] : [])
      .concat(skipped ? [plural(skipped, "cell") + " skipped: read-only, not used by that product, or past the edge of the grid."] : [])
      .join(" ");
  }

  function onCopy(e) {
    if (editing || !cells.length || !e.clipboardData || e.target.closest("input, select")) return;
    const row = shown[at.r], col = cols[at.c];
    if (!row) return;
    e.clipboardData.setData("text/plain", applies(row, col) ? rawText(row, col) : "");
    e.preventDefault();
    announce("Copied.");
  }

  // The cells that block a save: a value that is not allowed, or an attar
  // price that matches none of its sizes. A message from the server is shown
  // but does not block: the next save asks the server again.
  function invalid() {
    const out = [];
    for (const row of rows) {
      for (const col of cols) {
        const message = applies(row, col) && (editError(row, col) || crossError(row, col));
        if (message) out.push({ row, col, message });
      }
    }
    return out;
  }

  function update() {
    const n = count();
    saveBtn.textContent = n ? "Save " + plural(n, "change") : "Save changes";
    saveBtn.disabled = !n;
    if (n) savebar.show({ onSave: save, onDiscard: discard, message: plural(n, "unsaved change") });
    else savebar.hide();
  }

  // The product as it will be saved: the loaded copy with this grid's edits.
  function build(r) {
    const d = copy(r.data);
    for (const col of cols) if (has(r, col) && col.put) col.put(d, r.edits[col.key].value);
    return d;
  }

  async function save() {
    if (editing) commit();
    const dirty = rows.filter((r) => Object.keys(r.edits).length);
    if (!dirty.length) return;
    clear(note);
    const bad = invalid();
    if (bad.length) {
      note.append(banner({ tone: "critical", title: "Not saved: " + plural(bad.length, "cell") + " to fix first.",
        items: bad.slice(0, 8).map((b) => name(b.row) + ", " + b.col.label + ": " + b.message)
          .concat(bad.length > 8 ? ["And " + (bad.length - 8) + " more, marked in the grid."] : []) }));
      const i = shown.indexOf(bad[0].row);
      if (i >= 0) go(i, cols.indexOf(bad[0].col));
      return;
    }
    const stale = dirty.filter((r) => r.stale);
    if (stale.length) {
      note.append(banner({ tone: "warning", title: "Reload the rows marked Changed elsewhere first.", items: stale.map(name) }));
      return;
    }
    const n = count();
    const changes = dirty.map((r) => ({ id: r.id, rev: r.rev, data: build(r) }));
    saveBtn.disabled = true;
    savebar.busy("Saving " + plural(n, "change") + " and rebuilding the site");
    try {
      const res = await saveProducts(app, changes, names());
      for (const c of changes) {
        const r = rows.find((x) => x.id === c.id);
        Object.assign(r, { data: c.data, rev: (res.revs && res.revs[c.id]) || r.rev, edits: {}, server: {}, stale: false });
        if (app.state.products) app.state.products[c.id] = c.data;
      }
      undo.length = 0;
      redo.length = 0;
      status.textContent = "";
      drawGrid();
      drawStale();
      update();
      if (cells.length) go(at.r, at.c);
      toast("Saved " + plural(n, "change") + " to " + plural(changes.length, "product") + "." + builtIn(res));
      const w = warningsBanner(res, names());
      if (w) note.append(w);
    } catch (e) {
      update();
      if (e.code === "stale_rev" && e.details && e.details.conflicts) {
        for (const c of e.details.conflicts) {
          const r = rows.find((x) => x.id === c.id);
          if (r) r.stale = true;
        }
        drawGrid();
        drawStale();
      } else if (e.code === "validation" && e.details && e.details.errors) {
        problems(e.details.errors);
      } else if (e.code !== "cancelled") {
        const b = failure(e);
        if (b) note.append(b);
      }
    }
  }

  // A 422 names each product's problems by JSON pointer. A problem in one of
  // the grid's columns marks its cell; the rest are written under the name.
  function problems(errors) {
    rows.forEach((r) => { r.server = {}; });
    const items = [];
    for (const [id, list] of Object.entries(errors)) {
      const r = rows.find((x) => x.id === id);
      for (const x of list) {
        const k = keyFor(x.path || "");
        if (r && k) r.server[k] = x.message;
        else if (r) r.server._row = (r.server._row || []).concat(x.message);
        items.push(((r && name(r)) || id) + (k ? ", " + cols.find((c) => c.key === k).label : "") + ": " + x.message);
      }
    }
    drawGrid();
    const n = Object.keys(errors).length;
    note.append(banner({ tone: "critical", title: "Not saved: " + plural(n, "product") + " " + (n === 1 ? "needs" : "need") + " attention.",
      items: items.slice(0, 10).concat(items.length > 10 ? ["And " + (items.length - 10) + " more, marked in the grid."] : []) }));
  }

  function keyFor(path) {
    const m = /^\/sizes\/(\d+)\/price$/.exec(path);
    const k = m ? "size" + m[1] : path.split("/")[1] || "";
    return cols.some((c) => c.key === k) ? k : null;
  }

  // Stale rows get a Reload button each here, where the keyboard reaches it.
  function drawStale() {
    clear(staleBox);
    const list = rows.filter((r) => r.stale);
    if (!list.length) return;
    staleBox.append(banner({ tone: "warning", title: "Not saved: " + plural(list.length, "product") + " changed since this screen opened.",
      items: ["Reload those rows, then save again. Your changes stay, except where the same cell was changed elsewhere too."],
      actions: list.map((r) => h("button", { class: "btn small", type: "button", onclick: () => reload(r) }, "Reload " + name(r)))
        .concat(list.length > 1 ? [h("button", { class: "btn small", type: "button", onclick: reloadAll }, "Reload all")] : []) }));
  }

  // A fresh copy of one product after a 412. An edit is kept where the cell
  // still holds what this screen loaded, and dropped where it was changed
  // elsewhere too, so a reload never quietly overwrites someone else's change.
  async function reload(row) {
    if (editing) commit();
    try {
      const fresh = await api("GET", "products/" + row.id);
      const freshRow = { data: fresh.data };
      const dropped = [];
      for (const col of cols) {
        if (!has(row, col)) continue;
        const now = applies(freshRow, col) ? col.get(fresh.data) : undefined;
        if (!applies(freshRow, col) || !same(saved(row, col), now)) {
          dropped.push(col.label);
          delete row.edits[col.key];
        }
      }
      Object.assign(row, { data: fresh.data, rev: fresh.rev, stale: false, server: {} });
      for (const col of cols) {
        if (has(row, col) && !editError(row, col) && same(row.edits[col.key].value, saved(row, col))) delete row.edits[col.key];
      }
      forget(row.id);
      if (app.state.products) app.state.products[row.id] = fresh.data;
      const kept = Object.keys(row.edits).length;
      toast("Reloaded " + name(row) + "."
        + (dropped.length ? " " + dropped.join(", ") + " changed elsewhere too, so your value" + (dropped.length === 1 ? " was" : "s were") + " dropped." : "")
        + (kept ? " Your other changes are kept." : ""));
    } catch (e) {
      if (e.status === 404) {
        rows = rows.filter((x) => x !== row);
        forget(row.id);
        toast(name(row) + " was deleted elsewhere, so its row is gone.");
      } else {
        const b = failure(e);
        if (b) note.append(b);
      }
    }
    drawGrid();
    drawStale();
    update();
  }

  // Undo steps that touch a reloaded row would put back edits made against
  // the copy it replaced, so they go.
  function forget(id) {
    for (const st of [undo, redo]) {
      for (let i = st.length - 1; i >= 0; i--) {
        st[i] = st[i].filter((en) => en.id !== id);
        if (!st[i].length) st.splice(i, 1);
      }
    }
  }

  async function reloadAll() {
    for (const r of rows.filter((x) => x.stale)) await reload(r);
  }

  function discard() {
    if (editing) cancel();
    rows.forEach((r) => { r.edits = {}; r.server = {}; });
    undo.length = 0;
    redo.length = 0;
    clear(note);
    status.textContent = "";
    drawGrid();
    update();
    announce("Changes discarded.");
  }

  guard.set(() => count() > 0 || !!editing);
  onSaveKey(save);
  try {
    const list = await api("GET", "products");
    app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
    const most = Math.max(0, ...list.items.filter((it) => it.data.category === "attars" && Array.isArray(it.data.sizes))
      .map((it) => it.data.sizes.length));
    const cap = F("/sizes").max;
    cols = columns(cap ? Math.min(cap, most) : most);
    rows = list.items.map((it) => ({ id: it.id, rev: it.rev, data: it.data, edits: {}, server: {}, stale: false }));
    drawGrid();
    update();
  } catch (e) {
    clear(wrap).append(banner({ tone: "critical", title: e.message }));
  }
}
