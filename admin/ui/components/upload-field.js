// Upload buttons for the picture and film fields of the document editors:
// the homepage banner and films, the category circles, the logos and the
// emblem. A field's schema entry says what its file is (field.upload); the
// buttons send the file to staging, attach it (which saves and rebuilds),
// and then reload the document.
import { h } from "../lib/dom.js";
import { icon } from "../icons.js";
import { guard, toast } from "../lib/ui.js";
import { KINDS, accept, pickFiles, progressList, progressRow, problems, saveFirst, sendOne } from "../lib/media.js";
import { cropDialog, BANNER_FRAMES, SQUARE_FRAME } from "./crop.js";

const index = (ptr, re) => {
  const m = String(ptr).match(re);
  return m ? Number(m[1]) : null;
};

// The buttons each kind of field offers, and the attach target each sends.
// A poster or a site icon is made from another upload, so it has none.
const BUTTONS = {
  banner: (ptr) => {
    const slide = index(ptr, /^\/hero_slides\/(\d+)\//);
    return slide === null ? [] : [{ label: "Upload a new picture", kind: "banner",
      target: async (staged, file) => {
        const c = await cropDialog({ file, width: staged.width, height: staged.height, frames: BANNER_FRAMES,
          title: "Crop the banner for slide " + (slide + 1) });
        return c && { kind: "banner", slide, crop_desktop: c.crop_desktop, crop_phone: c.crop_phone };
      } }];
  },
  reel: (ptr, item) => {
    const i = index(ptr, /^\/reels\/items\/(\d+)\//);
    return i === null ? [] : [{ label: "Upload a new film", kind: "reel",
      target: async () => ({ kind: "reel", product: item.product, index: i }) }];
  },
  category: (ptr) => {
    const i = index(ptr, /^\/categories\/(\d+)\//);
    return i === null ? [] : [
      { label: "Upload a photo", kind: "category-photo",
        target: async (staged, file) => {
          const c = await cropDialog({ file, width: staged.width, height: staged.height, frames: SQUARE_FRAME, title: "Crop the circle picture" });
          return c && { kind: "category-photo", index: i, crop: c.crop };
        } },
      { label: "Upload a cut-out", kind: "cutout", target: async () => ({ kind: "cutout", index: i }) },
    ];
  },
  "logo-dark": () => [{ label: "Upload a new logo", kind: "logo", target: async () => ({ kind: "logo", variant: "dark" }) }],
  "logo-light": () => [{ label: "Upload a new logo", kind: "logo", target: async () => ({ kind: "logo", variant: "light" }) }],
  emblem: () => [{ label: "Upload a new emblem", kind: "emblem", target: async () => ({ kind: "emblem" }) }],
};

// getEd returns the screen's editor (lib/editor.js), for its rev, save and
// reload. The result is the ctx.uploadActions hook lib/forms.js calls; a
// screen makes it once per visit. Saving first or reloading draws the form
// again, and each field's progress list then moves into the new field with
// its rows, so a file on its way stays in view. One file at a time.
export function uploadActions(getEd) {
  const lists = new Map();
  let busy = false;
  return (f, ptr, item) => {
    const buttons = (BUTTONS[f.upload] || (() => []))(ptr, item || {});
    if (!buttons.length) return null;
    const key = ptr + " " + f.upload;
    if (!lists.has(key)) lists.set(key, progressList());
    const list = lists.get(key);

    async function run(b) {
      if (busy) { toast("The file already chosen is still on its way."); return; }
      const ed = getEd();
      // the file is chosen first: a browser opens its file chooser only
      // straight after a click, and saving other changes takes a moment
      const files = await pickFiles({ types: accept(b.kind) });
      if (!files.length) return;
      if (!(await saveFirst(ed, () => guard.dirty()))) return;
      busy = true;
      const row = progressRow(list, files[0].name);
      try {
        const res = await sendOne({ kind: b.kind, file: files[0], row, rev: () => ed.rev(),
          target: (staged) => b.target(staged, files[0]) });
        if (!res) return;
        // a film takes a while: if the owner has moved on or started other
        // edits meanwhile, reloading would throw those away
        if (list.isConnected && !guard.dirty()) {
          await ed.reload();
          toast(res.trashed ? "Saved. The file it replaces is in the trash." : "Saved, and the site rebuilt with it.");
        } else {
          toast("The new " + KINDS[b.kind].label + " is saved. Reload this screen to see it here.");
        }
      } catch (e) {
        row.fail(problems(e).join(" "));
      } finally {
        busy = false;
      }
    }

    return h("div", { class: "media-up" },
      h("div", { class: "media-actions" }, buttons.map((b) =>
        h("button", { class: "btn small", type: "button", onclick: () => run(b) }, icon("upload", 14), b.label))),
      list);
  };
}
