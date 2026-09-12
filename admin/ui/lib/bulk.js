// Saving many products at once, as the Inventory and Bulk editor screens do:
// one products/bulk request, all or nothing, and the ways it can end that are
// not about one row. Kept apart from editor.js, which edits one record.
import { api } from "./api.js";
import { h } from "./dom.js";
import { banner, confirmDialog, toast } from "./ui.js";

export function productField(app, path) {
  return app.state.schema.resources.products.fields.find((f) => f.path === path) || { path, label: path.slice(1) };
}

// Category keys and their labels come from the schema, so a label changed
// there shows here without an edit.
export function categories(app) {
  const f = productField(app, "/category");
  const out = {};
  (f.enum || []).forEach((k, i) => { out[k] = (f.enumLabels && f.enumLabels[i]) || k; });
  return out;
}

export const plural = (n, one, many) => n + " " + (n === 1 ? one : many || one + "s");

// The checks validate.text_problem makes on the server, so a typed or pasted
// cell is marked before a save is tried. The server still decides. A broken
// half of a character pair is refused here too: the server cannot write it.
export function textProblem(s) {
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (ch === "<" || ch === ">") return "Leave out < and >: the page would read them as code.";
    if (c < 32 || c === 127) return "Remove the invisible character (a line break or tab) from this field.";
    if (c === 0x2014 || c === 0x2015) return "Use a hyphen or a colon instead of a long dash.";
    if (c >= 0xd800 && c <= 0xdfff) return "Remove the broken character from this field.";
  }
  if (s.includes("%%")) return "Write a single % sign.";
  return null;
}

// Sends the changes. A 428 names the guarded fields per product; once the
// owner confirms them, the same changes go once more with those confirmed.
// Saying no throws an error with the code "cancelled", which callers ignore.
export async function saveProducts(app, changes, names) {
  try {
    return await api("POST", "products/bulk", { body: { changes } });
  } catch (e) {
    if (e.code !== "guarded_field" || !e.details || !e.details.guarded) throw e;
    const guarded = e.details.guarded;
    const keys = [...new Set(Object.values(guarded).flat())];
    const helps = keys.map((k) => productField(app, "/" + k).help).filter(Boolean);
    const lines = Object.entries(guarded).map(([id, fields]) => {
      const c = changes.find((x) => x.id === id);
      return (names[id] || id) + ": " + fields.map((k) => {
        const v = c ? c.data[k] : undefined;
        return productField(app, "/" + k).label + (v === true ? " turns on" : v === false ? " turns off" : " changes");
      }).join(", ");
    });
    const ok = await confirmDialog({ title: e.message, body: helps.concat(lines), confirm: "Confirm and save" });
    if (!ok) {
      const stop = new Error("Not saved.");
      stop.code = "cancelled";
      throw stop;
    }
    return api("POST", "products/bulk", { body: { changes, confirm_guarded: guarded } });
  }
}

// The banner for a save that failed as a whole, or null when a toast says
// enough (another save is still running).
export function failure(e) {
  if (e.code === "busy") {
    toast("Another change is still saving. Try again in a moment.");
    return null;
  }
  if (e.code === "build_failed") {
    return banner({ tone: "critical", title: "Not saved: the site would not build with these changes.",
      items: ((e.details && e.details.problems) || []).concat(["Everything was put back as it was. Your edits are still here to fix."]) });
  }
  if (e.code === "bad_token") {
    return banner({ tone: "critical", title: "The admin restarted.",
      items: ["Reload the page to carry on. Unsaved changes on this screen will be lost."],
      actions: [h("button", { class: "btn", type: "button", onclick: () => location.reload() }, "Reload")] });
  }
  return banner({ tone: "critical", title: e.message });
}

// " The site rebuilt in 1.4 s." from a save's answer, or nothing when the
// answer does not say how long the build took.
export function builtIn(res) {
  const ms = res && res.build && res.build.ms;
  return ms ? " The site rebuilt in " + (ms / 1000).toFixed(1) + " s." : "";
}

// The warnings a bulk save returns, {id: [{message}]}, as one banner.
export function warningsBanner(res, names) {
  const w = (res && res.warnings) || {};
  const items = Object.entries(w).flatMap(([id, list]) => list.map((x) => (names[id] || id) + ": " + x.message));
  return items.length ? banner({ tone: "warning", title: "Saved. Something to check:", items }) : null;
}
