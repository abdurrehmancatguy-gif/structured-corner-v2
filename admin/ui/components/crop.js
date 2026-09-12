// The crop tool: the picture with one fixed-shape frame per target (a banner
// has a wide desktop band and a phone crop), each moved and resized by
// pointer or keyboard. Only where the frames sit is sent, as fractions of the
// picture; the server cuts the files, so nothing is drawn to a canvas here.
import { h, nextId } from "../lib/dom.js";

// The shapes and minimum widths are the server's (media.render_banner and
// media.render_category): a smaller crop would have to be enlarged.
export const BANNER_FRAMES = [
  { key: "crop_desktop", label: "Desktop", aspect: 2400 / 790, need: 2400, what: "the wide band on computers (2400x790)" },
  { key: "crop_phone", label: "Phone", aspect: 1110 / 600, need: 1110, what: "the crop phones show (1110x600)" },
];
export const SQUARE_FRAME = [
  { key: "crop", label: "Circle", aspect: 1, need: 432, what: "the square the circle is cut from (432x432)" },
];

export function cropDialog({ file, width: W, height: H, frames, title }) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const hint = nextId("crop");
    const stage = h("div", { class: "crop-stage" }, h("img", { src: url, alt: "", draggable: "false" }));
    const readout = h("ul", { class: "crop-read" });
    const d = h("dialog", { class: "dlg crop-dlg" });
    const finish = (v) => { d.close(); d.remove(); URL.revokeObjectURL(url); resolve(v); };
    d.addEventListener("cancel", (e) => { e.preventDefault(); finish(null); });

    const all = frames.map((f, i) => frame(f, i));
    function frame(f, i) {
      const maxW = Math.min(W, H * f.aspect);
      const minW = Math.min(f.need, maxW);
      const s = { f, w: maxW, x: 0, y: 0 };
      s.x = (W - s.w) / 2;
      s.y = (H - s.w / f.aspect) / 2;
      const handle = h("span", { class: "crop-handle", tabindex: "0", role: "slider",
        "aria-label": "Size of the " + f.label.toLowerCase() + " crop", "aria-describedby": hint,
        "aria-valuemin": String(Math.round(minW)), "aria-valuemax": String(Math.round(maxW)) });
      const el = h("div", { class: "crop-frame f" + i, tabindex: "0", role: "group", "aria-roledescription": "crop frame",
        "aria-label": f.label + " crop: " + f.what, "aria-describedby": hint },
        h("span", { class: "crop-tag", "aria-hidden": "true" }, f.label), handle);
      const line = h("li", {});
      readout.append(line);
      s.el = el;

      const clamp = () => {
        s.w = Math.max(minW, Math.min(s.w, maxW));
        s.x = Math.max(0, Math.min(s.x, W - s.w));
        s.y = Math.max(0, Math.min(s.y, H - s.w / f.aspect));
      };
      // a resize keeps the top left corner where it is, as far as it can
      const grow = (w) => {
        s.w = Math.max(minW, Math.min(w, W - s.x, (H - s.y) * f.aspect));
        clamp();
      };
      s.place = () => {
        const hgt = s.w / f.aspect;
        el.style.setProperty("left", (s.x / W) * 100 + "%");
        el.style.setProperty("top", (s.y / H) * 100 + "%");
        el.style.setProperty("width", (s.w / W) * 100 + "%");
        el.style.setProperty("height", (hgt / H) * 100 + "%");
        const size = Math.round(s.w) + "x" + Math.round(hgt) + " px";
        handle.setAttribute("aria-valuenow", String(Math.round(s.w)));
        handle.setAttribute("aria-valuetext", size + " of the picture");
        line.textContent = f.label + ": " + size + " of the picture, for " + f.what + ".";
      };
      const front = () => { all.forEach((o) => o.el.classList.toggle("on", o === s)); };

      el.addEventListener("focusin", front);
      el.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        front();
        el.focus();
        const sizing = e.target === handle;
        const scale = W / stage.getBoundingClientRect().width;
        const start = { cx: e.clientX, cy: e.clientY, x: s.x, y: s.y, w: s.w };
        el.setPointerCapture(e.pointerId);
        const move = (ev) => {
          const dx = (ev.clientX - start.cx) * scale;
          const dy = (ev.clientY - start.cy) * scale;
          if (sizing) {
            // follow whichever way the pointer went further, keeping the shape
            grow(start.w + (Math.abs(dx) >= Math.abs(dy * f.aspect) ? dx : dy * f.aspect));
          } else {
            s.x = start.x + dx;
            s.y = start.y + dy;
            clamp();
          }
          s.place();
        };
        const up = () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", up);
          el.removeEventListener("pointercancel", up);
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
        el.addEventListener("pointercancel", up);
      });
      el.addEventListener("keydown", (e) => {
        const k = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
        if (!k) return;
        e.preventDefault();
        const step = e.shiftKey ? 0.1 : 0.01;
        if (e.target === handle) {
          grow(s.w + (k[0] + k[1]) * step * W);
        } else {
          s.x += k[0] * step * W;
          s.y += k[1] * step * H;
          clamp();
        }
        s.place();
      });
      stage.append(el);
      s.place();
      return s;
    }

    const rect = (s) => {
      const x = s.x / W;
      const y = s.y / H;
      return { x, y, w: Math.min(s.w / W, 1 - x), h: Math.min(s.w / s.f.aspect / H, 1 - y) };
    };
    const one = frames.length === 1;
    d.append(
      h("h2", {}, title),
      h("p", { id: hint },
        (one ? "Drag the frame" : "Drag each frame") + " to the part of the picture to keep, and drag its corner to resize it. "
        + "With the keyboard, the arrow keys move a frame and, on its corner, resize it; hold Shift for larger steps."),
      h("div", { class: "crop-wrap" }, stage),
      readout,
      h("div", { class: "dlg-actions" },
        h("button", { class: "btn", type: "button", onclick: () => finish(null) }, "Cancel"),
        h("button", { class: "btn primary", type: "button",
          onclick: () => finish(Object.fromEntries(all.map((s) => [s.f.key, rect(s)]))) }, one ? "Use this crop" : "Use these crops")));
    document.body.append(d);
    d.showModal();
    all[0].el.focus();
  });
}
