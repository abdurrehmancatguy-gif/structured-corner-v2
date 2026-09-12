// Scent quiz: the questions and their answers, what each answer looks for,
// the sprays a visitor can be matched with, and the quiz page's own words,
// all kept in content/quiz.json and saved together. Keys are shown but never
// edited: a key joins an answer's button to what the answer looks for.
import { api } from "../lib/api.js";
import { h, clear, append, useCss, getPtr, setPtr, nextId } from "../lib/dom.js";
import { icon } from "../icons.js";
import { announce } from "../lib/ui.js";
import { mountEditor } from "../lib/editor.js";
import { field, iconBtn } from "../lib/forms.js";

// The open screen's state: the schema's fields, the editor's context and
// draft, and every facet seen so far. A facet's column stays while the
// screen is open, even once nothing ticks it, so a slip can be undone.
let S = null;

// A schema field by its path, among a document's or a rows field's fields.
function find(fields, path) {
  return (fields || []).find((f) => f.path === path) || { path, type: "text", label: path };
}

const list = (v) => (Array.isArray(v) ? v : []);
const count = (arr, f) => list(arr).filter((x) => x === f).length;

// Every facet an answer or a profile uses, plus any added on this screen,
// in alphabetical order.
function vocabulary() {
  for (const a of list(S.data.answers)) list(a.facets).forEach((f) => S.known.add(f));
  for (const p of list(S.data.profiles)) list(p.facets).forEach((f) => S.known.add(f));
  return [...S.known].sort();
}

// A text input in a table cell, bound to one JSON pointer, with its own
// error line so a refusal from the server lands next to it.
function textCell(f, target, ptr, label) {
  const err = h("p", { class: "error", id: nextId("qz-e"), hidden: true });
  const v = getPtr(target, f.path);
  const td = h("td", {}, h("input", {
    class: "input", type: "text", value: v === undefined || v === null ? "" : String(v), maxlength: f.maxLength || null,
    autocomplete: "off", "aria-label": label, "aria-describedby": err.id,
    oninput: (e) => { setPtr(target, f.path, e.target.value); S.ctx.onChange(f); },
  }), err);
  S.ctx.slots.set(ptr, { err, wrap: td });
  return td;
}

// ---- questions ----------------------------------------------------------------

function questionsCard() {
  const qs = list(S.data.questions);
  const n = qs.reduce((sum, q) => sum + list(q.options).length, 0);
  return h("section", { class: "card", "aria-labelledby": "qz-q-h" },
    h("h2", { id: "qz-q-h" }, S.Q.label),
    h("p", { class: "sub qz-sub" }, qs.length + (qs.length === 1 ? " question with " : " questions with ") + n +
      (n === 1 ? " answer. " : " answers between them. ") + (find(S.OPT.fields, "/key").readonly || "")),
    qs.map(questionBlock));
}

function questionBlock(q, i) {
  const ptr = "/questions/" + i;
  const kind = find(S.Q.fields, "/kind");
  const k = list(kind.enum).indexOf(q.kind);
  const named = k < 0 ? String(q.kind || "") : String((kind.enumLabels || kind.enum)[k]);
  const L = (p) => find(S.OPT.fields, p);
  return h("div", { class: "qz-q" },
    h("h3", {}, "Question " + (i + 1)),
    h("div", { class: "qz-qhead" },
      field(find(S.Q.fields, "/title"), q, ptr + "/title", S.ctx),
      field(find(S.Q.fields, "/columns"), q, ptr + "/columns", S.ctx)),
    h("p", { class: "qz-kind", title: kind.readonly || "" }, icon("lock", 14),
      kind.label + " ", h("b", {}, named.charAt(0).toLowerCase() + named.slice(1)), "."),
    h("div", { class: "table-wrap" }, h("table", { class: "table qz-opts" },
      h("thead", {}, h("tr", {},
        h("th", { scope: "col" }, L("/key").label), h("th", { scope: "col" }, L("/label").label),
        h("th", { scope: "col" }, L("/sub").label))),
      h("tbody", {}, list(q.options).map((o, j) => {
        const at = ptr + "/options/" + j;
        const who = "Question " + (i + 1) + ", answer " + (j + 1);
        return h("tr", {},
          h("td", { class: "qz-key" }, h("code", {}, String(o.key))),
          textCell(L("/label"), o, at + "/label", who),
          textCell(L("/sub"), o, at + "/sub", who + ", small line"));
      })))));
}

// ---- what each answer looks for -----------------------------------------------

function matrixCard() {
  const card = h("section", { class: "card flush", "aria-labelledby": "qz-m-h" });
  const note = h("p", { class: "hint" });
  // A facet an answer looks for but no profile has can never add to a match.
  S.facetNote = () => {
    const have = new Set(list(S.data.profiles).flatMap((p) => list(p.facets)));
    const idle = [...new Set(list(S.data.answers).flatMap((a) => list(a.facets)))].filter((f) => !have.has(f)).sort();
    clear(note).append(idle.length
      ? "No profile has " + idle.join(", ") + ", so an answer looking for " + (idle.length === 1 ? "it" : "them") + " adds nothing to a match."
      : "Every facet an answer looks for belongs to at least one profile.");
  };
  S.drawMatrix = () => {
    for (const k of [...S.ctx.slots.keys()]) if (k.startsWith("/answers/")) S.ctx.slots.delete(k);
    const facets = vocabulary();
    const answers = list(S.data.answers);
    const index = new Map(answers.map((a, i) => [a.key, i]));
    const shown = new Set();
    const rows = [];
    list(S.data.questions).forEach((q, qi) => {
      rows.push(h("tr", { class: "qz-group" }, h("th", { scope: "colgroup", colspan: String(facets.length + 2) },
        "Question " + (qi + 1) + ": " + (q.title || ""))));
      for (const o of list(q.options)) {
        const i = index.get(o.key);
        if (i === undefined) continue;
        shown.add(i);
        rows.push(answerRow(answers[i], i, o.label || o.key, facets));
      }
    });
    answers.forEach((a, i) => { if (!shown.has(i)) rows.push(answerRow(a, i, String(a.key), facets)); });

    const input = h("input", { class: "input", type: "text", id: "qz-newfacet", autocomplete: "off",
      maxlength: String(find(S.ANS.fields, "/facets").itemMaxLength || 24), "aria-describedby": "qz-newfacet-err" });
    const addErr = h("p", { class: "error", id: "qz-newfacet-err", hidden: true });
    const add = () => {
      const f = input.value.trim().toLowerCase();
      const why = !/^[a-z]+(?:-[a-z]+)*$/.test(f) ? "Use one lower-case word, or words joined by hyphens."
        : S.known.has(f) ? f + " already has a column." : "";
      if (why) { addErr.textContent = why; addErr.hidden = false; input.focus(); return; }
      S.known.add(f);
      S.drawMatrix();
      S.drawProfiles();
      announce("Added the facet " + f + ". Tick it for the answers and profiles that have it.");
      const again = document.getElementById("qz-newfacet");
      if (again) again.focus();
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
    append(clear(card), [
      h("div", { class: "qz-intro" }, h("h2", { id: "qz-m-h" }, S.ANS.label),
        h("p", { class: "sub" }, "Tick the facets each answer looks for; the match is the profile with the most of them. " +
          (find(S.ANS.fields, "/facets").help || "") + " The last column is what the result calls the answer.")),
      h("div", { class: "table-wrap" }, h("table", { class: "table qz-grid" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Answer"),
          facets.map((f) => h("th", { scope: "col", class: "qz-f" }, f)),
          h("th", { scope: "col" }, find(S.ANS.fields, "/label").label))),
        h("tbody", {}, rows))),
      note,
      h("div", { class: "qz-add" }, h("label", { for: "qz-newfacet" }, "New facet"), input,
        h("button", { class: "btn small", type: "button", onclick: add }, icon("plus", 14), "Add a column"), addErr),
    ]);
    S.facetNote();
  };
  S.drawMatrix();
  return card;
}

function answerRow(a, i, label, facets) {
  const ptr = "/answers/" + i;
  const err = h("p", { class: "error", id: nextId("qz-e"), hidden: true });
  const head = h("th", { scope: "row", class: "qz-ans" }, label, h("small", {}, String(a.key)), err);
  S.ctx.slots.set(ptr, { err, wrap: head });
  S.ctx.slots.set(ptr + "/facets", { err, wrap: head });
  return h("tr", {}, head, facets.map((f) => facetCell(a, f, label)),
    textCell(find(S.ANS.fields, "/label"), a, ptr + "/label", label + ": named in the result as"));
}

// A checkbox per facet. A ticked facet gets a x2 toggle, because a facet an
// answer lists twice counts twice in the match.
function facetCell(a, f, who) {
  const box = h("input", { type: "checkbox", "aria-label": who + ": " + f });
  const twice = h("button", { type: "button", class: "qz-x2", "aria-label": who + ": count " + f + " twice", title: "Count it twice" }, "×2");
  const sync = () => {
    const n = count(a.facets, f);
    box.checked = n > 0;
    twice.hidden = n === 0;
    twice.setAttribute("aria-pressed", String(n > 1));
  };
  box.addEventListener("change", () => {
    a.facets = list(a.facets).filter((x) => x !== f);
    if (box.checked) a.facets.push(f);
    sync();
    S.ctx.onChange(S.ANS);
    S.facetNote();
  });
  twice.addEventListener("click", () => {
    a.facets = list(a.facets).slice();
    if (count(a.facets, f) > 1) a.facets.splice(a.facets.lastIndexOf(f), 1);
    else a.facets.push(f);
    sync();
    S.ctx.onChange(S.ANS);
  });
  sync();
  return h("td", { class: "qz-cell" }, h("span", { class: "qz-cellin" }, box, twice));
}

// ---- result profiles -------------------------------------------------------------

function profilesCard() {
  const card = h("section", { class: "card", "aria-labelledby": "qz-p-h" });
  const err = h("p", { class: "error", hidden: true });
  S.drawProfiles = (focus) => {
    for (const k of [...S.ctx.slots.keys()]) if (k.startsWith("/profiles")) S.ctx.slots.delete(k);
    if (!Array.isArray(S.data.profiles)) S.data.profiles = [];
    const items = S.data.profiles;
    const full = S.PRO.max !== undefined && items.length >= S.PRO.max;
    const intro = h("div", {}, h("h2", { id: "qz-p-h" }, S.PRO.label), h("p", { class: "sub qz-sub" }, S.PRO.help || ""), err);
    S.ctx.slots.set("/profiles", { err, wrap: intro });
    append(clear(card), [intro,
      items.length ? h("ol", { class: "qz-profiles" }, items.map(profileItem))
        : h("p", { class: "empty" }, "No profiles yet, so the quiz has nothing to match."),
      h("div", { class: "qz-foot" }, h("button", { class: "btn", type: "button", disabled: full,
        title: full ? "The quiz holds up to " + S.PRO.max + " profiles." : null,
        onclick: () => {
          items.push({ product: "", notes: "", facets: [] });
          S.ctx.onChange(S.PRO);
          S.drawProfiles("#qz-pro-" + (items.length - 1) + " select");
        } }, icon("plus", 16), "Add a profile"))]);
    if (focus) {
      const el = card.querySelector(focus);
      if (el) el.focus();
    }
  };
  S.drawProfiles();
  return card;
}

function profileItem(p, i) {
  const items = S.data.profiles;
  const ptr = "/profiles/" + i;
  const P = (x) => find(S.PRO.fields, x);
  const title = h("h3", {});
  const info = h("p", { class: "qz-info" });
  // The name, price and barcode the shop shows come from the product itself.
  const draw = () => {
    const d = S.ctx.products[p.product];
    clear(title).append(d ? d.name || p.product : "Profile " + (i + 1));
    const dup = !!p.product && items.findIndex((x) => x.product === p.product) < i;
    append(clear(info), d
      ? [[d.size, d.gender, d.price !== undefined ? "AED " + d.price : null, d.barcode ? "Barcode " + d.barcode : null]
          .filter(Boolean).join(" · "),
        d.published === false ? h("span", { class: "badge gold" }, "Not published, so left out of the quiz") : null,
        dup ? h("span", { class: "badge red" }, "A profile above has this product") : null]
      : "Pick the product this profile stands for.");
  };
  const pick = field(P("/product"), p, ptr + "/product", S.ctx);
  const sel = pick.querySelector("select");
  if (sel) sel.addEventListener("change", draw);
  // Focus follows the moved profile to its button for the same direction, or
  // to the other one once it reaches an end, where that button is disabled.
  const move = (d) => {
    const j = i + d;
    const [x] = items.splice(i, 1);
    items.splice(j, 0, x);
    S.ctx.onChange(S.PRO);
    const dir = d < 0 ? (j === 0 ? "down" : "up") : (j === items.length - 1 ? "up" : "down");
    S.drawProfiles("#qz-pro-" + j + " .qz-" + dir);
    announce("Moved to position " + (j + 1) + ".");
  };
  const remove = () => {
    items.splice(i, 1);
    S.ctx.onChange(S.PRO);
    S.drawProfiles(items.length ? "#qz-pro-" + Math.min(i, items.length - 1) + " select" : ".qz-foot button");
    S.facetNote();
    announce("Removed profile " + (i + 1) + ". Save to apply.");
  };
  const name = "profile " + (i + 1);
  const up = iconBtn("up", "Move " + name + " up", i === 0, () => move(-1));
  const down = iconBtn("down", "Move " + name + " down", i === items.length - 1, () => move(1));
  up.classList.add("qz-up");
  down.classList.add("qz-down");
  const fErr = h("p", { class: "error", id: nextId("qz-e"), hidden: true });
  const facets = h("fieldset", { class: "qz-facets", "aria-describedby": fErr.id }, h("legend", {}, P("/facets").label),
    vocabulary().map((f) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: list(p.facets).includes(f),
      onchange: (e) => {
        p.facets = list(p.facets).filter((x) => x !== f);
        if (e.target.checked) p.facets.push(f);
        S.ctx.onChange(P("/facets"));
        S.facetNote();
      } }), f)), fErr);
  S.ctx.slots.set(ptr + "/facets", { err: fErr, wrap: facets });
  draw();
  return h("li", { class: "qz-pro", id: "qz-pro-" + i },
    h("div", { class: "qz-pro-head" }, title, up, down, iconBtn("trash", "Remove " + name, false, remove)),
    pick, info, field(P("/notes"), p, ptr + "/notes", S.ctx), facets);
}

// ---- the result's and the page's own words -----------------------------------------

function labelsCard(group, heading, id) {
  const fs = S.F.filter((f) => f.group === group && f.type !== "rows");
  return h("section", { class: "card", "aria-labelledby": id }, h("h2", { id }, heading), fs.map((f) => field(f, S.data, f.path, S.ctx)));
}

// Found before sending: a profile with no product picked, or with the
// product of a profile above it, which could never be the match.
function profileProblems(data) {
  const out = [];
  list(data.profiles).forEach((p, i) => {
    const at = "/profiles/" + i + "/product";
    if (!p.product) out.push({ path: at, message: "Pick the product this profile stands for." });
    else if (list(data.profiles).findIndex((x) => x.product === p.product) < i) {
      out.push({ path: at, message: "A profile above already has this product." });
    }
  });
  return out;
}

export function render(main, { app }) {
  useCss("quiz");
  const res = app.state.schema.resources.quiz;
  const Q = find(res.fields, "/questions");
  S = { F: res.fields, Q, OPT: find(Q.fields, "/options"), ANS: find(res.fields, "/answers"), PRO: find(res.fields, "/profiles"),
    known: new Set(), ctx: null, data: null, facetNote: () => {}, drawMatrix: () => {}, drawProfiles: () => {} };
  mountEditor(main, app, {
    heading: res.resource.label,
    subtitle: res.resource.intro || null,
    load: async () => {
      const [d, prods] = await Promise.all([api("GET", "documents/quiz"), api("GET", "products")]);
      return { rev: d.rev, data: d.data, meta: { products: Object.fromEntries(prods.items.map((it) => [it.id, it.data])) } };
    },
    put: (data, rev) => {
      const probs = profileProblems(data);
      if (probs.length) {
        const e = new Error("Some fields need attention.");
        e.code = "validation";
        e.details = probs;
        return Promise.reject(e);
      }
      return api("PUT", "documents/quiz", { body: { data }, rev });
    },
    view: () => "/quiz.html",
    actions: () => [h("a", { class: "btn", href: "/quiz.html", target: "_blank", rel: "noopener noreferrer" }, "View the quiz")],
    form: (ctx, data, meta) => {
      ctx.root = data;
      ctx.products = meta.products || {};
      S.ctx = ctx;
      S.data = data;
      return h("div", { class: "qz" }, questionsCard(), matrixCard(), profilesCard(),
        labelsCard("Result", "The result", "qz-r-h"), labelsCard("Page", "The quiz page", "qz-pg-h"));
    },
  });
}
