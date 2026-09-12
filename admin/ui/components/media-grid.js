// A product's photos as tiles. The first is the card image; the second is
// the one the card swaps to when a shopper points at it (the box shot).
// Moving and removing change the draft, which the save bar saves like any
// other field; an upload is saved at once, and the product then reloads.
import { api } from "../lib/api.js";
import { h, clear, getPtr, setPtr, thumb, useCss, nextId } from "../lib/dom.js";
import { iconBtn } from "../lib/forms.js";
import { announce, banner, confirmDialog, toast, guard } from "../lib/ui.js";
import { dropZone, progressList, progressRow, problems, saveFirst, sendOne } from "../lib/media.js";

const TITLES = ["Card image", "Hover image (box shot)"];

// What outlives a redraw of the form (saving first, the reload after an
// upload): the list of files on their way and whether one is being sent.
// Kept per editor, which is one visit to the product.
const visits = new WeakMap();

export function mediaGrid({ f, draft, ctx, pid, ed, app }) {
  useCss("media");
  if (!visits.has(ed)) visits.set(ed, { uploads: progressList(), busy: false });
  const st = visits.get(ed);
  const tiles = h("ol", { class: "mgrid", "aria-label": "Photos, in the order the shop shows them" });
  const extra = h("div", {});
  const uploads = st.uploads;
  const err = h("p", { class: "error", hidden: true });
  const wrap = h("div", { class: "field t-images", dataset: { ptr: f.path } }, tiles, extra,
    dropZone({ kind: "product-image", multiple: true, label: "Add photos", onFiles }),
    uploads, f.help ? h("p", { class: "help" }, f.help) : null, err);
  ctx.slots.set(f.path, { err, wrap });
  let spare = [];          // this product's frames in the library that nothing uses
  let dragFrom = null;     // the tile a pointer is dragging, by position

  const list = () => (Array.isArray(getPtr(draft, f.path)) ? getPtr(draft, f.path) : []);
  const set = (next, focus) => { setPtr(draft, f.path, next); ctx.onChange(f); draw(focus); };

  // act names the button that moved it, which keeps the focus; a drag has none
  function move(i, j, act) {
    const a = list().slice();
    const [name] = a.splice(i, 1);
    a.splice(j, 0, name);
    set(a, act ? { index: j, act } : null);
    announce(name + " is now photo " + (j + 1) + " of " + a.length + (j < 2 ? ", the " + TITLES[j].toLowerCase() : "") + ". Save to apply.");
  }

  function takeOff(i) {
    const a = list().slice();
    const [name] = a.splice(i, 1);
    set(a, { index: Math.min(i, a.length - 1), act: "off" });
    announce(name + " taken off this product. Save to apply.");
  }

  async function trash(i) {
    const name = list()[i];
    const others = guard.dirty();
    const ok = await confirmDialog({
      title: "Remove " + name + " and move the file to the trash?",
      body: ["The product is saved without this photo now" + (others ? ", together with the other changes you made here" : "") + ". "
        + "Then the photo and its sized copies leave the site's files and wait in the trash, where Files can restore them.",
      "It leaves the live site at the next publish."],
      confirm: "Remove and trash", danger: true });
    if (!ok) return;
    const a = list().slice();
    a.splice(i, 1);
    setPtr(draft, f.path, a);
    ctx.onChange(f);
    await ed.save();
    const now = ed.data();
    if (!now || (now.images || []).includes(name)) return;      // not saved: the editor said why
    try {
      await api("POST", "media/trash", { body: { path: "assets/img/" + name } });
      toast(name + " moved to the trash. Files can restore it.");
    } catch (e) {
      const items = e.details && e.details.refs ? e.details.refs.map((r) => r.where) : problems(e).slice(1);
      ed.msgs.append(banner({ tone: "warning", title: "Taken off this product, but the file was not moved to the trash. " + e.message, items }));
    }
  }

  async function onFiles(files) {
    if (st.busy) { toast("The photos already chosen are still uploading."); return; }
    if (!(await saveFirst(ed, () => guard.dirty()))) return;
    st.busy = true;
    clear(uploads);
    let rev = ed.rev();
    let added = 0;
    const failed = [];
    try {
      for (const file of files) {
        const row = progressRow(uploads, file.name);
        try {
          const res = await sendOne({ kind: "product-image", file, row, rev: () => rev,
            target: async () => ({ kind: "product-image", product: pid }) });
          if (res) {
            rev = res.rev;
            added++;
            if (app.state.products) app.state.products[pid] = res.data;
          }
        } catch (e) {
          const why = problems(e).join(" ");
          row.fail(why);
          failed.push(file.name + ": " + why);
        }
      }
    } finally {
      st.busy = false;
    }
    if (!added) return;
    await ed.reload();
    toast(added === 1 ? "Photo added and saved." : added + " photos added and saved.");
    if (failed.length) ed.msgs.append(banner({ tone: "critical", title: "Some files were not added.", items: failed }));
  }

  function act(name, label, disabled, fn, key) {
    const b = iconBtn(name, label, disabled, fn);
    b.dataset.act = key;
    return b;
  }

  // A pointer can also drag a tile to its new place; the buttons do the same
  // from the keyboard. Only a tile of this grid is taken here: a file dragged
  // in from the computer goes to the drop zone.
  function dragTile(el, i) {
    el.addEventListener("dragstart", (e) => {
      dragFrom = i;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("application/x-bgs-frame", list()[i]);
      el.classList.add("dragging");
    });
    el.addEventListener("dragend", () => { dragFrom = null; el.classList.remove("dragging"); });
    el.addEventListener("dragover", (e) => {
      if (dragFrom === null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      el.classList.add("over");
    });
    el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("over"); });
    el.addEventListener("drop", (e) => {
      if (dragFrom === null) return;
      e.preventDefault();
      const from = dragFrom;
      dragFrom = null;
      el.classList.remove("over");
      if (from !== i) move(from, i, null);
    });
    return el;
  }

  function tile(name, i, n) {
    const title = TITLES[i] || "Photo " + (i + 1);
    const make = i > 0 ? h("button", { class: "btn small m-make", type: "button", "aria-label": "Make " + name + " the card image",
      onclick: () => move(i, 0, "make") }, "Make card image") : null;
    if (make) make.dataset.act = "make";
    return dragTile(h("li", { class: "mtile" + (i === 0 ? " first" : ""), draggable: "true" },
      h("img", { src: thumb(name), alt: "", loading: "lazy", width: "156", height: "156", draggable: "false" }),
      h("span", { class: "m-label" }, title),
      h("span", { class: "m-name" }, name),
      h("div", { class: "m-actions" }, make,
        act("left", "Move " + name + " left", i === 0, () => move(i, i - 1, "left"), "left"),
        act("right", "Move " + name + " right", i === n - 1, () => move(i, i + 1, "right"), "right"),
        act("close", "Take " + name + " off this product", false, () => takeOff(i), "off"),
        act("trash", "Take " + name + " off and move the file to the trash", false, () => trash(i), "trash"))), i);
  }

  // Redrawn after every change; focus goes back to the same button on the
  // tile that moved, or its nearest usable one, so the keyboard keeps its place.
  function draw(focus) {
    const a = list();
    clear(tiles).append(...a.map((n, i) => tile(n, i, a.length)));
    clear(extra);
    if (a.length === 0) {
      extra.append(h("p", { class: "muted" }, "No photos yet. The first photo you add becomes the card image; the second shows when a shopper points at the card."));
    } else if (a.length === 1) {
      extra.append(banner({ tone: "warning", title: "One photo only: the card has no second picture to swap to when a shopper points at it.",
        items: ["Add the box shot as the second photo."] }));
    }
    const left = spare.filter((n) => !a.includes(n));
    if (left.length) {
      const id = nextId("spare");
      extra.append(h("div", { class: "m-add" },
        h("label", { class: "f-label", for: id }, "Put back a photo of this product that is not in use"),
        h("select", { id, class: "input", onchange: (e) => { if (e.target.value) set(a.concat([e.target.value])); } },
          h("option", { value: "" }, "Choose a photo"), left.map((n) => h("option", { value: n }, n)))));
    }
    if (focus && tiles.children[focus.index]) {
      const t = tiles.children[focus.index];
      const b = t.querySelector('[data-act="' + focus.act + '"]:not([disabled])') || t.querySelector("button:not([disabled])");
      if (b) b.focus();
    }
  }

  // Frames named after this product that no product uses: taken off before,
  // or brought back from the trash. Only complete ones (every size there)
  // are offered, because the save refuses the others.
  api("GET", "media?kind=product-image&unused=1").then((r) => {
    const re = new RegExp("^" + pid + "-\\d+\\.jpg$");
    spare = r.items.filter((it) => !it.copies.missing.length).map((it) => it.path.replace(/^assets\/img\//, "")).filter((n) => re.test(n));
    if (spare.length) draw();
  }).catch(() => {});

  draw();
  return wrap;
}
