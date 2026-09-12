// Translations: the Arabic the storefront's language switch puts in place of
// the shop's English labels, edited as one table and saved as a whole; then
// how far each product's own Arabic name and story have got (saved with the
// product, not shown by the shop yet).
import { api } from "../lib/api.js";
import { h, clear, append, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, announce } from "../lib/ui.js";
import { mountEditor } from "../lib/editor.js";
import { iconBtn } from "../lib/forms.js";

// The elements shop.js's toggle looks in for text to swap (toggleLang).
const SWAPPED = "a,span,b,p,h1,h2,h3,h4,h5,button,i,div,label";

// The editor works on a list of rows, not on the stored object: an object
// cannot hold a row still being typed with no English yet, or two rows with
// the same English, and both have to be shown and fixed before a save.
function toRows(doc) {
  const rest = Object.assign({}, doc);
  const dict = rest.ar && typeof rest.ar === "object" && !Array.isArray(rest.ar) ? rest.ar : {};
  delete rest.ar;
  return { rest, rows: Object.entries(dict).map(([en, ar]) => ({ en, ar: typeof ar === "string" ? ar : "" })) };
}

// Back to the stored shape. The shop matches the trimmed text of a label, so
// both sides are trimmed; a row left empty on both sides is dropped.
function toDoc(ui) {
  const ar = {};
  for (const r of ui.rows) {
    const en = r.en.trim();
    if (en || r.ar.trim()) ar[en] = r.ar.trim();
  }
  return Object.assign({}, ui.rest, { ar });
}

// What a save would lose or the server would refuse, found before sending:
// Arabic with no English, and English that is already in the list.
function rowProblems(rows) {
  const out = [];
  const seen = new Set();
  rows.forEach((r, i) => {
    const en = r.en.trim();
    if (!en) {
      if (r.ar.trim()) out.push({ path: "row:" + i + ":en", message: "Write the English text this translates, or remove the entry." });
    } else if (seen.has(en)) {
      out.push({ path: "row:" + i + ":en", message: "This English text is already in the list." });
    } else seen.add(en);
  });
  return out;
}

function validationError(details) {
  const e = new Error("Some fields need attention.");
  e.code = "validation";
  e.details = details;
  return e;
}

// Every text a visitor can meet on the built site, read from the preview the
// way a browser gets it: text directly inside the elements the toggle looks
// in, on every page; every text value in catalogue.js except the dictionary
// itself, which names every entry; and shop.js, for the labels it writes
// while someone shops.
async function siteTexts(pages) {
  const get = async (path) => {
    const r = await fetch("/" + path, { cache: "no-store", credentials: "same-origin" });
    if (!r.ok) throw new Error("The preview answered " + r.status + " for " + path + ".");
    return r.text();
  };
  const [htmls, cat, shop] = await Promise.all([Promise.all(pages.map(get)), get("assets/catalogue.js"), get("assets/shop.js")]);
  const texts = new Set();
  const add = (s) => { const t = String(s).trim(); if (t) texts.add(t); };
  for (const src of htmls) {
    const doc = new DOMParser().parseFromString(src, "text/html");
    doc.querySelectorAll(SWAPPED).forEach((el) => {
      for (const n of el.childNodes) if (n.nodeType === 3) add(n.nodeValue);
    });
  }
  const walk = (o) => { if (typeof o === "string") add(o); else if (o && typeof o === "object") Object.values(o).forEach(walk); };
  for (const line of cat.split("\n")) {
    const m = line.match(/^window\.([A-Za-z_]\w*) = (.*);$/);
    if (!m || m[1] === "BGS_AR") continue;
    try { walk(JSON.parse(m[2])); } catch (e) { /* not JSON: nothing to read */ }
  }
  return { texts, shop };
}

const onSite = (en, site) => site.texts.has(en) ||
  site.shop.includes('"' + en + '"') || site.shop.includes("'" + en + "'") || site.shop.includes(">" + en + "<");

export function render(main, { app }) {
  useCss("translations");
  const res = app.state.schema.resources.translations;
  const f = res.fields.find((x) => x.type === "dictionary") || { path: "/ar" };
  let view = "all";             // all, missing or unused
  let q = "";
  let site = null;              // the built site's texts once read, or { error }
  let redraw = () => {};
  const prodCard = h("section", { class: "card tr-products", "aria-labelledby": "tr-prod-h" });

  // A save sends the stored shape; the answer, and the other version a 412
  // carries, come back as rows. Problems are shown on the rows they are
  // about, with the filters cleared so every such row is on screen.
  async function put(ui, rev) {
    const probs = rowProblems(ui.rows);
    if (probs.length) { view = "all"; q = ""; redraw(); throw validationError(probs); }
    try {
      const r = await api("PUT", "documents/translations", { body: { data: toDoc(ui) }, rev });
      return Object.assign({}, r, { data: toRows(r.data) });
    } catch (e) {
      if (e.code === "stale_rev" && e.details && e.details.current) e.details.current = toRows(e.details.current);
      if (e.code === "validation" && Array.isArray(e.details)) {
        view = "all"; q = ""; redraw();
        e.details = e.details.map((d) => {
          const i = d.key === undefined ? -1 : ui.rows.findIndex((r) => r.en.trim() === d.key);
          return i < 0 ? d : Object.assign({}, d, { path: "row:" + i + ":" + (d.part === "value" ? "ar" : "en") });
        });
      }
      throw e;
    }
  }

  mountEditor(main, app, {
    heading: res.resource.label,
    subtitle: res.resource.intro || null,
    load: async () => { const d = await api("GET", "documents/translations"); return { rev: d.rev, data: toRows(d.data), meta: d }; },
    put,
    view: () => "/",
    actions: () => [h("a", { class: "btn", href: "/", target: "_blank", rel: "noopener noreferrer" }, "View store")],
    form: (ctx, data) => dictionaryCard(ctx, data.rows),
  });
  main.append(prodCard);
  drawProducts();
  siteTexts(app.state.schema.pages || [])
    .then((s) => { site = s; })
    .catch((e) => { site = { error: e.message }; })
    .then(() => redraw());

  function dictionaryCard(ctx, rows) {
    const missing = (r) => !!r.en.trim() && !r.ar.trim();
    const unused = (r) => !!site && !site.error && !!r.en.trim() && !onSite(r.en.trim(), site);
    const VIEWS = [["all", "All", () => true], ["missing", "Missing", missing], ["unused", "Not used on the site", unused]];
    const tbody = h("tbody");
    const cover = h("div", { class: "tr-cover" });
    const pills = h("div", { class: "tr-views", role: "group", "aria-label": "Show" });
    const note = h("p", { class: "hint" });
    const cardErr = h("p", { class: "error", hidden: true });
    const intro = h("div", { class: "tr-intro" },
      h("h2", { id: "tr-dict-h" }, "Shop labels"),
      h("p", { class: "sub" }, "When a visitor switches to Arabic, each English text below is replaced by its Arabic wherever a page shows exactly that text. " + (f.help || "")),
      cover, cardErr);
    const search = h("input", { class: "input", type: "search", value: q, placeholder: "Search English or Arabic", "aria-label": "Search entries",
      oninput: (e) => { q = e.target.value; drawTable(); } });
    const addBtn = h("button", { class: "btn", type: "button", onclick: addRow }, icon("plus", 16), "Add an entry");
    ctx.slots.set(f.path, { err: cardErr, wrap: intro });

    function changed() { ctx.onChange(); drawCover(); drawPills(); }

    function drawCover() {
      const named = rows.filter((r) => r.en.trim());
      const done = named.filter((r) => r.ar.trim()).length;
      const pct = named.length ? Math.floor((done / named.length) * 100) : 0;
      append(clear(cover), [
        h("p", {}, named.length ? [h("b", {}, done + " of " + named.length), (named.length === 1 ? " entry has" : " entries have") + " Arabic (" + pct + "%)"] : "No entries yet."),
        named.length ? h("div", { class: "tr-bar", role: "img", "aria-label": pct + "% translated" }, h("span", { style: { width: pct + "%" } })) : null]);
      addBtn.disabled = f.max !== undefined && rows.length >= f.max;
      addBtn.title = addBtn.disabled ? "The dictionary holds up to " + f.max + " entries." : "";
    }

    function drawPills() {
      append(clear(pills), VIEWS.map(([k, label, test]) => {
        const off = k === "unused" && (!site || !!site.error);
        return h("button", { class: "btn small", type: "button", "aria-pressed": String(view === k), disabled: off,
          onclick: () => { view = k; drawPills(); drawTable(); } }, label + (off ? "" : " (" + rows.filter(test).length + ")"));
      }));
    }

    function drawNote() {
      clear(note).append(!site ? "Checking which entries the site uses." : site.error
        ? "Could not check which entries the site uses: " + site.error
        : "Not used on the site: that exact English is on no page the build writes, and not in catalogue.js or shop.js, so the switch has nothing to replace. The check reads the built files: text put together while someone shops can be missed, so look at the page before removing an entry.");
    }

    function emptyText() {
      if (q.trim()) return "No entries match your search.";
      if (view === "missing") return "Every entry has Arabic.";
      if (view === "unused") return "Every entry's English is on the site.";
      return "The dictionary is empty. Add an entry to start.";
    }

    function rowEl(r, i) {
      const enErr = h("p", { class: "error", id: "tr-en-err" + i, hidden: true });
      const arErr = h("p", { class: "error", id: "tr-ar-err" + i, hidden: true });
      const state = h("td", { class: "tr-state" });
      const name = () => r.en.trim() || "entry " + (i + 1);
      const del = iconBtn("trash", "Remove " + name(), false, (e) => removeRow(i, e.currentTarget));
      const ar = h("input", { class: "input", type: "text", dir: f.dir || "rtl", lang: "ar", value: r.ar, maxlength: f.maxLength || null,
        autocomplete: "off", "aria-label": "Arabic for " + name(), "aria-describedby": arErr.id,
        oninput: (e) => { r.ar = e.target.value; changed(); drawState(); } });
      const en = h("input", { class: "input", type: "text", value: r.en, maxlength: f.keyMaxLength || null, autocomplete: "off",
        "aria-label": "English, entry " + (i + 1), "aria-describedby": enErr.id,
        oninput: (e) => {
          r.en = e.target.value;
          ar.setAttribute("aria-label", "Arabic for " + name());
          del.setAttribute("aria-label", "Remove " + name());
          del.title = "Remove " + name();
          changed();
          drawState();
        } });
      const drawState = () => append(clear(state), [
        missing(r) ? h("span", { class: "badge gold" }, "Missing") : null,
        unused(r) ? h("span", { class: "badge outline" }, "Not used on the site") : null]);
      drawState();
      const enCell = h("td", { class: "tr-en" }, en, enErr);
      const arCell = h("td", { class: "tr-ar" }, ar, arErr);
      ctx.slots.set("row:" + i + ":en", { err: enErr, wrap: enCell });
      ctx.slots.set("row:" + i + ":ar", { err: arErr, wrap: arCell });
      return h("tr", {}, enCell, arCell, state, h("td", { class: "t-move" }, del));
    }

    function drawTable() {
      for (const k of [...ctx.slots.keys()]) if (k.startsWith("row:")) ctx.slots.delete(k);
      const needle = q.trim().toLowerCase();
      const test = VIEWS.find((v) => v[0] === view)[2];
      const shown = [];
      rows.forEach((r, i) => {
        if (test(r) && (!needle || r.en.toLowerCase().includes(needle) || r.ar.toLowerCase().includes(needle))) shown.push(rowEl(r, i));
      });
      append(clear(tbody), shown.length ? shown : h("tr", {}, h("td", { colspan: "4", class: "empty" }, emptyText())));
    }

    function addRow() {
      rows.push({ en: "", ar: "" });
      view = "all";
      q = "";
      search.value = "";
      changed();
      drawTable();
      const first = tbody.lastElementChild && tbody.lastElementChild.querySelector("input");
      if (first) { first.scrollIntoView({ block: "center" }); first.focus(); }
    }

    // Focus goes to the next row's remove button, so removing several in a
    // row is one key press each.
    function removeRow(i, btn) {
      const pos = Array.prototype.indexOf.call(tbody.children, btn.closest("tr"));
      const gone = rows.splice(i, 1)[0];
      changed();
      drawTable();
      const btns = tbody.querySelectorAll(".icon-btn");
      (btns[pos] || btns[pos - 1] || search).focus();
      announce((gone.en.trim() ? "Removed " + gone.en.trim() : "Removed the entry") + ". Save to apply.");
    }

    redraw = () => { search.value = q; drawCover(); drawPills(); drawTable(); drawNote(); };
    redraw();
    return h("section", { class: "card flush tr-dict", "aria-labelledby": "tr-dict-h" }, intro,
      h("div", { class: "toolbar" }, h("label", { class: "search" }, icon("search", 16), search), pills, addBtn),
      h("div", { class: "table-wrap" }, h("table", { class: "table tr-table" },
        h("thead", {}, h("tr", {},
          h("th", { scope: "col" }, f.keyLabel || "English"), h("th", { scope: "col" }, f.valueLabel || "Arabic"),
          h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Status")),
          h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Remove")))),
        tbody)),
      note);
  }

  // Products carry their own Arabic, which the shop does not show yet; this
  // card only counts it and links to each product's page to write it.
  async function drawProducts() {
    const head = [h("div", { class: "tr-card-head" }, h("h2", { id: "tr-prod-h" }, "Products in Arabic"),
      h("span", { class: "badge outline", title: "Saved, but the shop does not show this yet." }, "Not on the site yet")),
    h("p", { class: "sub" }, "Each product has its own Arabic name and story, written on the product's page. They are saved with the product, but the shop does not show them yet: the language switch changes the labels above, not products.")];
    append(clear(prodCard), [head, h("p", { class: "muted" }, "Loading products.")]);
    let list;
    try { list = await api("GET", "products"); } catch (e) { append(clear(prodCard), [head, banner({ tone: "critical", title: e.message })]); return; }
    const items = list.items;
    const lines = (a) => (Array.isArray(a) ? a : []).filter((s) => typeof s === "string" && s.trim()).length;
    const hasName = (d) => typeof d.name_ar === "string" && !!d.name_ar.trim();
    const gap = (d) => !hasName(d) || (lines(d.story) > 0 && !lines(d.story_ar));
    const withStory = items.filter((it) => lines(it.data.story));
    const named = items.filter((it) => hasName(it.data)).length;
    const told = withStory.filter((it) => lines(it.data.story_ar)).length;
    let only = false;
    const tbody = h("tbody");
    const draw = () => {
      const shown = items.filter((it) => !only || gap(it.data));
      append(clear(tbody), shown.length ? shown.map(({ id, data: d }) => h("tr", {},
        h("td", {}, h("a", { class: "t-name", href: "#/products/" + id }, d.name || id), d.published === false ? [" ", h("span", { class: "badge muted" }, "Draft")] : null),
        h("td", {}, hasName(d) ? h("span", { dir: "rtl", lang: "ar" }, d.name_ar) : h("span", { class: "badge gold" }, "Missing")),
        h("td", {}, storyCell(lines(d.story), lines(d.story_ar)))))
        : h("tr", {}, h("td", { colspan: "3", class: "empty" }, items.length ? "Every product has its Arabic name and story." : "No products yet.")));
    };
    append(clear(prodCard), [head,
      h("div", { class: "stats" },
        h("div", { class: "stat" }, h("b", {}, named + " of " + items.length), h("span", {}, "products have an Arabic name")),
        h("div", { class: "stat" }, h("b", {}, told + " of " + withStory.length), h("span", {}, "stories have Arabic"))),
      h("label", { class: "check tr-only" }, h("input", { type: "checkbox", onchange: (e) => { only = e.target.checked; draw(); } }), "Only products missing Arabic"),
      h("div", { class: "table-wrap" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Product"), h("th", { scope: "col" }, "Arabic name"), h("th", { scope: "col" }, "Arabic story"))),
        tbody))]);
    draw();
  }
}

function storyCell(en, ar) {
  if (!en && !ar) return h("span", { class: "muted" }, "No story");
  if (!ar) return h("span", { class: "badge gold" }, "Missing");
  return en ? ar + " of " + en + " lines" : ar + (ar === 1 ? " line" : " lines");
}
