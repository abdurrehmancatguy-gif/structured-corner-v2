// Log: the admin's own record of sign-ins, refused sign-ins, sign-outs and
// every change to people and roles. Admin and Manager.
//
// Content changes are not here: the store records those with the person's
// address on each, and History shows them with the before and after. This is
// everything that is not content.
//
// Lines are kept 60 days. Nothing is deleted quietly: when the oldest are
// within a week of that, this screen says so and offers the copy.
import { api, download } from "../lib/api.js";
import { h, clear, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast } from "../lib/ui.js";

const KINDS = { signin: "Sign-in", signout: "Sign-out", staff: "People and roles" };

function when(text) {
  try {
    const d = new Date(text);
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch (e) {
    return text;
  }
}

export async function render(main, { app }) {
  useCss("audit");
  const note = h("div", { class: "msgs" });
  const body = h("div", { class: "table-wrap" });
  const foot = h("p", { class: "hint" });

  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("h1", { tabindex: "-1" }, "Log"),
      h("p", { class: "sub" }, "Who signed in, who was refused, and every change to people and roles. "
        + "Changes to the shop's content are in History, with what they changed."))),
    note,
    h("section", { class: "card flush" }, body, foot));

  let got;
  try {
    got = await api("GET", "audit");
  } catch (e) {
    return clear(note).append(banner({ tone: "critical", title: e.message }));
  }

  const s = got.stats || {};
  if (s.expiring) {
    clear(note).append(banner({
      tone: "warning",
      title: "The oldest lines are nearly " + s.keep_days + " days old and will go",
      items: ["Lines are kept " + s.keep_days + " days. The oldest is " + (s.oldest_days || 0)
              + " days old. Save a copy now if this needs keeping for longer."],
      actions: [h("button", { class: "btn", type: "button", onclick: () => saveCopy() }, "Save a copy")],
    }));
  }

  async function saveCopy() {
    try {
      await download("audit/export.jsonl", "bgs-admin-events.jsonl");
      toast("Saved. Keep it somewhere other than this computer.");
    } catch (e) {
      clear(note).append(banner({ tone: "critical", title: e.message }));
    }
  }

  const events = got.events || [];
  if (!events.length) {
    clear(body).append(h("p", { class: "empty" }, "Nothing yet. Sign-ins and role changes appear here."));
  } else {
    clear(body).append(h("table", { class: "table log" },
      h("thead", {}, h("tr", {},
        h("th", {}, "When"), h("th", {}, "What"), h("th", {}, "Who"), h("th", {}, "Detail"))),
      h("tbody", {}, events.map((e) => h("tr", { class: e.ok === false ? "bad" : null },
        h("td", { class: "nowrap" }, when(e.when)),
        h("td", {}, h("span", { class: "pill" }, KINDS[e.kind] || e.kind)),
        h("td", { class: "mono" }, e.actor || "—"),
        h("td", {}, e.message || ""))))));
  }

  clear(foot).append(
    h("span", {}, (s.lines || 0) + " line" + (s.lines === 1 ? "" : "s") + ", kept "
      + (s.keep_days || 60) + " days"),
    h("button", { class: "btn ghost", type: "button", onclick: saveCopy },
      icon("copy", 16), "Save a copy"));
}
