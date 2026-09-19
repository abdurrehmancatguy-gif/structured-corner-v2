// One product: the fields in two columns, as the Shopify product page lays
// them out, with the actions that need their own confirmation.
import { api, storeUrl } from "../lib/api.js";
import { h, clear } from "../lib/dom.js";
import { icon } from "../icons.js";
import { mountEditor } from "../lib/editor.js";
import { field, visible } from "../lib/forms.js";
import { banner, confirmDialog, formDialog, toast, guard } from "../lib/ui.js";
import { mediaGrid } from "../components/media-grid.js";

export function render(main, { arg: pid, app }) {
  const F = Object.fromEntries(app.state.schema.resources.products.fields.map((f) => [f.path, f]));
  let refs = [];
  const card = (title, ...kids) => {
    const k = kids.flat().filter(Boolean);
    return k.length ? h("section", { class: "card" }, h("h2", {}, title), k) : null;
  };
  const store = (d) => storeUrl("product.html?p=" + encodeURIComponent(pid));

  const ed = mountEditor(main, app, {
    back: { href: "#/products", label: "Products" },
    heading: (d) => (d && d.name) || pid,
    load: async () => {
      const [d, list] = await Promise.all([api("GET", "products/" + pid), app.state.products ? null : api("GET", "products")]);
      if (list) app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
      refs = d.refs || [];
      return { rev: d.rev, data: d.data };
    },
    put: (data, rev, confirmed) => api("PUT", "products/" + pid, { body: { data, confirm_guarded: confirmed }, rev }),
    view: store,
    onSaved: (res) => { if (app.state.products) app.state.products[pid] = res.data; },
    actions: () => [
      h("a", { class: "btn", href: store(), target: "_blank", rel: "noopener noreferrer" }, icon("external", 16), "View on store"),
      h("a", { class: "btn", href: "#/history/products/" + pid }, icon("clock", 16), "History"),
      h("button", { class: "btn", type: "button", onclick: duplicate }, icon("copy", 16), "Duplicate"),
      h("button", { class: "btn danger-text", type: "button", onclick: remove }, icon("trash", 16), "Delete"),
    ],
    form: (ctx, d) => {
      ctx.root = d;
      ctx.selfId = pid;
      const f = (p) => (visible(F[p], d) ? field(F[p], d, p, ctx) : null);
      const later = ["/name_ar", "/story_ar", "/family", "/tone", "/occasion", "/season", "/longevity", "/sillage", "/badge",
        "/seo_title", "/seo_description", "/image_alt", "/related"].map(f);
      return h("div", { class: "two-col" },
        h("div", { class: "col-main" },
          card("Title and story", f("/name"), f("/story")),
          card("Photos", visible(F["/images"], d) ? mediaGrid({ f: F["/images"], draft: d, ctx, pid, ed, app }) : null),
          card("Pricing", f("/price"), f("/sizes"), f("/size"), f("/contents"), f("/gender")),
          card("Inventory", f("/stock")),
          card("Scent notes", f("/top"), f("/heart"), f("/base")),
          card("Details", f("/ingredients"), f("/barcode")),
          h("section", { class: "card later" }, h("h2", {}, "Saved for later"),
            h("p", { class: "sub" }, "Kept with the product, but the shop does not show these yet."), later)),
        h("div", { class: "col-side" },
          card("Status", f("/published")),
          card("Category", f("/category")),
          card("Pricing rules", f("/never_discount")),
          h("section", { class: "card" }, h("h2", {}, "Where it appears"),
            refs.length ? h("ul", { class: "refs-list" }, refs.map((r) => h("li", {}, h("a", { href: r.link }, r.where))))
              : h("p", { class: "muted" }, "Not linked from the banner, the films or the navigation. It shows on its category's shelf and page.")),
          card("Position", f("/order"))));
    },
  });

  async function duplicate() {
    const v = await formDialog({
      title: "Duplicate this product", body: "The copy starts as a draft, without photos or barcode.", confirm: "Duplicate",
      fields: [
        { name: "name", label: "Title", value: ((ed.data() && ed.data().name) || pid) + " copy", required: true },
        { name: "new_id", label: "Web address id", value: pid + "-copy", required: true },
      ],
    });
    if (!v) return;
    try {
      await api("POST", "products/" + pid + "/duplicate", { body: { new_id: v.new_id, name: v.name } });
      app.state.products = null;
      guard.clear();
      toast("Copy created as a draft.");
      location.hash = "#/products/" + v.new_id;
    } catch (e) {
      clear(ed.msgs).append(banner({ tone: "critical", title: e.message, items: Array.isArray(e.details) ? e.details.map((x) => x.message) : [] }));
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      title: "Delete " + ((ed.data() && ed.data().name) || pid) + "?",
      body: ["It goes from the shop at the next save. Its photos stay in the site's files until they are removed there."],
      confirm: "Delete", danger: true,
    });
    if (!ok) return;
    try {
      await api("DELETE", "products/" + pid, { rev: ed.rev() });
      app.state.products = null;
      guard.clear();
      toast("Deleted.");
      location.hash = "#/products";
    } catch (e) {
      const items = e.details && e.details.refs ? e.details.refs.map((r) => r.where) : [];
      clear(ed.msgs).append(banner({ tone: "critical", title: e.message, items }));
    }
  }
}
