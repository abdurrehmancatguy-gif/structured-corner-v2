// Pages: the words on the shop's fixed pages, one page at a time. The list
// comes from the schema (resources.pages.resource.groups), where each page
// names the storefront page it opens; checkout and the order confirmation
// are listed with a lock, because their words stay in code with payments
// and VAT. One page (#/content/pages/<key>) opens in the shared editor over
// documents/pages: only that page's fields are drawn, under its sections'
// headings, and a save writes the whole document and rebuilds the site.
import { api } from "../lib/api.js";
import { h, clear, useCss, getPtr, setPtr, copy } from "../lib/dom.js";
import { mountEditor } from "../lib/editor.js";
import { field, visible } from "../lib/forms.js";
import { banner, guard } from "../lib/ui.js";
import { icon } from "../icons.js";

const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

export function render(main, { sub, app }) {
  useCss("pages");
  const res = app.state.schema.resources.pages;
  if (!res || !Array.isArray(res.resource.groups)) {
    guard.clear();
    clear(main).append(h("h1", { tabindex: "-1" }, "Pages"),
      banner({ tone: "critical", title: "The server did not describe the pages.", items: ["Restart the admin and reload this page."] }));
    return;
  }
  const groups = res.resource.groups;
  if (!sub) return list(main, app, res, groups);
  const g = groups.find((x) => x.key === sub);
  if (!g) return missing(main, sub);
  if (g.locked) return locked(main, app, g);
  return detail(main, app, res, g);
}

// The storefront address a page's "View page" opens. The product page shows
// a product only when the address names one, so it names the first published
// product the admin has loaded; before that list arrives it opens the bare
// page, which says the product was not found.
function pageHref(app, g) {
  if (g.page === "product.html") {
    const all = app.state.products || {};
    const first = Object.keys(all).find((id) => all[id] && all[id].published !== false);
    if (first) return "/product.html?p=" + encodeURIComponent(first);
  }
  return "/" + g.page;
}

function viewLink(app, g) {
  // The product list can arrive after the link is drawn, so the address is
  // worked out again just before it is used.
  const refresh = (e) => { e.currentTarget.href = pageHref(app, g); };
  return h("a", { class: "btn", href: pageHref(app, g), target: "_blank", rel: "noopener noreferrer",
    "aria-label": "View " + g.label + " on the store", onpointerenter: refresh, onfocus: refresh },
  icon("external", 16), "View page");
}

function list(main, app, res, groups) {
  guard.clear();
  const counts = new Map();
  for (const f of res.fields) counts.set(f.group, (counts.get(f.group) || 0) + 1);
  clear(main).append(
    h("div", { class: "page-head" },
      h("div", {}, h("h1", { tabindex: "-1" }, "Pages"), h("p", { class: "sub" }, res.resource.intro))),
    h("ul", { class: "pg-list" }, groups.map((g) => (g.locked ? lockedItem(app, g) : item(app, g, counts.get(g.label) || 0)))));
}

function item(app, g, n) {
  return h("li", { class: "card pg-item" },
    h("div", { class: "pg-body" },
      h("h2", {}, h("a", { href: "#/content/pages/" + encodeURIComponent(g.key) }, g.label)),
      g.about ? h("p", { class: "pg-about" }, g.about) : null,
      h("p", { class: "pg-meta" }, n ? plural(n, "field", "fields") : "No fields yet.")),
    h("div", { class: "pg-actions" }, viewLink(app, g)));
}

function lockedItem(app, g) {
  return h("li", { class: "card locked pg-item" },
    h("div", { class: "pg-body" },
      h("h2", {}, g.label),
      h("p", { class: "pg-lockline" }, h("span", { class: "badge lock" }, icon("lock", 12), "Locked"), " ", g.locked + "."),
      g.about ? h("p", { class: "pg-meta" }, g.about) : null),
    h("div", { class: "pg-actions" }, viewLink(app, g)));
}

function head(app, g, extra) {
  return h("div", { class: "page-head" },
    h("div", {}, h("a", { class: "back", href: "#/content/pages" }, "Pages"), h("h1", { tabindex: "-1" }, g.label),
      g.about ? h("p", { class: "sub" }, g.about) : null),
    h("div", { class: "head-actions" }, extra));
}

function missing(main, key) {
  guard.clear();
  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("a", { class: "back", href: "#/content/pages" }, "Pages"),
      h("h1", { tabindex: "-1" }, "Page not found"))),
    banner({ tone: "critical", title: "There is no page called " + key + ".", items: ["Pick one from the list of pages."] }));
}

function locked(main, app, g) {
  guard.clear();
  clear(main).append(head(app, g, viewLink(app, g)),
    h("section", { class: "card locked" },
      h("h2", {}, h("span", { class: "badge lock" }, icon("lock", 12), "Locked")),
      h("p", { class: "pg-note" }, g.locked + ". Nothing on this page can be edited here.")));
}

function detail(main, app, res, g) {
  const fields = res.fields.filter((f) => f.group === g.label);
  mountEditor(main, app, {
    back: { href: "#/content/pages", label: "Pages" },
    heading: g.label,
    subtitle: (g.about ? g.about + " " : "") + "Saving rebuilds the site.",
    load: async () => { const d = await api("GET", "documents/pages"); return { rev: d.rev, data: d.data, meta: d }; },
    put: (data, rev) => api("PUT", "documents/pages", { body: { data }, rev }),
    // The draft is the whole document but the screen shows one page, so
    // "Save mine over it" takes only this page's fields over to the newer
    // copy: the other pages keep what was saved elsewhere in the meantime.
    rebase: (current, draft) => {
      for (const f of fields) {
        const v = getPtr(draft, f.path);
        if (v !== undefined) setPtr(current, f.path, copy(v));
      }
      return current;
    },
    view: () => pageHref(app, g),
    actions: () => [viewLink(app, g)],
    form: (ctx, data) => {
      ctx.root = data;
      if (!fields.length) return h("p", { class: "empty" }, "This page has no fields yet.");
      // Fields keep the schema's order; a section's heading comes where its
      // first field does. Fields with no section sit in a card of their own.
      const sections = new Map();
      for (const f of fields) {
        if (!visible(f, data)) continue;
        const s = f.section || "";
        if (!sections.has(s)) sections.set(s, []);
        sections.get(s).push(f);
      }
      return h("div", { class: "cards pg-form" }, [...sections].map(([s, fs]) =>
        h("section", { class: "card" }, s ? h("h2", {}, s) : null, fs.map((f) => field(f, data, f.path, ctx)))));
    },
  });
}
