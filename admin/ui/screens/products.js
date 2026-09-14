// All products: search, filter, the first photo, price, stock and status,
// reorder within a category, and adding a new product (created as a draft).
import { api } from "../lib/api.js";
import { h, clear, thumb } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, formDialog, toast, guard } from "../lib/ui.js";
import { iconBtn } from "../lib/forms.js";

// the names the shop shows today (navigation.json); the stored keys stay as they are
const CATS = { attars: "Oud Attar", edp: "EDP Sprays", bakhoor: "Bakhoor", "gift-sets": "Gift Sets" };

function priceText(d) {
  if (Array.isArray(d.sizes) && d.sizes.length > 1) {
    const ps = d.sizes.map((s) => s.price);
    return "AED " + Math.min(...ps) + " to " + Math.max(...ps);
  }
  return "AED " + d.price;
}

function slug(s) {
  return String(s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

export async function render(main, { app }) {
  guard.clear();
  const f = { q: "", category: "", status: "" };
  let data = null;
  const table = h("div", { class: "table-wrap" });
  const note = h("div", { class: "msgs" });

  const toolbar = h("div", { class: "toolbar" },
    h("label", { class: "search" }, icon("search", 16),
      h("input", { class: "input", type: "search", placeholder: "Search products", "aria-label": "Search products",
        oninput: (e) => { f.q = e.target.value.trim().toLowerCase(); draw(); } })),
    h("select", { class: "input", "aria-label": "Category", onchange: (e) => { f.category = e.target.value; draw(); } },
      h("option", { value: "" }, "All categories"), Object.entries(CATS).map(([k, v]) => h("option", { value: k }, v))),
    h("select", { class: "input", "aria-label": "Status", onchange: (e) => { f.status = e.target.value; draw(); } },
      h("option", { value: "" }, "Active and draft"), h("option", { value: "active" }, "Active"), h("option", { value: "draft" }, "Draft")));

  clear(main).append(
    h("div", { class: "page-head" },
      h("div", {}, h("h1", { tabindex: "-1" }, "Products"), h("p", { class: "sub" }, "Everything in the shop. Drafts are hidden from the shop, not from the public GitHub repository.")),
      h("div", { class: "head-actions" }, h("button", { class: "btn primary", type: "button", onclick: add }, icon("plus", 16), "Add product"))),
    note, h("section", { class: "card flush" }, toolbar, table));

  async function load() {
    data = await api("GET", "products");
    app.state.products = Object.fromEntries(data.items.map((it) => [it.id, it.data]));
    draw();
  }

  function rows() {
    return data.items.filter(({ id, data: d }) => {
      const active = d.published !== false;
      if (f.category && d.category !== f.category) return false;
      if (f.status === "active" && !active) return false;
      if (f.status === "draft" && active) return false;
      if (f.q && !id.includes(f.q) && !(d.name || "").toLowerCase().includes(f.q)) return false;
      return true;
    });
  }

  function draw() {
    const list = rows();
    const canMove = !!f.category && !f.q && !f.status;
    clear(table);
    if (!list.length) { table.append(h("p", { class: "empty" }, "No products match.")); return; }
    table.append(h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", {}, h("span", { class: "sr-only" }, "Photo")), h("th", {}, "Product"), h("th", {}, "Status"),
        h("th", {}, "Category"), h("th", {}, "Price"), h("th", {}, "Stock"), canMove ? h("th", {}, h("span", { class: "sr-only" }, "Order")) : null)),
      h("tbody", {}, list.map(({ id, data: d }, i) => h("tr", {},
        h("td", { class: "t-img" }, d.images && d.images.length ? h("img", { src: thumb(d.images[0]), alt: "", width: "44", height: "44", loading: "lazy" }) : h("span", { class: "noimg" }, icon("image", 16))),
        h("td", {}, h("a", { href: "#/products/" + id, class: "t-name" }, d.name || id), h("span", { class: "t-id" }, id)),
        h("td", {}, d.published === false ? h("span", { class: "badge muted" }, "Draft") : h("span", { class: "badge green" }, "Active")),
        h("td", {}, CATS[d.category] || d.category),
        h("td", { class: "num" }, priceText(d)),
        h("td", {}, d.stock === null || d.stock === undefined ? h("span", { class: "muted" }, "Not tracked")
          : d.stock <= 5 ? h("span", { class: "badge red" }, d.stock + " left") : String(d.stock)),
        canMove ? h("td", { class: "t-move" },
          iconBtn("up", "Move " + (d.name || id) + " up", i === 0, () => move(list, i, -1)),
          iconBtn("down", "Move " + (d.name || id) + " down", i === list.length - 1, () => move(list, i, 1))) : null)))));
    if (!canMove) table.append(h("p", { class: "hint" }, "Pick a category to change the order products appear in."));
  }

  async function move(list, i, d) {
    const ids = list.map((x) => x.id);
    const [x] = ids.splice(i, 1);
    ids.splice(i + d, 0, x);
    try {
      await api("POST", "products/reorder", { body: { category: f.category, ids, expect_collection_rev: data.collection_rev } });
      toast("Order saved. The site rebuilt.");
      await load();
    } catch (e) {
      clear(note).append(banner({ tone: "critical", title: e.message }));
      await load();
    }
  }

  async function add() {
    const v = await formDialog({
      title: "Add a product", body: "It starts as a draft, hidden from the shop until you make it active.", confirm: "Create draft",
      fields: [
        { name: "name", label: "Title", required: true },
        { name: "category", label: "Category", options: Object.entries(CATS).map(([k, l]) => ({ value: k, label: l })), value: "attars" },
        { name: "price", label: "Price (AED)", required: true, pattern: "[0-9]+" },
        { name: "size", label: "Size or contents", placeholder: "6 ml, 50 ml, 40 g or 3 x 3 ml", required: true },
        { name: "id", label: "Web address id", placeholder: "made from the title if left empty", hint: "Lower-case letters, digits and hyphens. It cannot be changed later." },
      ],
    });
    if (!v) return;
    const id = v.id || slug(v.name);
    const price = Math.trunc(Number(v.price));
    const d = { name: v.name, category: v.category, price };
    if (v.category === "attars") d.sizes = [{ label: v.size, price }];
    else if (v.category === "gift-sets") d.contents = v.size;
    else d.size = v.size;
    if (v.category === "edp") d.gender = "Unisex";
    try {
      await api("POST", "products", { body: { id, data: d } });
      toast("Draft created.");
      location.hash = "#/products/" + id;
    } catch (e) {
      const items = e.details && Array.isArray(e.details) ? e.details.map((x) => x.message) : [];
      clear(note).append(banner({ tone: "critical", title: e.message, items }));
    }
  }

  try { await load(); } catch (e) { clear(table).append(banner({ tone: "critical", title: e.message })); }
}
