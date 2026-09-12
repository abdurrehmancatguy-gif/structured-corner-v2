// Collections: the four categories the shop is built around, and its
// all-products page. The list shows each one's name, intro, product count
// and circle picture. One collection opens with its words, its homepage
// circle and shelf, and its products in the shop's order. A save writes Site
// text, Homepage and Navigation together (PUT collections/<key>); moving a
// product saves at once through products/reorder. The categories themselves
// are code, so none can be added here.
import { api } from "../lib/api.js";
import { h, clear, thumb, useCss } from "../lib/dom.js";
import { mountEditor } from "../lib/editor.js";
import { field, iconBtn } from "../lib/forms.js";
import { banner, toast, guard } from "../lib/ui.js";
import { icon } from "../icons.js";

const NO_ADD = "Categories are wired into the shop's code: filters, card lines and breadcrumbs.";

// The collection keys the server's schema knows, in its order: one set of
// Site text fields per key, so nothing here lists them by hand.
function keys(app) {
  return app.state.schema.resources.copy.fields
    .map((f) => (f.path.match(/^\/categories\/([^/]+)\/label$/) || [])[1]).filter(Boolean);
}

const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

export function render(main, ctx) {
  useCss("collections");
  if (!ctx.sub) return list(main, ctx);
  if (!keys(ctx.app).includes(ctx.sub)) return missing(main, ctx.sub);
  return detail(main, ctx);
}

function missing(main, key) {
  guard.clear();
  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("a", { class: "back", href: "#/collections" }, "Collections"),
      h("h1", { tabindex: "-1" }, "Collection not found"))),
    banner({ tone: "critical", title: "There is no collection called " + key + ".",
      items: ["The shop's collections are its four categories and the all-products page."] }));
}

async function list(main) {
  guard.clear();
  const msgs = h("div", { class: "msgs" });
  const grid = h("div", { class: "coll-grid" });
  clear(main).append(
    h("div", { class: "page-head" },
      h("div", {}, h("h1", { tabindex: "-1" }, "Collections"),
        h("p", { class: "sub" }, "The shop's categories and its all-products page: their names and intros, their homepage circles and shelves, and the order of their products.")),
      h("div", { class: "head-actions coll-add" },
        h("button", { class: "btn", type: "button", disabled: true, "aria-describedby": "coll-add-why" }, icon("plus", 16), "Add collection"),
        h("p", { class: "help", id: "coll-add-why" }, NO_ADD))),
    msgs, grid);
  let res;
  try {
    res = await api("GET", "collections");
  } catch (e) {
    msgs.append(banner({ tone: "critical", title: "The collections did not load.", items: [e.message] }));
    return;
  }
  grid.append(...res.items.map(card));
}

function card(it) {
  const d = it.data;
  const circle = d.circle || {};
  const facts = [plural(it.published, "product", "products") + " on the site"];
  if (it.drafts) facts.push(plural(it.drafts, "draft", "drafts"));
  if (it.shelf_shows) facts.push("homepage shelf of " + plural(it.shelf_shows.cards, "card", "cards"));
  return h("section", { class: "card coll-card" },
    h("div", { class: "coll-pic" + (circle.cutout ? " cut" : "") },
      circle.image ? h("img", { src: "/" + circle.image, alt: "", width: "72", height: "72", loading: "lazy" })
        : icon(it.key === "all" ? "grid" : "image", 22)),
    h("div", { class: "coll-body" },
      h("h2", {}, h("a", { href: "#/collections/" + it.key }, d.label || it.name)),
      it.key === "all" ? h("p", { class: "coll-kind" }, "All-products page") : null,
      d.intro ? h("p", { class: "coll-intro" }, d.intro) : h("p", { class: "coll-intro muted" }, "No intro yet."),
      h("p", { class: "coll-meta" }, facts.join(", ") + ".")));
}

function priceText(d) {
  if (Array.isArray(d.sizes) && d.sizes.length > 1) {
    const ps = d.sizes.map((s) => s.price);
    return "AED " + Math.min(...ps) + " to " + Math.max(...ps);
  }
  return "AED " + d.price;
}

const ARROW = String.fromCharCode(0x2192);

function detail(main, { sub: key, app }) {
  let meta = null;
  const prodCard = h("section", { class: "card" });
  mountEditor(main, app, {
    back: { href: "#/collections", label: "Collections" },
    heading: (d) => (d && d.label) || key,
    subtitle: "Saving updates Site text, Homepage and Navigation together and rebuilds the site.",
    load: async () => {
      meta = await api("GET", "collections/" + key);
      return { rev: meta.rev, data: meta.data, meta };
    },
    put: (data, rev) => api("PUT", "collections/" + key, { body: { data }, rev }),
    view: () => "/" + meta.href,
    actions: () => [h("a", { class: "btn", href: "/" + meta.href, target: "_blank", rel: "noopener noreferrer" }, icon("external", 16), "View on store")],
    form: (ctx, data, m) => {
      ctx.root = data;
      const defs = new Map(m.fields.map((f) => [f.path, f]));
      const put = (p) => (defs.has(p) ? field(defs.get(p), data, p, ctx) : null);
      const shelfNote = h("p", { class: "coll-preview" });
      // What the homepage will draw, worked out as build.py does: the first
      // cards up to the limit, and the link with {n} counted.
      const refresh = () => {
        const s = data.shelf;
        if (!s) return;
        const n = m.published;
        const cards = Number.isInteger(s.limit) ? Math.min(s.limit, n) : n;
        const link = String(s.link_label || "").split("{n}").join(String(n));
        shelfNote.textContent = "The homepage shows " + plural(cards, "card", "cards") + " of the " + n +
          " published, then a link that reads " + link + " " + ARROW + ".";
      };
      const none = (what) => h("p", { class: "muted" }, key === "all" ? "The all-products page has no " + what + " of its own." : "No " + what + " on the homepage belongs to this collection.");
      const words = h("section", { class: "card" }, h("h2", {}, "Name and intro"), put("/label"), put("/crumb"), put("/intro"));
      const shelf = h("section", { class: "card" }, h("h2", {}, "Homepage shelf"),
        data.shelf ? [put("/shelf/heading"), put("/shelf/limit"), put("/shelf/link_label"), shelfNote] : none("shelf"));
      const circle = h("section", { class: "card" }, h("h2", {}, "Homepage circle"),
        data.circle ? [h("p", { class: "sub coll-sub" }, "The circle under the homepage banner and the link in the category bar."),
          put("/circle/label"), put("/circle/tint"), put("/circle/cutout"), put("/circle/image")] : none("circle"));
      const wrap = h("div", {}, h("div", { class: "two-col" }, h("div", {}, words, shelf), h("div", {}, circle)), prodCard);
      wrap.addEventListener("input", refresh);
      wrap.addEventListener("change", refresh);
      refresh();
      return wrap;
    },
  });
  productsCard(prodCard, key);
}

// The collection's products in the shop's order, each moved up or down with
// a save at once (products/reorder, guarded by the product list's rev).
// Every category keeps its own order, so the all-products page points there.
function productsCard(box, key) {
  if (key === "all") {
    clear(box).append(h("h2", {}, "Products"),
      h("p", { class: "coll-note" }, "Every published product is on this page. Each category keeps its own order: open a category to change it."));
    return;
  }
  let data = null;
  let focusAfter = null;
  let moving = false;
  const msgs = h("div", { class: "msgs" });
  const table = h("div", { class: "table-wrap" });
  clear(box).append(h("h2", {}, "Products"),
    h("p", { class: "sub coll-sub" }, "In the shop's order, which the collection page and the homepage shelf follow. A move saves at once and rebuilds the site."),
    msgs, table);

  const load = async () => {
    data = await api("GET", "products?category=" + encodeURIComponent(key));
    draw();
  };
  const moveBtn = (items, i, dir) => {
    const { id, data: d } = items[i];
    const b = iconBtn(dir < 0 ? "up" : "down", "Move " + (d.name || id) + (dir < 0 ? " up" : " down"),
      dir < 0 ? i === 0 : i === items.length - 1, () => move(i, dir));
    b.dataset.move = id + (dir < 0 ? ":up" : ":down");
    return b;
  };
  function draw() {
    clear(table);
    const items = data.items;
    if (!items.length) { table.append(h("p", { class: "empty" }, "No products in this collection yet.")); return; }
    table.append(h("table", { class: "table" },
      h("caption", { class: "sr-only" }, "Products in this collection, in the shop's order"),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Photo")), h("th", { scope: "col" }, "Product"),
        h("th", { scope: "col" }, "Status"), h("th", { scope: "col" }, "Price"), h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Order")))),
      h("tbody", {}, items.map(({ id, data: d }, i) => h("tr", {},
        h("td", { class: "t-img" }, d.images && d.images.length ? h("img", { src: thumb(d.images[0]), alt: "", width: "44", height: "44", loading: "lazy" }) : h("span", { class: "noimg" }, icon("image", 16))),
        h("td", {}, h("a", { href: "#/products/" + id, class: "t-name" }, d.name || id), h("span", { class: "t-id" }, id)),
        h("td", {}, d.published === false ? h("span", { class: "badge muted" }, "Draft") : h("span", { class: "badge green" }, "Active")),
        h("td", { class: "num" }, priceText(d)),
        h("td", { class: "t-move" }, moveBtn(items, i, -1), moveBtn(items, i, 1)))))));
    if (focusAfter) {
      // Keep the keyboard on the product that moved. At the top or the
      // bottom its button that way is switched off, so the other one takes it.
      const other = focusAfter.endsWith(":up") ? focusAfter.replace(/:up$/, ":down") : focusAfter.replace(/:down$/, ":up");
      let b = table.querySelector('[data-move="' + focusAfter + '"]');
      if (!b || b.disabled) b = table.querySelector('[data-move="' + other + '"]');
      if (b) b.focus();
      focusAfter = null;
    }
  }
  async function move(i, dir) {
    // One move at a time: a second click while the reorder is in flight would
    // send the list as it was before the reload and be refused, showing "not
    // saved" although the first move saved. The next click acts on the
    // reloaded list.
    if (moving) return;
    moving = true;
    const ids = data.items.map((x) => x.id);
    const [x] = ids.splice(i, 1);
    ids.splice(i + dir, 0, x);
    focusAfter = x + (dir < 0 ? ":up" : ":down");
    clear(msgs);
    try {
      await api("POST", "products/reorder", { body: { category: key, ids, expect_collection_rev: data.collection_rev } });
      toast("Order saved. The site rebuilt.");
    } catch (e) {
      msgs.append(banner({ tone: "critical", title: "The order was not saved.", items: [e.message] }));
    }
    try { await load(); } catch (e) { msgs.append(banner({ tone: "critical", title: e.message })); }
    moving = false;
  }
  load().catch((e) => msgs.append(banner({ tone: "critical", title: "The products did not load.", items: [e.message] })));
}
