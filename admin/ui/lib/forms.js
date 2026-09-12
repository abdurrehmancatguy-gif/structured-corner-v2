// Forms built from the server's schema: one control per field type, rows
// editors for lists of entries, and a map from JSON pointers to fields so a
// 422 from the server lands next to the field it is about. The server checks
// everything again; nothing here is trusted.
import { h, clear, getPtr, setPtr, copy, nextId, thumb } from "./dom.js";
import { icon } from "../icons.js";
import { confirmDialog } from "./ui.js";

export function makeCtx(app, extra = {}) {
  return Object.assign({
    root: null, selfId: null,
    icons: app.state.schema.icons, tints: app.state.schema.tints,
    products: app.state.products || {},
    slots: new Map(), confirmed: new Set(),
    onChange() {}, rerender() {},
  }, extra);
}

export function visible(f, root) {
  if (!f || !f.visibleWhen) return !!f;
  return Object.entries(f.visibleWhen).every(([k, vals]) => vals.includes(root ? root[k] : undefined));
}

export const iconBtn = (name, label, disabled, onclick) =>
  h("button", { class: "icon-btn", type: "button", "aria-label": label, title: label, disabled, onclick }, icon(name, 16));

function badges(f) {
  const out = [];
  if (f.locked) out.push(h("span", { class: "badge lock", title: f.locked }, icon("lock", 12), "Locked"));
  else if (f.readonly) out.push(h("span", { class: "badge muted", title: f.readonly }, "Not editable here yet"));
  if (f.rendered === false) out.push(h("span", { class: "badge outline", title: f.notShown || "" }, "Not on the site yet"));
  if (f.guarded) out.push(h("span", { class: "badge gold" }, "Asks first"));
  return out;
}

function blank(fields) {
  const o = {};
  for (const f of fields) {
    const v = { text: "", textarea: "", href: "", image: "", video: "", int: 0, money: 1, bool: false, lines: [], rows: [],
      "product-refs": [], images: [] }[f.type];
    if (f.type === "enum") setPtr(o, f.path, f.enum[0]);
    else if (v !== undefined) setPtr(o, f.path, copy(v));
  }
  return o;
}

function rowTitle(f, item, i, ctx) {
  let v = f.itemLabel ? getPtr(item, "/" + f.itemLabel) : "";
  if (f.itemLabel === "product" && ctx.products[v]) v = ctx.products[v].name;
  v = String(v || "").replace(/\n/g, " ").trim();
  return v || "Entry " + (i + 1);
}

function productOptions(ctx, exclude = []) {
  return Object.entries(ctx.products)
    .filter(([pid]) => !exclude.includes(pid))
    .sort((a, b) => (a[1].name || a[0]).localeCompare(b[1].name || b[0]));
}

export function field(f, target, ptr, ctx) {
  const id = nextId();
  const disabled = !!(f.locked || f.readonly);
  const help = [f.locked || f.readonly, f.help, f.rendered === false ? f.notShown : null].filter(Boolean);
  const err = h("p", { class: "error", id: id + "-err", hidden: true });
  const described = (help.length ? id + "-help " : "") + id + "-err";
  const get = () => getPtr(target, f.path);
  const set = (v) => { setPtr(target, f.path, v); ctx.onChange(f); };
  const common = { id, disabled, "aria-describedby": described };
  let control;
  let counter = null;

  switch (f.type) {
    case "text": case "href": case "image": case "video": {
      const v = get();
      const input = h("input", Object.assign({}, common, {
        class: "input", type: "text", value: v === null || v === undefined ? "" : String(v),
        maxlength: f.maxLength || null, dir: f.dir || null, autocomplete: "off",
        list: f.type === "href" && !f.social ? "bgs-links" : null,
        placeholder: f.type === "href" ? (f.social ? "https://" : "product.html?p=... or collection.html?cat=...") : null,
        oninput: (e) => { set(e.target.value); if (counter) counter.textContent = e.target.value.length + " / " + f.maxLength; },
      }));
      control = input;
      if (f.type === "image" && v) control = h("div", { class: "img-field" }, h("img", { class: "img-prev", src: "/" + v, alt: "" }), input);
      if (f.maxLength && !disabled) counter = h("span", { class: "count" }, String((v || "").length) + " / " + f.maxLength);
      break;
    }
    case "textarea": {
      control = h("textarea", Object.assign({}, common, {
        class: "input area", rows: f.multiline ? 2 : 3, maxlength: f.maxLength || null, dir: f.dir || null,
        oninput: (e) => {
          let v = e.target.value;
          if (!f.multiline && v.includes("\n")) { v = v.replace(/\n+/g, " "); e.target.value = v; }
          set(v);
          if (counter) counter.textContent = v.length + " / " + f.maxLength;
        },
      }));
      control.value = get() || "";
      if (f.maxLength && !disabled) counter = h("span", { class: "count" }, String((get() || "").length) + " / " + f.maxLength);
      break;
    }
    case "int": case "money": {
      const v = get();
      const toNum = (s) => (s === "" ? null : Math.trunc(Number(s)));
      const num = h("input", Object.assign({}, common, {
        class: "input num", type: "number", step: "1", inputmode: "numeric",
        min: f.min !== undefined ? f.min : (f.type === "money" ? 1 : null), max: f.max !== undefined ? f.max : null,
        value: v === null || v === undefined ? "" : String(v),
        oninput: (e) => set(toNum(e.target.value)),
      }));
      if (f.nullable) {
        num.disabled = disabled || v === null || v === undefined;
        const track = h("input", { type: "checkbox", id: id + "-t", checked: v !== null && v !== undefined, disabled,
          onchange: (e) => { num.disabled = !e.target.checked; set(e.target.checked ? (toNum(num.value) || 0) : null); } });
        control = h("div", { class: "inline" }, h("label", { class: "check", for: id + "-t" }, track, f.nullableLabel || "Track"), num);
      } else control = num;
      break;
    }
    case "bool": {
      const input = h("input", Object.assign({}, common, {
        type: "checkbox", class: "switch", role: "switch", checked: !!get(),
        onchange: async (e) => {
          const v = e.target.checked;
          if (f.guarded) {
            const ok = await confirmDialog({ title: (v ? "Turn on " : "Turn off ") + f.label.toLowerCase() + "?", body: [f.help], confirm: v ? "Turn on" : "Turn off" });
            if (!ok) { e.target.checked = !v; return; }
            ctx.confirmed.add(f.path.replace(/^\//, ""));
          }
          set(v);
        },
      }));
      control = h("div", { class: "switch-row" }, input);
      break;
    }
    case "enum": {
      const v = get();
      const idx = f.enum.findIndex((x) => x === v);
      control = h("select", Object.assign({}, common, {
        class: "input",
        onchange: (e) => { set(f.enum[Number(e.target.value)]); if (f.path === "/category") ctx.rerender(); },
      }), idx < 0 ? h("option", { value: "", selected: true, disabled: true }, "Choose") : null,
      f.enum.map((x, i) => h("option", { value: String(i), selected: i === idx }, (f.enumLabels && f.enumLabels[i]) || String(x))));
      break;
    }
    case "icon": case "tint": {
      const opts = (f.type === "icon" ? ctx.icons : ctx.tints) || [];
      const v = get();
      control = h("select", Object.assign({}, common, { class: "input", onchange: (e) => set(e.target.value) }),
        opts.includes(v) ? null : h("option", { value: "", selected: true, disabled: true }, "Choose"),
        opts.map((o) => h("option", { value: o, selected: o === v }, o.replace(/_/g, " "))));
      break;
    }
    case "lines": control = linesEditor(f, get(), set, disabled, id); break;
    case "product-ref": {
      const v = get();
      control = h("select", Object.assign({}, common, { class: "input", onchange: (e) => set(e.target.value) }),
        ctx.products[v] ? null : h("option", { value: "", selected: true, disabled: true }, v ? v + " (not found)" : "Choose a product"),
        productOptions(ctx).map(([pid, d]) => h("option", { value: pid, selected: pid === v }, (d.name || pid) + "  (" + pid + ")")));
      break;
    }
    case "product-refs": control = refsEditor(f, get(), set, disabled, id, ctx); break;
    case "images": {
      const v = get() || [];
      control = h("div", { class: "thumbs", id }, v.length
        ? v.map((n, i) => h("figure", {}, h("img", { src: thumb(n), alt: "", loading: "lazy", width: "80", height: "80" }),
          h("figcaption", {}, i === 0 ? "Card" : i === 1 ? "Hover" : String(i + 1))))
        : h("p", { class: "muted" }, "No photos yet."));
      break;
    }
    case "rows": control = rowsEditor(f, target, ptr, ctx, disabled); break;
    default: control = h("p", { class: "muted" }, "This field type is not shown yet.");
  }

  const labelEl = ["rows", "images", "lines", "product-refs"].includes(f.type)
    ? h("span", { class: "f-label", id: id + "-label" }, f.label)
    : h("label", { class: "f-label", for: id }, f.label);
  const wrap = h("div", { class: "field t-" + f.type + (disabled ? " is-disabled" : ""), dataset: { ptr } },
    h("div", { class: "f-head" }, labelEl, f.required ? h("span", { class: "req" }, "Required") : null, ...badges(f), counter),
    control,
    help.length ? h("p", { class: "help", id: id + "-help" }, help.join(" ")) : null,
    err);
  ctx.slots.set(ptr, { err, wrap });
  return wrap;
}

function linesEditor(f, value, set, disabled, id) {
  const arr = Array.isArray(value) ? value : [];
  const box = h("div", { class: "lines" });
  const draw = (focusLast) => {
    clear(box);
    arr.forEach((line, i) => box.append(h("div", { class: "line-row" },
      h("input", { class: "input", type: "text", value: line, dir: f.dir || null, maxlength: f.itemMaxLength || null, disabled,
        id: i === 0 ? id : null, "aria-label": f.label + ", line " + (i + 1), oninput: (e) => { arr[i] = e.target.value; set(arr); } }),
      iconBtn("up", "Move line up", disabled || i === 0, () => { [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]; set(arr); draw(); }),
      iconBtn("down", "Move line down", disabled || i === arr.length - 1, () => { [arr[i + 1], arr[i]] = [arr[i], arr[i + 1]]; set(arr); draw(); }),
      iconBtn("trash", "Remove line", disabled, () => { arr.splice(i, 1); set(arr); draw(); }))));
    if (!disabled && (f.max === undefined || f.max === null || arr.length < f.max)) {
      box.append(h("button", { class: "btn small", type: "button", onclick: () => { arr.push(""); set(arr); draw(true); } }, icon("plus", 14), "Add a line"));
    }
    if (focusLast) { const ins = box.querySelectorAll("input"); if (ins.length) ins[ins.length - 1].focus(); }
  };
  draw();
  return box;
}

function refsEditor(f, value, set, disabled, id, ctx) {
  const arr = Array.isArray(value) ? value : [];
  const box = h("div", { class: "refs" });
  const draw = () => {
    clear(box);
    const chips = h("div", { class: "chips" }, arr.length ? arr.map((pid, i) => h("span", { class: "chip" },
      (ctx.products[pid] && ctx.products[pid].name) || pid,
      disabled ? null : h("button", { type: "button", class: "chip-x", "aria-label": "Remove " + pid, onclick: () => { arr.splice(i, 1); set(arr); draw(); } }, icon("close", 12))))
      : h("span", { class: "muted" }, "None picked."));
    box.append(chips);
    if (!disabled && (f.max === undefined || arr.length < f.max)) {
      box.append(h("select", { id, class: "input", onchange: (e) => { if (e.target.value) { arr.push(e.target.value); set(arr); draw(); } } },
        h("option", { value: "", selected: true }, "Add a product"),
        productOptions(ctx, arr.concat(ctx.selfId ? [ctx.selfId] : [])).map(([pid, d]) => h("option", { value: pid }, d.name || pid))));
    }
  };
  draw();
  return box;
}

function rowsEditor(f, target, ptr, ctx, disabled) {
  let list = getPtr(target, f.path);
  if (!Array.isArray(list)) list = [];
  const box = h("div", { class: "rows" });
  const commit = () => { setPtr(target, f.path, list); ctx.onChange(f); draw(); };
  const move = (i, d) => { const [x] = list.splice(i, 1); list.splice(i + d, 0, x); commit(); };
  const full = () => f.max !== undefined && f.max !== null && list.length >= f.max;
  const draw = () => {
    clear(box);
    list.forEach((item, i) => {
      const body = h("div", { class: "row-body" });
      for (const sub of f.fields || []) if (visible(sub, ctx.root)) body.append(field(sub, item, ptr + "/" + i + sub.path, ctx));
      const stop = (fn) => (e) => { e.preventDefault(); e.stopPropagation(); fn(); };
      box.append(h("details", { class: "row", open: list.length <= 3 },
        h("summary", {},
          h("span", { class: "row-title" }, rowTitle(f, item, i, ctx)),
          h("span", { class: "row-actions" },
            iconBtn("up", "Move up", disabled || i === 0, stop(() => move(i, -1))),
            iconBtn("down", "Move down", disabled || i === list.length - 1, stop(() => move(i, 1))),
            iconBtn("copy", "Duplicate", disabled || full(), stop(() => { list.splice(i + 1, 0, copy(item)); commit(); })),
            iconBtn("trash", "Remove", disabled || (f.min !== undefined && list.length <= f.min), stop(() => { list.splice(i, 1); commit(); })))),
        body));
    });
    if (f.canAdd && !disabled && !full()) {
      box.append(h("button", { class: "btn small", type: "button", onclick: () => { list.push(blank(f.fields || [])); commit(); } }, icon("plus", 14), "Add"));
    }
  };
  draw();
  return box;
}

export function showErrors(ctx, details) {
  clearErrors(ctx);
  const unplaced = [];
  let first = null;
  for (const d of details || []) {
    let p = d.path || "";
    let slot = ctx.slots.get(p);
    while (!slot && p.includes("/")) { p = p.slice(0, p.lastIndexOf("/")); slot = ctx.slots.get(p); }
    if (!slot) { unplaced.push(d.message); continue; }
    slot.err.textContent = d.message;
    slot.err.hidden = false;
    slot.wrap.classList.add("has-error");
    const input = slot.wrap.querySelector("input, textarea, select");
    if (input) input.setAttribute("aria-invalid", "true");
    if (!first) first = input || slot.wrap;
  }
  if (first) { const row = first.closest("details"); if (row) row.open = true; first.focus(); }
  return unplaced;
}

export function clearErrors(ctx) {
  for (const s of ctx.slots.values()) {
    s.err.hidden = true;
    s.err.textContent = "";
    s.wrap.classList.remove("has-error");
    const input = s.wrap.querySelector("[aria-invalid]");
    if (input) input.removeAttribute("aria-invalid");
  }
}
