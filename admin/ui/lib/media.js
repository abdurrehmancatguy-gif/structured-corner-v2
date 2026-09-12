// Uploads, the same way on every screen. A picture or film is checked here
// first (type, size, pixels), so a wrong file is refused before a long
// upload; then it goes to staging as the raw body with a progress bar, and
// then it is attached to the place it is for, which saves and rebuilds. The
// server checks everything again: these checks only save the owner a wait.
import { api, upload } from "./api.js";
import { h } from "./dom.js";
import { confirmDialog } from "./ui.js";
import { icon } from "../icons.js";

const MB = 1024 * 1024;
const PHOTO = ["image/jpeg", "image/png", "image/webp"];
const PNG = ["image/png"];
const HEIC = "HEIC and AVIF photos cannot be read here. Export the photo as a JPEG first (in Photos or Preview: File, Export).";
const REFUSED = {
  "image/heic": HEIC, "image/heif": HEIC, "image/avif": HEIC,
  "image/svg+xml": "SVG files cannot be uploaded: they can carry script, and everything in the shop's assets is published.",
  "image/gif": "GIF files cannot be uploaded. Use a JPEG or a PNG; films go in as MP4.",
};
const BY_EXT = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", mp4: "video/mp4",
  heic: "image/heic", heif: "image/heif", avif: "image/avif", svg: "image/svg+xml", gif: "image/gif" };
const px = (w, hh) => w + "x" + hh + " px";

// The server's rules (media.KINDS, media.stage_image and video.probe),
// repeated so the owner hears about a wrong file before sending it.
export const KINDS = {
  "product-image": { label: "product photo", cap: 25 * MB, types: PHOTO,
    rule: "JPEG, PNG or WebP, at least 1000 px on the short side, up to 25 MB",
    check: (d) => (Math.min(d.width, d.height) < 1000 ? "A product photo needs at least 1000 px on its short side; this one is " + px(d.width, d.height) + "." : null) },
  banner: { label: "banner picture", cap: 30 * MB, types: PHOTO,
    rule: "JPEG, PNG or WebP, at least 2400 px wide and 790 px tall, up to 30 MB",
    check: (d) => (d.width < 2400 || d.height < 790 ? "A banner picture needs to be at least 2400 px wide and 790 px tall; this one is " + px(d.width, d.height) + "." : null) },
  "category-photo": { label: "category photo", cap: 10 * MB, types: PHOTO,
    rule: "JPEG, PNG or WebP, at least 432 px on the short side, up to 10 MB",
    check: (d) => (Math.min(d.width, d.height) < 432 ? "A category photo needs at least 432 px on its short side; this one is " + px(d.width, d.height) + "." : null) },
  cutout: { label: "cut-out", cap: 10 * MB, types: PNG,
    rule: "a PNG with a transparent background, up to 10 MB",
    check: () => null },
  logo: { label: "logo", cap: 10 * MB, types: PNG,
    rule: "a PNG with a transparent background, at least 486 px wide, up to 10 MB",
    check: (d) => (d.width < 486 ? "A logo needs to be at least 486 px wide; this one is " + d.width + " px." : null) },
  emblem: { label: "emblem", cap: 10 * MB, types: PNG,
    rule: "a PNG with a transparent background, at least 180 px on its long side, up to 10 MB",
    check: (d) => (Math.max(d.width, d.height) < 180 ? "The emblem needs at least 180 px on its long side; this one is " + px(d.width, d.height) + "." : null) },
  reel: { label: "film", cap: 80 * MB, types: ["video/mp4"],
    rule: "an upright MP4 (9:16), at least 540x960, 1 to 30 seconds, up to 80 MB",
    check: (d) => {
      if (!d.width) return null;       // the browser could not read it; the server decides
      if (d.width >= d.height) return "The row shows films upright (9:16); this one is " + d.width + "x" + d.height + ", landscape or square.";
      if (d.width < 540 || d.height < 960) return "A film needs to be at least 540x960; this one is " + d.width + "x" + d.height + ".";
      if (d.duration > 30.05) return "A film can be at most 30 s long; this one is " + d.duration.toFixed(1) + " s. Trim it first.";
      if (d.duration < 1) return "The film is shorter than a second.";
      return null;
    } },
};

export const accept = (kind) => KINDS[kind].types.join(",");

export function typeOf(file) {
  const ext = (String(file.name || "").split(".").pop() || "").toLowerCase();
  return file.type || BY_EXT[ext] || "";
}

export function fmtBytes(n) {
  if (typeof n !== "number") return "";
  return n < MB ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / MB).toFixed(1) + " MB";
}

async function pictureSize(file) {
  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch (e) {
    throw new Error("This picture could not be read. Save it again as a JPEG or PNG and try once more.");
  }
  const out = { width: bmp.width, height: bmp.height };
  bmp.close();
  return out;
}

// A film's size and length from the browser's own reading of it. One the
// browser cannot play (some phone formats) is left to the server to judge.
function filmSize(file) {
  return new Promise((resolve) => {
    const v = document.createElement("video");
    const url = URL.createObjectURL(file);
    const done = (val) => { URL.revokeObjectURL(url); v.removeAttribute("src"); resolve(val); };
    v.preload = "metadata";
    v.muted = true;
    v.onloadedmetadata = () => done({ width: v.videoWidth, height: v.videoHeight, duration: v.duration });
    v.onerror = () => done({});
    v.src = url;
  });
}

// Type, size cap and pixels, in that order, so the cheap checks come first.
export async function precheck(kind, file) {
  const k = KINDS[kind];
  const type = typeOf(file);
  if (REFUSED[type]) throw new Error(REFUSED[type]);
  if (!k.types.includes(type)) throw new Error("A " + k.label + " must be " + k.rule.split(",")[0] + ". This file is not.");
  if (file.size > k.cap) {
    throw new Error("A " + k.label + " can be at most " + k.cap / MB + " MB. This file is " + (file.size / MB).toFixed(1) + " MB.");
  }
  const dims = kind === "reel" ? await filmSize(file) : await pictureSize(file);
  const why = k.check(dims);
  if (why) throw new Error(why);
  return Object.assign({ type }, dims);
}

// ---- choosing files ------------------------------------------------------------

export function pickFiles({ types, multiple = false } = {}) {
  return new Promise((resolve) => {
    const input = h("input", { type: "file", accept: types, multiple, class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
    const finish = (files) => { input.remove(); resolve(files); };
    input.addEventListener("change", () => finish([...input.files]));
    input.addEventListener("cancel", () => finish([]));
    document.body.append(input);
    input.click();
  });
}

// A button that opens the file picker, on an area that also takes a drop.
export function dropZone({ kind, multiple = false, label, hint, onFiles }) {
  const zone = h("div", { class: "drop" },
    h("button", { class: "btn", type: "button", onclick: async () => {
      const files = await pickFiles({ types: accept(kind), multiple });
      if (files.length) onFiles(files);
    } }, icon("upload", 16), label),
    h("span", { class: "drop-hint" }, hint || "or drop " + (multiple ? "files" : "a file") + " here: " + KINDS[kind].rule + "."));
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  });
  return zone;
}

// ---- progress -------------------------------------------------------------------
// One line per file: its name, a bar and what is happening. Only the steps
// are read out, not every percent.

export const progressList = () => h("ul", { class: "uploads", "aria-live": "polite" });

export function progressRow(list, name) {
  const bar = h("progress", { max: "1", "aria-label": "Progress for " + name });
  bar.value = 0;
  const msg = h("span", { class: "up-msg" }, "Waiting");
  const el = h("li", { class: "up-row" }, h("span", { class: "up-name" }, name), bar, msg);
  list.append(el);
  const say = (text) => { if (msg.textContent !== text) msg.textContent = text; };
  return {
    el,
    step(text, frac) {
      say(text);
      if (frac === null) bar.removeAttribute("value");
      else if (frac !== undefined) bar.value = frac;
    },
    done(text) { el.classList.add("ok"); bar.value = 1; say(text); },
    fail(text) { el.classList.add("bad"); bar.hidden = true; say(text); },
  };
}

// What went wrong, with the server's own details when it sent any.
export function problems(e) {
  const d = e && e.details;
  const out = [(e && e.message) || "Something went wrong."];
  if (Array.isArray(d)) out.push(...d.map((x) => x && x.message).filter(Boolean));
  else if (d && Array.isArray(d.problems)) out.push(...d.problems);
  if (d && d.restored) out.push("Everything was put back as it was.");
  if (e && e.code === "stale_rev") out.push("It was saved somewhere else meanwhile. Reload this screen and upload the file again.");
  return out;
}

// ---- sending --------------------------------------------------------------------

// A film is converted on the server in the background: ask again every
// second and a half until it is done or has failed.
export async function waitJob(id, onTick) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    const j = await api("GET", "jobs/" + id);
    if (onTick) onTick(j);
    if (j.state === "done") return j.result || {};
    if (j.state === "failed") {
      const e = new Error((j.error && j.error.message) || "The film could not be prepared.");
      e.code = (j.error && j.error.code) || "job_failed";
      e.details = j.error && j.error.details;
      throw e;
    }
  }
}

// One file from start to finish. target(staged, info) gives the attach
// target, or null when the owner cancels (the crop tool); rev() is read at
// attach time, so each file in a row uses the version the one before saved.
export async function sendOne({ kind, file, row, target, rev }) {
  row.step("Checking the file", 0);
  const info = await precheck(kind, file);
  row.step("Uploading", 0);
  const staged = await upload("media/staging?kind=" + encodeURIComponent(kind), file,
    { type: info.type, onProgress: (f) => row.step("Uploading", f) });
  row.step("Uploaded", 1);
  const t = await target(staged, info);
  if (!t) {
    row.fail("Cancelled: nothing was changed.");
    return null;
  }
  row.step(kind === "reel" ? "Starting the film" : "Saving and rebuilding the site", null);
  const res = await api("POST", "media/attach", { body: { staging_id: staged.staging_id, expect_rev: rev(), target: t } });
  if (res && res.job) {
    const out = await waitJob(res.job, (j) => row.step(j.state === "queued" ? "Waiting for the film converter" : "Converting the film for the web", null));
    row.done("Saved");
    return out;
  }
  row.done("Saved");
  return res;
}

// An upload saves at once and the screen then reloads, which would drop
// edits not saved yet, so those are saved first when the owner agrees.
export async function saveFirst(ed, dirty) {
  if (!dirty()) return true;
  const ok = await confirmDialog({ title: "Save your changes first?",
    body: ["An upload is saved straight away, and this screen then reloads. Save what you changed here first so it is not lost."],
    confirm: "Save and continue" });
  if (!ok) return false;
  await ed.save();
  return !dirty();
}
