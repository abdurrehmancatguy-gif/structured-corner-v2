// Files: every picture and film the site publishes, by folder (pictures,
// category pictures, films), with where each is used and whether its sized
// copies are up to date. A file nothing uses is still published at its
// address until it goes to the trash, so those are listed first. Uploads
// here go to staging, then attach to the place picked for them.
import { api } from "../lib/api.js";
import { h, clear, useCss, nextId } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, confirmDialog, toast, guard } from "../lib/ui.js";
import { KINDS, dropZone, fmtBytes, progressList, progressRow, problems, sendOne } from "../lib/media.js";
import { cropDialog, BANNER_FRAMES, SQUARE_FRAME } from "../components/crop.js";

const TABS = [
  { key: "images", label: "Images", folder: "assets/img/", uploads: ["banner", "logo", "emblem"] },
  { key: "categories", label: "Category pictures", folder: "assets/cat/", uploads: ["category-photo", "cutout"] },
  { key: "films", label: "Films", folder: "assets/video/", uploads: ["reel"] },
  { key: "trash", label: "Trash" },
];
const KIND_LABEL = { "product-image": "Product photo", banner: "Banner", logo: "Logo", emblem: "Emblem",
  "category-photo": "Category photo", cutout: "Cut-out", reel: "Film", other: "Other picture", orphan: "Copy without its original" };
const base = (p) => String(p || "").split("/").pop();
const line = (s) => String(s || "").replace(/\s+/g, " ").trim();

export async function render(main, { sub, app }) {
  useCss("media");
  useCss("files");
  guard.clear();
  const tab = TABS.find((t) => t.key === String(sub || "").split("/")[0]) || TABS[0];
  const msgs = h("div", { class: "msgs" });
  const body = h("div", {});
  clear(main).append(
    h("div", { class: "page-head" }, h("div", {},
      h("h1", { tabindex: "-1" }, "Files"),
      h("p", { class: "sub" }, "Every picture and film the site publishes, where it is used, and whether its sized copies are up to date."))),
    h("nav", { class: "ftabs", "aria-label": "Kinds of file" }, TABS.map((t) =>
      h("a", { class: "ftab" + (t === tab ? " on" : ""), href: "#/content/files/" + t.key, "aria-current": t === tab ? "page" : null }, t.label))),
    msgs, body);
  if (tab.key === "trash") return drawTrash(body, msgs);

  const docs = {};
  const list = h("div", { class: "flist" }, h("p", { class: "loading" }, "Loading"));
  const up = h("section", { class: "card fupload" });
  body.append(up, list);
  let redraw = () => {};
  const refresh = async () => {
    try { await loadDocs(docs, tab); } catch (e) { /* the list below still shows what is there */ }
    redraw();
    drawList(list, tab, msgs, refresh);
  };
  try {
    await loadDocs(docs, tab);
    if (tab.uploads.includes("reel") && !app.state.products) {
      const l = await api("GET", "products");
      app.state.products = Object.fromEntries(l.items.map((it) => [it.id, it.data]));
    }
  } catch (e) {
    msgs.append(banner({ tone: "critical", title: e.message }));
  }
  redraw = drawUpload(up, tab, docs, app, refresh);
  drawList(list, tab, msgs, refresh);
}

// The documents an upload on this tab changes: their data names the places
// to pick from, and their revs go with the attach.
async function loadDocs(docs, tab) {
  const need = new Set(tab.uploads.map((k) => UP[k].doc));
  await Promise.all([...need].map(async (n) => { docs[n] = await api("GET", "documents/" + n); }));
}

// ---- uploads -----------------------------------------------------------------
// Each kind names the document it changes, the places to pick from and the
// attach target it sends. Crops are asked for after the upload, because the
// crop tool needs the picture's size as the server read it.

const UP = {
  banner: { doc: "home", label: "Hero banner",
    note: "Replaces the picture of the slide you pick. You crop it twice: a wide band for computers and a crop for phones. The old picture stays here until you move it to the trash.",
    picks: (docs) => [{ name: "slide", label: "Slide", options: slides(docs) }],
    target: async (v, staged, file) => {
      const c = await cropDialog({ file, width: staged.width, height: staged.height, frames: BANNER_FRAMES, title: "Crop the banner" });
      return c && { kind: "banner", slide: Number(v.slide), crop_desktop: c.crop_desktop, crop_phone: c.crop_phone };
    } },
  logo: { doc: "settings", label: "Logo",
    note: "The logo in use now goes to the trash, so you can put it back from there.",
    picks: () => [{ name: "variant", label: "Which logo", options: [
      { value: "dark", label: "Logo (the header)" }, { value: "light", label: "Logo on dark (the footer)" }] }],
    target: async (v) => ({ kind: "logo", variant: v.variant }) },
  emblem: { doc: "settings", label: "Emblem",
    note: "The favicon, the 32 and 16 px icons and the home screen icon are made from it. The emblem in use now goes to the trash.",
    picks: () => [],
    target: async () => ({ kind: "emblem" }) },
  "category-photo": { doc: "navigation", label: "Category photo",
    note: "Cropped square, and shown as a photo inside the circle of the entry you pick.",
    picks: (docs) => [{ name: "index", label: "Category", options: cats(docs) }],
    target: async (v, staged, file) => {
      const c = await cropDialog({ file, width: staged.width, height: staged.height, frames: SQUARE_FRAME, title: "Crop the circle picture" });
      return c && { kind: "category-photo", index: Number(v.index), crop: c.crop };
    } },
  cutout: { doc: "navigation", label: "Cut-out",
    note: "Trimmed to the object and stood in the circle of the entry you pick; an object much wider than it is tall is laid across the circle instead.",
    picks: (docs) => [{ name: "index", label: "Category", options: cats(docs) }],
    target: async (v) => ({ kind: "cutout", index: Number(v.index) }) },
  reel: { doc: "home", label: "Film",
    note: "Converted for the web on this computer before it is saved, and its poster is cut from it. One film at a time.",
    picks: (docs, app) => [{ name: "product", label: "Product the film links to", options: productOpts(app) },
      { name: "index", label: "Place in the row", options: places(docs, app) }],
    target: async (v) => ({ kind: "reel", product: v.product, index: Number(v.index) }) },
};

function slides(docs) {
  const s = (docs.home && docs.home.data.hero_slides) || [];
  return s.map((x, i) => ({ value: String(i), label: "Slide " + (i + 1) + ": " + line(x.headline) }));
}

function cats(docs) {
  const c = (docs.navigation && docs.navigation.data.categories) || [];
  return c.map((x, i) => ({ value: String(i), label: line(x.label) || "Entry " + (i + 1) }));
}

function productOpts(app) {
  return Object.entries(app.state.products || {})
    .sort((a, b) => (a[1].name || a[0]).localeCompare(b[1].name || b[0]))
    .map(([pid, d]) => ({ value: pid, label: (d.name || pid) + " (" + pid + ")" }));
}

// The homepage row holds up to 12 films (MAX_REELS on the server).
function places(docs, app) {
  const items = ((docs.home && docs.home.data.reels) || {}).items || [];
  const name = (pid) => (app.state.products && app.state.products[pid] && app.state.products[pid].name) || pid;
  return (items.length < 12 ? [{ value: String(items.length), label: "Add at the end of the row" }] : [])
    .concat(items.map((it, i) => ({ value: String(i), label: "Replace film " + (i + 1) + ": " + name(it.product) })));
}

// Returns its own redraw, so a finished upload can refresh the choices
// (a new film changes the places) while the progress lines stay.
function drawUpload(box, tab, docs, app, refresh) {
  let kind = tab.uploads[0];
  let busy = false;
  const uploads = progressList();
  const form = h("div", { class: "fform" });
  const group = nextId("kind");

  async function send(file, k, spec, vals) {
    if (busy) { toast("The file already chosen is still on its way."); return; }
    if (!docs[spec.doc]) { toast("This screen did not load everything it needs. Reload it and try again."); return; }
    busy = true;
    const row = progressRow(uploads, file.name);
    try {
      const res = await sendOne({ kind: k, file, row, rev: () => docs[spec.doc].rev,
        target: (staged) => spec.target(vals, staged, file) });
      if (res) {
        toast(res.trashed ? "Saved. The file it replaces is in the trash." : "Saved, and the site rebuilt with it.");
        await refresh();
      }
    } catch (e) {
      row.fail(problems(e).join(" "));
    } finally {
      busy = false;
    }
  }

  function draw() {
    const k = kind;
    const spec = UP[k];
    const vals = {};
    const picks = spec.picks(docs, app).map((p) => {
      const id = nextId("pick");
      vals[p.name] = p.options.length ? p.options[0].value : "";
      return h("div", { class: "field" }, h("label", { class: "f-label", for: id }, p.label),
        h("select", { id, class: "input", onchange: (e) => { vals[p.name] = e.target.value; } },
          p.options.map((o) => h("option", { value: o.value }, o.label))));
    });
    clear(form).append(h("p", { class: "help" }, spec.note + " File: " + KINDS[k].rule + "."), ...picks,
      dropZone({ kind: k, label: "Choose a file", onFiles: (files) => send(files[0], k, spec, vals) }));
  }

  box.append(h("h2", {}, "Upload"),
    ...(tab.key === "images" ? [h("p", { class: "sub fsub" }, "Product photos are added on each product's page, under Products.")] : []),
    h("fieldset", { class: "fkinds" }, h("legend", { class: "f-label" }, "What are you uploading?"),
      tab.uploads.map((k) => {
        const id = nextId("k");
        return h("label", { class: "fkind", for: id },
          h("input", { type: "radio", id, name: group, value: k, checked: k === kind, onchange: () => { kind = k; draw(); } }), UP[k].label);
      })),
    form, uploads);
  draw();
  return draw;
}

// ---- the library -------------------------------------------------------------

async function drawList(box, tab, msgs, refresh) {
  let r;
  try {
    r = await api("GET", "media");
  } catch (e) {
    clear(box).append(banner({ tone: "critical", title: e.message }));
    return;
  }
  const items = r.items.filter((it) => it.path.startsWith(tab.folder)).sort((a, b) => a.path.localeCompare(b.path));
  const kinds = [...new Set(items.map((it) => it.kind))];
  const count = (k) => items.filter((it) => it.kind === k).length;
  const groups = h("div", {});
  const id = nextId("show");
  let show = "all";
  const drawGroups = () => {
    const pick = items.filter((it) => show === "all" || it.kind === show);
    const unused = pick.filter((it) => !it.used_by.length);
    const used = pick.filter((it) => it.used_by.length);
    clear(groups).append(
      h("section", { class: "card" }, h("h2", {}, "Not used but still published (" + unused.length + ")"),
        h("p", { class: "sub fsub" }, unused.length
          ? "Nothing in the content points at these, but the site still publishes them at their addresses. Move the ones you do not need to the trash."
          : "Every file here is used by the content."),
        unused.length ? h("ul", { class: "fgrid" }, unused.map((it) => fileCard(it, (x) => trashFile(x, msgs, refresh)))) : null),
      h("section", { class: "card" }, h("h2", {}, "In use (" + used.length + ")"),
        used.length ? h("ul", { class: "fgrid" }, used.map((it) => fileCard(it))) : h("p", { class: "muted" }, "None.")));
  };
  const bar = kinds.length < 2 ? null : h("div", { class: "fbar" }, h("label", { class: "f-label", for: id }, "Show"),
    h("select", { id, class: "input", onchange: (e) => { show = e.target.value; drawGroups(); } },
      h("option", { value: "all" }, "All kinds (" + items.length + ")"),
      kinds.map((k) => h("option", { value: k }, (KIND_LABEL[k] || k) + " (" + count(k) + ")"))));
  clear(box).append(...[bar, groups].filter(Boolean));
  drawGroups();
}

// The smallest copy on disk makes the preview, so the screen does not load
// every full-size original.
const SMALL = ["-thumb.jpg", "-216.jpg", "-card-360.jpg", "-486.png", "-750.jpg", "-1320.jpg", "-card.jpg", "-600.jpg"];

function preview(it) {
  const name = base(it.path);
  const ok = (it.copies && it.copies.ok) || [];
  if (it.path.endsWith(".mp4")) {
    const poster = ok.find((p) => p.endsWith(".jpg"));
    return h("video", { class: "fprev film", src: "/" + it.path, poster: poster ? "/" + poster : null, preload: "none",
      controls: true, muted: true, playsinline: true, "aria-label": "Play " + name });
  }
  let src = it.path;
  for (const s of SMALL) {
    const hit = ok.find((p) => p.endsWith(s));
    if (hit) { src = hit; break; }
  }
  return h("a", { class: "fprev-link", href: "/" + it.path, target: "_blank", rel: "noopener noreferrer", "aria-label": "Open " + name + " in a new tab" },
    h("img", { class: "fprev" + (it.path.endsWith(".png") ? " alpha" : ""), src: "/" + src, alt: "", loading: "lazy" }));
}

function usedBy(it) {
  if (!it.used_by.length) {
    return h("p", { class: "fused muted" }, it.kind === "orphan" ? "A sized copy whose original is gone." : "Not used by the content.");
  }
  return h("div", { class: "fused" }, h("span", { class: "fk" }, "Used by"),
    h("ul", {}, it.used_by.map((u) => h("li", {}, u.link ? h("a", { href: u.link }, u.where) : u.where))));
}

// A copy make_derivatives writes is out of date when it was not made from
// the original's current bytes; the others can only be there or missing.
function copyState(it) {
  const c = it.copies || { ok: [], missing: [], stale: [] };
  const all = [...c.ok.map((p) => [p, "ok"]), ...c.stale.map((p) => [p, "out of date"]), ...c.missing.map((p) => [p, "missing"])];
  if (!all.length) return null;
  const bad = [c.missing.length ? c.missing.length + " missing" : null, c.stale.length ? c.stale.length + " out of date" : null].filter(Boolean);
  return h("details", { class: "fcopies" + (bad.length ? " bad" : "") },
    h("summary", {}, "Sized copies: " + (bad.length ? bad.join(", ") + " of " + all.length : all.length + ", none missing or out of date")),
    h("ul", {}, all.map(([p, s]) => h("li", {}, base(p) + ": " + s))));
}

function fileCard(it, onTrash) {
  const name = base(it.path);
  const facts = [it.width && it.height ? it.width + "x" + it.height + " px" : null, fmtBytes(it.bytes),
    typeof it.duration === "number" ? it.duration.toFixed(1) + " s" : null].filter(Boolean).join(", ");
  return h("li", { class: "fcard" }, preview(it),
    h("div", { class: "fbody" },
      h("p", { class: "fname" }, h("span", { class: "fn" }, name),
        h("span", { class: "badge" + (it.kind === "orphan" ? " red" : "") }, KIND_LABEL[it.kind] || it.kind)),
      h("p", { class: "ffacts" }, facts),
      usedBy(it), copyState(it),
      onTrash ? h("button", { class: "btn small danger-text", type: "button", "aria-label": "Move " + name + " to the trash",
        onclick: () => onTrash(it) }, icon("trash", 14), "Move to trash") : null));
}

async function trashFile(it, msgs, refresh) {
  const name = base(it.path);
  const c = it.copies || { ok: [], stale: [] };
  const n = c.ok.length + c.stale.length;
  const ok = await confirmDialog({ title: "Move " + name + " to the trash?",
    body: [(n ? "It and its " + n + (n === 1 ? " sized copy" : " sized copies") : "It") + " leave the site's files now and wait in the trash, where you can restore them.",
      "It leaves the live site at the next publish."],
    confirm: "Move to trash", danger: true });
  if (!ok) return;
  clear(msgs);
  try {
    await api("POST", "media/trash", { body: { path: it.path } });
    toast(name + " moved to the trash.");
    await refresh();
  } catch (e) {
    const refs = e.details && e.details.refs;
    msgs.append(banner({ tone: "critical", title: e.message,
      items: refs ? refs.map((r) => (r.link ? h("a", { href: r.link }, r.where) : r.where)) : problems(e).slice(1) }));
    msgs.scrollIntoView({ block: "nearest" });
  }
}

// ---- trash -------------------------------------------------------------------

function when(at) {
  const d = new Date(at);
  return isNaN(d) ? String(at || "") : d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function drawTrash(body, msgs) {
  clear(body).append(h("p", { class: "loading" }, "Loading"));
  let r;
  try {
    r = await api("GET", "media/trash");
  } catch (e) {
    clear(body).append(banner({ tone: "critical", title: e.message }));
    return;
  }
  const again = () => drawTrash(body, msgs);
  clear(body).append(h("section", { class: "card flush" },
    h("p", { class: "sub ftrash-intro" }, "Files moved to the trash wait here, outside the published site. Restoring one puts it and its sized copies back where they were."),
    r.items.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["File", "Kind", "Moved to the trash", "Files", "Size", "Restore"].map((c) => h("th", { scope: "col" }, c)))),
      h("tbody", {}, r.items.map((it) => trashRow(it, msgs, again)))))
      : h("p", { class: "empty" }, "The trash is empty.")));
}

// A logo or the emblem has one fixed name, so restoring one swaps it with
// the file in use; any other name that is taken now blocks the restore.
function trashRow(it, msgs, again) {
  const swap = it.kind === "logo" || it.kind === "emblem";
  const blocked = (it.blocked || []).length > 0;
  const name = base(it.path);
  const cell = blocked && !swap
    ? h("span", { class: "muted" }, "A file with the same name is on the site now (" + it.blocked.map(base).join(", ") + "). Move that one to the trash first.")
    : h("button", { class: "btn small", type: "button", "aria-label": "Restore " + name, onclick: () => restore(it, swap && blocked, msgs, again) }, "Restore");
  return h("tr", {},
    h("td", {}, h("span", { class: "t-name" }, name), h("span", { class: "t-id" }, it.path)),
    h("td", {}, KIND_LABEL[it.kind] || it.kind || ""),
    h("td", {}, when(it.at)),
    h("td", { class: "num" }, String((it.files || []).length)),
    h("td", { class: "num" }, fmtBytes(it.bytes)),
    h("td", {}, cell));
}

async function restore(it, swap, msgs, again) {
  const what = (KIND_LABEL[it.kind] || "file").toLowerCase();
  if (swap) {
    const ok = await confirmDialog({ title: "Put this " + what + " back?",
      body: ["The " + what + " in use now goes to the trash in its place, so you can switch back again."], confirm: "Restore" });
    if (!ok) return;
  }
  clear(msgs);
  try {
    await api("POST", "media/restore", { body: { trash_id: it.trash_id } });
    toast(it.kind === "product-image"
      ? base(it.path) + " is back in the files. Put it on its product from that product's Photos."
      : "Restored.");
    again();
  } catch (e) {
    msgs.append(banner({ tone: "critical", title: e.message, items: problems(e).slice(1) }));
  }
}
