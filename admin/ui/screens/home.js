// Home: what is true about the shop right now, counted from the content.
// No sample numbers and no analytics: those arrive with the database.
import { api, storeUrl } from "../lib/api.js";
import { h, clear } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, guard, toast } from "../lib/ui.js";

export async function render(main, { app }) {
  guard.clear();
  clear(main).append(h("div", { class: "page-head" }, h("div", {}, h("h1", { tabindex: "-1" }, "Home"),
    h("p", { class: "sub" }, "Your shop's content at a glance. Changes you save here appear on the preview at once."))));
  let list, st;
  try {
    [list, st] = await Promise.all([api("GET", "products"), api("GET", "status")]);
  } catch (e) { main.append(banner({ tone: "critical", title: e.message })); return; }
  app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
  const items = list.items.map((it) => it.data);
  const active = items.filter((d) => d.published !== false);
  const noPhoto = list.items.filter((it) => it.data.published !== false && !(it.data.images || []).length);
  const noStory = list.items.filter((it) => !(it.data.story || []).length);
  const low = list.items.filter((it) => typeof it.data.stock === "number" && it.data.stock <= 5);
  const stat = (n, label, href) => h("a", { class: "stat", href }, h("b", {}, String(n)), h("span", {}, label));
  const names = (arr) => arr.map((it) => h("a", { href: "#/products/" + it.id }, it.data.name || it.id));

  if (st.external && st.external.length) {
    main.append(banner({ tone: "warning", title: "Content changed outside the admin: " + st.external.join(", ") + ".",
      items: ["Someone edited the files directly (a terminal or a Claude session). Screens you open now show their version."],
      actions: [h("button", { class: "btn", type: "button", onclick: async () => { await api("POST", "status/ack", { body: {} }); toast("Noted."); render(main, { app }); } }, "Got it")] }));
  }
  main.append(
    h("section", { class: "card" }, h("h2", {}, "Your shop"),
      h("div", { class: "stats" }, stat(items.length, "products", "#/products"), stat(active.length, "active", "#/products"),
        stat(items.length - active.length, "drafts", "#/products"))),
    h("div", { class: "cards two" },
      h("section", { class: "card" }, h("h2", {}, "Needs attention"),
        h("ul", { class: "todo" },
          h("li", {}, h("b", {}, noPhoto.length + " active without a photo"), noPhoto.length ? h("span", { class: "names" }, names(noPhoto)) : null),
          h("li", {}, h("b", {}, noStory.length + " without a story"), noStory.length ? h("span", { class: "names" }, names(noStory.slice(0, 12)), noStory.length > 12 ? " and more" : "") : null),
          h("li", {}, h("b", {}, low.length + " at 5 or fewer in stock"), low.length ? h("span", { class: "names" }, names(low)) : null))),
      h("section", { class: "card" }, h("h2", {}, "Edit the shop"),
        h("div", { class: "quick" },
          h("a", { class: "btn", href: "#/products" }, icon("tag", 16), "Products"),
          h("a", { class: "btn", href: "#/content/home" }, icon("layout", 16), "Homepage"),
          h("a", { class: "btn", href: "#/content/navigation" }, icon("menu", 16), "Navigation"),
          h("a", { class: "btn", href: "#/content/copy" }, icon("text", 16), "Site text"),
          h("a", { class: "btn", href: "#/settings" }, icon("gear", 16), "Settings"),
          h("a", { class: "btn", href: storeUrl(""), target: "_blank", rel: "noopener noreferrer" }, icon("external", 16), "View store")))));
}
