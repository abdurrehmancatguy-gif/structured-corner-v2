// Line icons for the admin, drawn at a 1.6 stroke so they sit with the
// storefront's own. Built with the DOM, not markup strings.
const NS = "http://www.w3.org/2000/svg";

const P = {
  home: ["M3 10.5 12 3l9 7.5", "M5 9.5V20h5v-6h4v6h5V9.5"],
  orders: ["M6 7h12l-1 13H7z", "M9 7a3 3 0 0 1 6 0"],
  tag: ["M3 12V4h8l10 10-8 8z", "M8 8h.01"],
  grid: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
  users: ["M16 20v-1a4 4 0 0 0-8 0v1", "M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7"],
  layout: ["M4 4h16v16H4z", "M4 9h16", "M10 9v11"],
  menu: ["M4 7h16", "M4 12h16", "M4 17h16"],
  text: ["M5 6h14", "M12 6v13", "M9 19h6"],
  image: ["M4 5h16v14H4z", "M4 16l5-5 4 4 3-3 4 4", "M15.5 9h.01"],
  help: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6", "M12 17h.01"],
  globe: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M3 12h18", "M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3"],
  percent: ["M5 19 19 5", "M7 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4", "M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4"],
  chart: ["M4 20h16", "M7 16v-5", "M12 16V7", "M17 16v-8"],
  upload: ["M12 16V4", "M7 9l5-5 5 5", "M5 20h14"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18", "M12 7v5l3 2"],
  gear: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6", "M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14.2 3h-4.4l-.4 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2l.4 2.6h4.4l.4-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2"],
  lock: ["M6 11h12v9H6z", "M8.5 11V8a3.5 3.5 0 0 1 7 0v3"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v6H4V6h6"],
  plus: ["M12 5v14", "M5 12h14"],
  trash: ["M5 7h14", "M9 7V4h6v3", "M7 7l1 13h8l1-13"],
  copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  up: ["M12 19V5", "M6 11l6-6 6 6"],
  down: ["M12 5v14", "M6 13l6 6 6-6"],
  left: ["M15 18l-6-6 6-6"],
  right: ["M9 18l6-6-6-6"],
  alert: ["M12 3 2 20h20z", "M12 10v4", "M12 17h.01"],
  check: ["M5 12.5l4.5 4.5L19 7"],
  close: ["M6 6l12 12", "M18 6 6 18"],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14", "M16 16l4 4"],
  film: ["M4 5h16v14H4z", "M8 5v14", "M16 5v14", "M4 9h4", "M4 15h4", "M16 9h4", "M16 15h4"],
  eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6"],
};

export function icon(name, size = 18) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.6");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const d of P[name] || []) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}
