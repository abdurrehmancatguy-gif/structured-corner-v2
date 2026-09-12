// Inventory: every product that tracks its stock, with the number editable in
// place. One Save sends every changed row as one products/bulk save, so the
// set is saved and the site rebuilt together, or nothing changes.
import { api } from "../lib/api.js";
import { h, clear, copy, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast, savebar, guard, onSaveKey, announce } from "../lib/ui.js";
import { categories, productField, saveProducts, failure, builtIn, plural, warningsBanner } from "../lib/bulk.js";

// shop.js shows "only N left" on a card at 5 or fewer. The filter follows
// settings.store.low_stock_at instead once that key exists.
const LOW = 5;

export async function render(main, { app }) {
  useCss("inventory");
  const F = productField(app, "/stock");
  const lo = F.min !== undefined ? F.min : 0;
  const hi = F.max !== undefined ? F.max : null;
  const cats = categories(app);
  const f = { q: "", low: false };
  let rows = [];
  let low = LOW;
  const note = h("div", { class: "msgs" });
  // The 412 banner has a box of its own, so it goes once the last stale row
  // is reloaded instead of staying until the next save.
  const staleBox = h("div", { class: "msgs" });
  const table = h("div", { class: "table-wrap" });
  const lowText = h("span", {}, LOW + " or fewer");
  const foot = h("p", { class: "inv-foot" });

  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("a", { class: "back", href: "#/products" }, "Products"),
      h("h1", { tabindex: "-1" }, "Inventory"),
      h("p", { class: "sub" }, "Products that track their stock. Change any number and save once: every changed row is saved together, or none is."))),
    note, staleBox,
    h("section", { class: "card flush inv-card" },
      h("div", { class: "toolbar" },
        h("label", { class: "search" }, icon("search", 16),
          h("input", { class: "input", type: "search", placeholder: "Search products", "aria-label": "Search products",
            oninput: (e) => { f.q = e.target.value.trim().toLowerCase(); draw(); } })),
        h("label", { class: "check", for: "inv-low" },
          h("input", { type: "checkbox", id: "inv-low", onchange: (e) => { f.low = e.target.checked; draw(); } }), lowText)),
      table, foot));

  const name = (r) => r.data.name || r.id;
  const names = () => Object.fromEntries(rows.map((r) => [r.id, name(r)]));
  const changed = (r) => r.edit !== null;

  // Stock here is always a number: emptying it would stop tracking, which
  // belongs on the product page, where the Track switch says what it does.
  function parse(raw) {
    const s = String(raw).trim();
    if (s === "") return { raw, error: "Enter how many are in stock. To stop tracking it, open the product." };
    if (!/^\d+$/.test(s)) return { raw, error: "Enter a whole number." };
    const n = Number(s);
    if (n < lo) return { raw, error: "The lowest allowed is " + lo + "." };
    if (hi !== null && n > hi) return { raw, error: "The highest allowed is " + hi + "." };
    return { raw, value: n };
  }

  // The filter reads the saved number, so a row does not vanish while its
  // number is being typed.
  function shown() {
    return rows.filter((r) => {
      if (f.low && !(r.data.stock <= low)) return false;
      if (f.q && !r.id.includes(f.q) && !(r.data.name || "").toLowerCase().includes(f.q)) return false;
      return true;
    });
  }

  function draw() {
    const list = shown();
    drawStale();
    clear(table);
    foot.textContent = rows.length ? "At " + low + " or fewer the product's card shows how many are left." : "";
    foot.hidden = !rows.length;
    if (!rows.length) {
      table.append(h("p", { class: "empty" }, "No product tracks its stock. Turn on Track in a product's Inventory card and it is listed here."));
      return;
    }
    if (!list.length) {
      table.append(h("p", { class: "empty" }, f.low ? "No tracked product has " + low + " or fewer left." : "No products match."));
      return;
    }
    table.append(h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", {}, "Product"), h("th", {}, "Category"), h("th", {}, "Status"), h("th", {}, "Stock"))),
      h("tbody", {}, list.map(rowEl))));
  }

  function rowEl(r) {
    const id = "inv-" + r.id;
    const msg = h("span", { class: "inv-msg", id: id + "-msg", hidden: true });
    const input = h("input", {
      class: "input inv-stock", id, type: "text", inputmode: "numeric", autocomplete: "off", spellcheck: "false",
      value: r.edit ? r.edit.raw : String(r.data.stock), "aria-describedby": id + "-msg",
      oninput: (e) => {
        const p = parse(e.target.value);
        r.edit = !p.error && p.value === r.data.stock ? null : p;
        r.problem = null;
        paint(r);
        update();
      },
      onkeydown: (e) => keys(e, r),
    });
    const tr = h("tr", {},
      h("td", {},
        h("a", { href: "#/products/" + r.id, class: "t-name" }, name(r)), h("span", { class: "t-id" }, r.id),
        r.stale ? h("span", { class: "inv-stale" }, h("span", { class: "badge red" }, "Changed elsewhere"),
          h("button", { class: "btn small", type: "button", "aria-label": "Reload " + name(r), onclick: () => reload(r) }, "Reload row")) : null),
      h("td", {}, cats[r.data.category] || r.data.category),
      h("td", {}, r.data.published === false ? h("span", { class: "badge" }, "Draft") : h("span", { class: "badge green" }, "Active")),
      h("td", {},
        h("div", { class: "inv-cell" }, h("label", { class: "sr-only", for: id }, "Stock for " + name(r)), input,
          r.data.stock <= low ? h("span", { class: "badge red" }, "Low stock") : null),
        msg));
    r.el = { tr, input, msg };
    paint(r);
    return tr;
  }

  function paint(r) {
    const { tr, input, msg } = r.el;
    const err = (r.edit && r.edit.error) || r.problem;
    tr.className = "inv-row" + (r.edit && !r.edit.error ? " changed" : "") + (err ? " invalid" : "") + (r.stale ? " stale" : "");
    msg.textContent = err || "";
    msg.hidden = !err;
    if (err) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  }

  // Enter goes down the column as in a spreadsheet, Shift+Enter up; Esc puts
  // the saved number back.
  function keys(e, r) {
    if (e.key === "Escape" && (r.edit || r.problem)) {
      e.preventDefault();
      r.edit = null;
      r.problem = null;
      e.target.value = String(r.data.stock);
      paint(r);
      update();
      announce("Stock for " + name(r) + " put back to " + r.data.stock + ".");
    } else if (e.key === "Enter") {
      e.preventDefault();
      const all = [...table.querySelectorAll(".inv-stock")];
      const next = all[all.indexOf(e.target) + (e.shiftKey ? -1 : 1)];
      if (next) { next.focus(); next.select(); }
    }
  }

  function update() {
    const n = rows.filter(changed).length;
    if (n) savebar.show({ onSave: save, onDiscard: discard, message: plural(n, "unsaved change") });
    else savebar.hide();
  }

  function discard() {
    rows.forEach((r) => { r.edit = null; r.problem = null; });
    clear(note);
    draw();
    update();
    announce("Changes discarded.");
  }

  async function save() {
    const edited = rows.filter(changed);
    if (!edited.length) return;
    clear(note);
    const bad = edited.filter((r) => r.edit.error);
    if (bad.length) {
      note.append(banner({ tone: "critical", title: "Not saved: " + plural(bad.length, "number") + " to fix first.",
        items: bad.map((r) => name(r) + ": " + r.edit.error) }));
      if (bad[0].el && bad[0].el.input.isConnected) bad[0].el.input.focus();
      return;
    }
    savebar.busy("Saving and rebuilding the site");
    const changes = edited.map((r) => ({ id: r.id, rev: r.rev, data: Object.assign(copy(r.data), { stock: r.edit.value }) }));
    try {
      const res = await saveProducts(app, changes, names());
      for (const c of changes) {
        const r = rows.find((x) => x.id === c.id);
        Object.assign(r, { data: c.data, rev: (res.revs && res.revs[c.id]) || r.rev, edit: null, problem: null, stale: false });
        if (app.state.products) app.state.products[c.id] = c.data;
      }
      draw();
      update();
      toast("Saved the stock of " + plural(changes.length, "product") + "." + builtIn(res));
      const w = warningsBanner(res, names());
      if (w) note.append(w);
    } catch (e) {
      update();
      if (e.code === "stale_rev" && e.details && e.details.conflicts) stale(e.details.conflicts);
      else if (e.code === "validation" && e.details && e.details.errors) problems(e.details.errors);
      else if (e.code !== "cancelled") { const b = failure(e); if (b) note.append(b); }
    }
  }

  function stale(conflicts) {
    for (const c of conflicts) {
      const r = rows.find((x) => x.id === c.id);
      if (r) r.stale = true;
    }
    draw();
  }

  function drawStale() {
    clear(staleBox);
    const n = rows.filter((r) => r.stale).length;
    if (n) staleBox.append(banner({ tone: "warning", title: "Not saved: " + plural(n, "product") + " changed since this screen opened.",
      items: ["Reload the rows marked Changed elsewhere, then save again. Your other numbers are still here."] }));
  }

  function problems(errors) {
    const items = [];
    for (const [id, list] of Object.entries(errors)) {
      const r = rows.find((x) => x.id === id);
      const text = list.map((x) => x.message).join(" ");
      if (r) { r.problem = text; if (r.el) paint(r); }
      items.push(((r && name(r)) || id) + ": " + text);
    }
    note.append(banner({ tone: "critical", title: "Not saved: some products need attention.", items }));
  }

  // A fresh copy of one product after a 412. The typed number is kept when
  // the stock itself did not change elsewhere, and dropped when it did, so a
  // reload never quietly overwrites someone else's count.
  async function reload(r) {
    try {
      const fresh = await api("GET", "products/" + r.id);
      const mine = r.edit;
      const theirs = fresh.data.stock;
      const kept = !!mine && theirs === r.data.stock;
      Object.assign(r, { data: fresh.data, rev: fresh.rev, stale: false, problem: null,
        edit: kept && (mine.error || mine.value !== theirs) ? mine : null });
      if (app.state.products) app.state.products[r.id] = fresh.data;
      if (theirs === null || theirs === undefined) {
        rows = rows.filter((x) => x !== r);
        toast(name(r) + " no longer tracks its stock, so it left this list.");
      } else if (mine && !kept) {
        toast("The stock of " + name(r) + " was changed elsewhere to " + theirs + ". Your number was dropped.");
      } else {
        toast("Reloaded " + name(r) + (kept ? ". Your number is kept." : "."));
      }
    } catch (e) {
      if (e.status === 404) {
        rows = rows.filter((x) => x !== r);
        toast(name(r) + " was deleted elsewhere.");
      } else {
        const b = failure(e);
        if (b) note.append(b);
      }
    }
    draw();
    update();
  }

  guard.set(() => rows.some(changed));
  onSaveKey(save);
  try {
    const [list, settings] = await Promise.all([api("GET", "products"), api("GET", "documents/settings").catch(() => null)]);
    const s = settings && settings.data && settings.data.store;
    if (s && Object.prototype.hasOwnProperty.call(s, "low_stock_at") && Number.isInteger(s.low_stock_at)) low = s.low_stock_at;
    lowText.textContent = low + " or fewer";
    app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
    rows = list.items.filter((it) => it.data.stock !== null && it.data.stock !== undefined)
      .map((it) => ({ id: it.id, rev: it.rev, data: it.data, edit: null, problem: null, stale: false, el: null }));
    draw();
  } catch (e) {
    clear(table).append(banner({ tone: "critical", title: e.message }));
  }
}
