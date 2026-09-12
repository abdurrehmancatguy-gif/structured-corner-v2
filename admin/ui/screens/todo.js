// Sections of the admin that are planned but not built yet say so plainly.
import { h, clear } from "../lib/dom.js";
import { guard } from "../lib/ui.js";

const NEXT = {
  inventory: "Stock for every tracked product on one screen, edited inline.",
  bulk: "A spreadsheet-style grid to change many products at once.",
  import: "Download every product as a spreadsheet, and bring changes back in with a preview before anything is saved.",
  collections: "Each category's intro, circle picture and the order of its products.",
  pages: "The text on every page: product tabs, gift box, bag, track order, corporate, account and the 404 page.",
  quiz: "The scent quiz's questions, answers and results.",
  translations: "The Arabic version of every label on the site.",
  files: "Every image and film the site publishes: upload, replace, and remove what nothing uses any more.",
  discounts: "The volume discounts, the gift box fee and the free gift threshold.",
  publish: "Review exactly what changed, save it as a version, and send it to the live site with one confirmation.",
  history: "Every saved version of every product and page, with a one-click restore.",
};

export function render(main, { arg, label }) {
  guard.clear();
  clear(main).append(
    h("div", { class: "page-head" }, h("div", {}, h("h1", { tabindex: "-1" }, label || "Not built yet"))),
    h("section", { class: "card empty-state" },
      h("p", { class: "lead" }, "Not built yet."),
      NEXT[arg] ? h("p", {}, NEXT[arg]) : null,
      h("p", { class: "muted" }, "Everything in this section of the admin is coming in the next stages.")));
}
