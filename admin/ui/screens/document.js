// Settings, site text, homepage and navigation: one schema-driven editor,
// the fields grouped into cards the way the schema groups them.
import { api } from "../lib/api.js";
import { h } from "../lib/dom.js";
import { mountEditor } from "../lib/editor.js";
import { field, visible } from "../lib/forms.js";

const INTRO = {
  settings: "Store details, delivery rules and brand. Payments, tax and cash on delivery are locked: a developer changes those in code.",
  copy: "Text around the shop: the promises under the banner, the quiz banner, the top strip and the collection intros.",
  home: "The homepage banner, the product films and the section headings.",
  navigation: "The category bar and homepage circles, the phone tab bar and the footer.",
};

export function render(main, { arg: name, app }) {
  const res = app.state.schema.resources[name];
  mountEditor(main, app, {
    heading: res.resource.label,
    subtitle: INTRO[name],
    load: async () => { const d = await api("GET", "documents/" + name); return { rev: d.rev, data: d.data, meta: d }; },
    put: (data, rev) => api("PUT", "documents/" + name, { body: { data }, rev }),
    view: () => "/",
    actions: () => [h("a", { class: "btn", href: "/", target: "_blank", rel: "noopener noreferrer" }, "View store")],
    form: (ctx, data) => {
      ctx.root = data;
      const groups = new Map();
      for (const f of res.fields) {
        if (!visible(f, data)) continue;
        const g = f.group || "General";
        if (!groups.has(g)) groups.set(g, []);
        groups.get(g).push(f);
      }
      return h("div", { class: "cards" }, [...groups].map(([g, fs]) => {
        const locked = fs.every((f) => f.locked);
        return h("section", { class: "card" + (locked ? " locked" : "") }, h("h2", {}, g), fs.map((f) => field(f, data, f.path, ctx)));
      }));
    },
  });
}
