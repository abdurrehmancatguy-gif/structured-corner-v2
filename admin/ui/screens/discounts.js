// Discounts: the numbers behind the bag's volume ladder, the gift box and the
// free gift, kept in settings.json with the other store rules. The code that
// applies them (the bag's totals in shop.js) is locked, so each card says
// plainly what the admin cannot change. Discount codes wait for orders.
import { api } from "../lib/api.js";
import { h, clear, getPtr, setPtr, nextId, useCss } from "../lib/dom.js";
import { mountEditor } from "../lib/editor.js";
import { field, iconBtn } from "../lib/forms.js";
import { icon } from "../icons.js";

const LADDER = "/store/volume_ladder";
const BOX = ["/store/giftbox_fee", "/store/giftbox_volume_discount_at", "/store/giftbox_volume_discount_percent"];
const GIFT = ["/store/gift_with_purchase/threshold", "/store/gift_with_purchase/label"];
// The gift box page offers 3 or 6 slots (build.py's giftbox template), so a
// discount that starts above the larger box can never apply.
const BIGGEST_BOX = 6;

const IN_CODE = {
  ladder: [
    "The bag works the discount out in shop.js; only the rungs are set here.",
    "Products marked never discounted neither count toward a rung nor get the discount.",
    "The free gift and delivery are outside the ladder.",
    "VAT and cash on delivery stay locked with checkout.",
  ],
  box: [
    "The gift box page works its total out in shop.js as scents are picked.",
    "Its Add box to bag button opens the bag without putting the box in it, so the fee and discount show on that page only. Adding the box to the bag is a code change.",
    "The box holds 3 or 6 scents; the sizes are part of the page's code.",
    "The box discount counts every scent picked; it does not leave out never-discounted products.",
    "VAT and cash on delivery stay locked with checkout.",
  ],
  gift: [
    "The bag adds the gift line once its subtotal reaches the amount; it is worked out each time, never stored.",
    "The gift is free and outside the volume ladder.",
    "The gift is not a product in the catalogue, so it has no stock count.",
    "VAT and cash on delivery stay locked with checkout.",
  ],
};

export function render(main, { app }) {
  useCss("discounts");
  const fields = app.state.schema.resources.settings.fields;
  const def = (path) => fields.find((f) => f.path === path);
  let ed = null;
  ed = mountEditor(main, app, {
    heading: "Discounts",
    subtitle: "The bag's volume discount, the gift box and the free gift. These are store settings: saving rebuilds the site.",
    load: async () => { const d = await api("GET", "documents/settings"); return { rev: d.rev, data: d.data, meta: d }; },
    put: (data, rev) => api("PUT", "documents/settings", { body: { data }, rev }),
    view: () => "/cart.html",
    actions: () => [
      h("a", { class: "btn", href: "#/settings" }, "All settings"),
      h("a", { class: "btn", href: "/cart.html", target: "_blank", rel: "noopener noreferrer" }, icon("external", 16), "View bag"),
    ],
    onSaved: (res) => {
      if (!(res.warnings || []).some((w) => w.document === "copy")) return;
      // The editor lists the warnings right after this; the way to the text
      // they name goes under that list.
      setTimeout(() => ed.msgs.append(h("p", { class: "disc-next" }, h("a", { href: "#/content/copy" }, "Open Site text to update it"))), 0);
    },
    form: (ctx, data) => {
      ctx.root = data;
      const previews = [];
      const refresh = () => previews.forEach((fn) => fn());
      const card = (title, intro, body, preview, code) => {
        const out = h("div", { class: "preview" });
        previews.push(() => {
          const lines = preview(data);
          out.hidden = !lines.length;
          clear(out).append(...lines.map((t) => h("p", {}, t)));
        });
        return h("section", { class: "card" }, h("h2", {}, title), h("p", { class: "sub" }, intro), body, out,
          h("div", { class: "in-code" }, h("h3", {}, "Stays in code"), h("ul", {}, code.map((c) => h("li", {}, c)))));
      };
      const grid = h("div", { class: "disc-grid" },
        card("Volume ladder", "A percentage off the bag once it holds enough items.",
          ladderEditor(def(LADDER), data, ctx, refresh), ladderText, IN_CODE.ladder),
        card("Gift box", "The box's fee and its discount on the scents inside.",
          BOX.map((p) => field(def(p), data, p, ctx)), boxText, IN_CODE.box),
        card("Gift with purchase", "A free gift the bag adds from a set subtotal.",
          GIFT.map((p) => field(def(p), data, p, ctx)), giftText, IN_CODE.gift));
      grid.addEventListener("input", refresh);
      refresh();
      return h("div", {}, grid,
        h("section", { class: "card later" }, h("h2", {}, "Discount codes"),
          h("p", { class: "sub" }, "Arrives with the database: codes need orders to check against."),
          h("button", { class: "btn", type: "button", disabled: true }, "Create a code")));
    },
  });
}

const whole = (n) => Number.isInteger(n);
const aed = (n) => "AED " + n.toLocaleString("en-US");
const isLower = (c) => !!c && c === c.toLowerCase() && c !== c.toUpperCase();

// The bag's progress bar calls the gift by the part of its label before the
// comma, its capital dropped only when the rest of the phrase is lower case
// too, so a proper name keeps its capitals: build.py words it the same way.
function giftName(label) {
  const name = String(label).split(",")[0].trim();
  const rest = name.split(/\s+/).slice(1);
  return isLower(name[1]) && rest.every((w) => isLower(w[0])) ? name[0].toLowerCase() + name.slice(1) : name;
}

function ladderText(data) {
  const rungs = (getPtr(data, LADDER) || []).filter((r) => r && whole(r.units) && whole(r.percent));
  if (!rungs.length) return ["Add at least one rung."];
  for (let i = 1; i < rungs.length; i++) {
    if (rungs[i].units <= rungs[i - 1].units) return ["Each rung needs more items than the rung before it."];
  }
  return rungs.map((r, i) => {
    const next = rungs[i + 1];
    const span = !next ? r.units + " or more items"
      : next.units - 1 === r.units ? r.units + (r.units === 1 ? " item" : " items")
      : r.units + " to " + (next.units - 1) + " items";
    return span + " in the bag save " + r.percent + "%.";
  });
}

function boxText(data) {
  const s = data.store || {};
  const out = [];
  if (whole(s.giftbox_fee)) out.push("The gift box page adds " + aed(s.giftbox_fee) + " to the price of the scents.");
  const at = s.giftbox_volume_discount_at, pct = s.giftbox_volume_discount_percent;
  if (whole(at) && whole(pct)) {
    out.push(pct + "% off the scents once the box holds " + at + (at === 1 ? " scent." : " scents."));
    if (at > BIGGEST_BOX) out.push("The biggest box holds " + BIGGEST_BOX + " scents, so this discount would never apply.");
  }
  return out;
}

function giftText(data) {
  const g = (data.store || {}).gift_with_purchase || {};
  const label = String(g.label || "").trim();
  if (!whole(g.threshold) || !label) return [];
  return ["The bag's progress bar reads: Free " + giftName(label) + " over " + aed(g.threshold) + ".",
    "From a subtotal of " + aed(g.threshold) + " the bag lists " + label + " as a free line."];
}

// The rungs as a small table, units and percent side by side. Each input
// registers its own error slot, so a 422 on /store/volume_ladder/1/units
// lands under that input.
function ladderEditor(fl, data, ctx, after) {
  const unitsF = fl.fields.find((f) => f.path === "/units");
  const pctF = fl.fields.find((f) => f.path === "/percent");
  const err = h("p", { class: "error", hidden: true });
  const body = h("tbody");
  const add = h("button", { class: "btn small", type: "button", onclick: () => {
    rungs().push({ units: null, percent: null });
    changed(true);
    const last = body.lastElementChild;
    if (last) last.querySelector("input").focus();
  } }, icon("plus", 14), "Add a rung");
  const wrap = h("div", { class: "field ladder" },
    h("div", { class: "table-wrap" }, h("table", { class: "table ladder-t" },
      h("caption", { class: "sr-only" }, fl.label),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, unitsF.label), h("th", { scope: "col" }, pctF.label),
        h("th", { scope: "col" }, h("span", { class: "sr-only" }, "Remove")))),
      body)),
    add, fl.help ? h("p", { class: "help" }, fl.help) : null, err);
  ctx.slots.set(fl.path, { err, wrap });

  function rungs() {
    let list = getPtr(data, fl.path);
    if (!Array.isArray(list)) { list = []; setPtr(data, fl.path, list); }
    return list;
  }
  function changed(redraw) {
    ctx.onChange(fl);
    if (redraw) draw();
    if (after) after();
  }
  function cell(item, key, f, i) {
    const id = nextId();
    const e = h("p", { class: "error", id: id + "-err", hidden: true });
    const td = h("td", {}, h("input", { id, class: "input num", type: "number", step: "1", inputmode: "numeric",
      min: f.min, max: f.max, value: whole(item[key]) ? String(item[key]) : "",
      "aria-label": "Rung " + (i + 1) + ": " + f.label.toLowerCase(), "aria-describedby": id + "-err",
      oninput: (ev) => { item[key] = ev.target.value === "" ? null : Math.trunc(Number(ev.target.value)); changed(false); } }), e);
    ctx.slots.set(fl.path + "/" + i + "/" + key, { err: e, wrap: td });
    return td;
  }
  function draw() {
    for (const k of [...ctx.slots.keys()]) if (k.startsWith(fl.path + "/")) ctx.slots.delete(k);
    const list = rungs();
    clear(body).append(...list.map((item, i) => h("tr", {}, cell(item, "units", unitsF, i), cell(item, "percent", pctF, i),
      h("td", { class: "act" }, iconBtn("trash", "Remove rung " + (i + 1), list.length <= (fl.min || 0),
        () => { list.splice(i, 1); changed(true); })))));
    add.disabled = list.length >= fl.max;
  }
  draw();
  return wrap;
}
