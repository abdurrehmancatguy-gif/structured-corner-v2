// The admin shell: top bar, left navigation, hash router and the status poll.
import { initToken, api } from "./lib/api.js";
import { h, clear } from "./lib/dom.js";
import { icon } from "./icons.js";
import { mountChrome, guard, savebar, confirmDialog, banner } from "./lib/ui.js";

// The whole navigation from the plan, in Shopify's order. Each entry names
// its screen module (ui/screens/<screen>.js); one not written yet shows the
// plain "Not built yet" page. The entries that need the database or login
// are shown but switched off, with the reason.
const NAV = [
  { hash: "#/", label: "Home", icon: "home", screen: "home" },
  { label: "Orders", icon: "orders", off: "Arrives with the database" },
  { hash: "#/products", label: "Products", icon: "tag", screen: "products", kids: [
    { hash: "#/inventory", label: "Inventory", screen: "inventory" },
    { hash: "#/bulk", label: "Bulk editor", screen: "bulk" },
    { hash: "#/import", label: "Import and export", screen: "import" },
  ] },
  { hash: "#/collections", label: "Collections", icon: "grid", screen: "collections" },
  { label: "Customers", icon: "users", off: "Arrives with the database" },
  { group: "Content" },
  { hash: "#/content/home", label: "Homepage", icon: "layout", screen: "document", arg: "home" },
  { hash: "#/content/navigation", label: "Navigation", icon: "menu", screen: "document", arg: "navigation" },
  { hash: "#/content/copy", label: "Site text", icon: "text", screen: "document", arg: "copy" },
  { hash: "#/content/pages", label: "Pages", icon: "text", screen: "pages" },
  { hash: "#/content/quiz", label: "Scent quiz", icon: "help", screen: "quiz" },
  { hash: "#/content/translations", label: "Translations", icon: "globe", screen: "translations" },
  { hash: "#/content/files", label: "Files", icon: "image", screen: "files" },
  { hash: "#/discounts", label: "Discounts", icon: "percent", screen: "discounts" },
  { label: "Analytics", icon: "chart", off: "Arrives with the database" },
  { group: "Online store" },
  { hash: "#/publish", label: "Publish", icon: "upload", screen: "publish" },
  { hash: "#/history", label: "History", icon: "clock", screen: "history" },
  { hash: "#/settings", label: "Settings", icon: "gear", screen: "document", arg: "settings" },
];

// Screens can listen to the status poll (hooks.status) and add small things
// to the top bar (topSlot), so a new area never has to edit this file.
const app = { state: { schema: null, session: null, products: null }, hooks: { status: [] }, topSlot: null, poll: () => poll() };
let main, side, chip, current = "#/";

// "#/products/be-mine" opens one product. Any other deeper address belongs to
// the section it starts with, and the rest reaches that screen as `sub`:
// "#/history/products/be-mine" gives History the sub "products/be-mine".
function route(hash) {
  const m = hash.match(/^#\/products\/([a-z0-9-]+)$/);
  if (m) return { screen: "product", arg: m[1], nav: "#/products" };
  const flat = NAV.flatMap((n) => [n].concat(n.kids || [])).filter((n) => n.hash);
  let hit = flat.find((n) => n.hash === hash);
  let sub = "";
  if (!hit) {
    hit = flat.filter((n) => n.hash !== "#/" && hash.startsWith(n.hash + "/"))
      .sort((a, b) => b.hash.length - a.hash.length)[0];
    if (hit) {
      try { sub = decodeURIComponent(hash.slice(hit.hash.length + 1)); } catch (e) { sub = ""; }
    }
  }
  hit = hit || flat[0];
  return { screen: hit.screen, arg: hit.arg, sub, nav: hit.hash, label: hit.label };
}

function drawNav(active) {
  clear(side).append(h("nav", { "aria-label": "Admin sections" }, h("ul", {}, NAV.map((n) => {
    if (n.group) return h("li", { class: "nav-group" }, n.group);
    if (n.off) return h("li", {}, h("span", { class: "nav-item off", title: n.off }, icon(n.icon), h("span", {}, n.label), h("small", {}, n.off)));
    const on = n.hash === active || (n.kids || []).some((k) => k.hash === active);
    return h("li", {},
      h("a", { class: "nav-item" + (n.hash === active ? " on" : ""), href: n.hash, "aria-current": n.hash === active ? "page" : null }, icon(n.icon), h("span", {}, n.label)),
      n.kids && on ? h("ul", { class: "nav-kids" }, n.kids.map((k) => h("li", {},
        h("a", { class: "nav-item kid" + (k.hash === active ? " on" : ""), href: k.hash, "aria-current": k.hash === active ? "page" : null }, k.label)))) : null);
  }))));
}

// A screen module that is not there yet fails to load as a failed fetch (a
// TypeError naming the module); one that exists but breaks shows its error.
async function loadScreen(r) {
  try {
    return await import("./screens/" + r.screen + ".js");
  } catch (e) {
    if (!(e instanceof TypeError) || !/fetch|import|module/i.test(e.message || "")) throw e;
    r.arg = r.screen;
    return import("./screens/todo.js");
  }
}

async function show(hash) {
  const r = route(hash);
  current = hash;
  document.body.classList.remove("nav-open");
  savebar.hide();
  guard.clear();
  drawNav(r.nav);
  clear(main).append(h("p", { class: "loading" }, "Loading"));
  try {
    const mod = await loadScreen(r);
    await mod.render(main, { arg: r.arg, sub: r.sub, label: r.label, app });
  } catch (e) {
    clear(main).append(banner({ tone: "critical", title: e.message || "This screen did not load." }));
  }
  document.title = (main.querySelector("h1") ? main.querySelector("h1").textContent + " | " : "") + "BGS Corner admin";
  const h1 = main.querySelector("h1");
  if (h1) h1.focus();
}

async function onHash() {
  const next = location.hash || "#/";
  if (next === current) return;
  if (guard.dirty()) {
    history.replaceState(null, "", current);
    const leave = await confirmDialog({ title: "Leave without saving?", body: ["Your changes on this screen have not been saved."], confirm: "Leave", danger: true, cancel: "Stay" });
    if (!leave) return;
    guard.clear();
    history.replaceState(null, "", next);
  }
  show(next);
}

async function poll() {
  if (document.hidden) return;
  try {
    const st = await api("GET", "status");
    const b = st.build || {};
    chip.textContent = b.ok === null || b.ok === undefined ? "Preview ready" : b.ok ? "Built in " + ((b.ms || 0) / 1000).toFixed(1) + " s" : "Last build failed";
    chip.className = "chip" + (b.ok === false ? " bad" : "");
    chip.title = st.external && st.external.length ? "Changed outside the admin: " + st.external.join(", ") : "";
    if (st.external && st.external.length) chip.textContent += " · changed outside";
    for (const fn of app.hooks.status) {
      try { fn(st); } catch (e) { /* a listener never stops the poll */ }
    }
  } catch (e) {
    chip.textContent = e.code === "bad_token" ? "Admin restarted: reload" : "Server not answering";
    chip.className = "chip bad";
  }
}

async function boot() {
  initToken();
  const root = document.getElementById("app");
  clear(root);
  chip = h("span", { class: "chip" }, "Preview ready");
  main = h("main", { id: "main", tabindex: "-1" });
  side = h("aside", { class: "side" });
  app.topSlot = h("span", { class: "top-slot" });
  root.append(
    h("header", { class: "top" },
      h("button", { class: "icon-btn menu-btn", type: "button", "aria-label": "Menu", onclick: () => document.body.classList.toggle("nav-open") }, icon("menu", 20)),
      h("a", { class: "brand", href: "#/" }, h("img", { src: "/assets/img/logo-gold-light-486.png", alt: "BGS Corner", width: "150", height: "22" })),
      h("span", { class: "badge local", title: "This admin runs on this computer only. Nothing goes live until you publish." }, "Local admin"),
      h("span", { class: "spacer" }),
      app.topSlot,
      chip,
      h("a", { class: "btn ghost-light", href: "/", target: "_blank", rel: "noopener noreferrer" }, icon("external", 16), h("span", { class: "hide-sm" }, "View store"))),
    h("div", { class: "layout" }, side, main));
  mountChrome(root);
  root.append(h("datalist", { id: "bgs-links" }));
  try {
    [app.state.session, app.state.schema] = await Promise.all([api("GET", "session"), api("GET", "schema")]);
  } catch (e) {
    clear(main).append(banner({ tone: "critical", title: e.message }));
    return;
  }
  const links = document.getElementById("bgs-links");
  const opts = ["index.html", "collection.html", "collection.html?cat=attars", "collection.html?cat=bakhoor", "collection.html?cat=edp",
    "collection.html?cat=gift-sets", "gift-box.html", "corporate.html", "quiz.html", "track-order.html", "account.html", "cart.html"];
  opts.forEach((o) => links.append(h("option", { value: o })));
  api("GET", "products").then((list) => {
    app.state.products = Object.fromEntries(list.items.map((it) => [it.id, it.data]));
    list.items.forEach((it) => links.append(h("option", { value: "product.html?p=" + it.id }, it.data.name)));
  }).catch(() => {});
  window.addEventListener("hashchange", onHash);
  window.addEventListener("beforeunload", (e) => { if (guard.dirty()) { e.preventDefault(); e.returnValue = ""; } });
  current = null;
  show(location.hash || "#/");
  poll();
  setInterval(poll, 5000);
  // A screen that adds to the top bar exports topbar(app), called once here
  // so its chip shows on every screen.
  for (const name of ["publish"]) import("./screens/" + name + ".js").then((m) => m.topbar && m.topbar(app)).catch(() => {});
}

boot();
