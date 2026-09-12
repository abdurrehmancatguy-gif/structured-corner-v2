// Any whole document (settings, site text, homepage, navigation and the ones
// added since): one schema-driven editor, the fields grouped into cards the
// way the schema groups them. The line under the heading is the schema's
// intro for that document.
import { api } from "../lib/api.js";
import { h } from "../lib/dom.js";
import { icon } from "../icons.js";
import { mountEditor } from "../lib/editor.js";
import { field, visible } from "../lib/forms.js";
import { uploadActions } from "../components/upload-field.js";

export function render(main, { arg: name, app }) {
  const res = app.state.schema.resources[name];
  // made once per visit, so an upload on its way stays in view when a save
  // or a reload draws the form again
  const uploads = uploadActions(() => ed);
  const ed = mountEditor(main, app, {
    heading: res.resource.label,
    subtitle: res.resource.intro || null,
    load: async () => { const d = await api("GET", "documents/" + name); return { rev: d.rev, data: d.data, meta: d }; },
    put: (data, rev) => api("PUT", "documents/" + name, { body: { data }, rev }),
    view: () => "/",
    actions: () => [
      h("a", { class: "btn", href: "#/history/documents/" + name }, icon("clock", 16), "History"),
      h("a", { class: "btn", href: "/", target: "_blank", rel: "noopener noreferrer" }, "View store"),
    ],
    form: (ctx, data) => {
      ctx.root = data;
      ctx.uploadActions = uploads;
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
