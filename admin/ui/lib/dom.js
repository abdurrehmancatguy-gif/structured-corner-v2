// Every node the admin draws is built here, and text only ever goes in as
// text: nothing sets innerHTML, so a product name edited by hand in the JSON
// cannot run as code inside the admin. Styles are set through the CSSOM,
// which the admin's CSP allows, never as a style attribute string.

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "style") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (["value", "checked", "disabled", "hidden", "open", "selected", "indeterminate"].includes(k)) el[k] = v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }
  return append(el, kids);
}

export function append(el, kids) {
  for (const kid of [kids].flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export const copy = (o) => JSON.parse(JSON.stringify(o));
export const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function getPtr(obj, path) {
  let cur = obj;
  for (const part of path.split("/").filter(Boolean)) {
    if (cur === null || cur === undefined) return undefined;
    cur = cur[part];
  }
  return cur;
}

export function setPtr(obj, path, value) {
  const parts = path.split("/").filter(Boolean);
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (cur[parts[i]] === null || typeof cur[parts[i]] !== "object") cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

let uid = 0;
export const nextId = (p = "f") => p + (++uid);

export const thumb = (name) => "/assets/img/" + String(name).replace(/\.jpg$/, "-thumb.jpg");
