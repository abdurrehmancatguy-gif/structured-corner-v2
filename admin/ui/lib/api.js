// The one way the admin talks to its server. The per-run token comes from
// the page's meta tag and lives only in this module: never in storage,
// cookies or URLs, which the storefront (same origin) could read. A change
// is never retried automatically.

let TOKEN = "";

export function initToken() {
  const m = document.querySelector('meta[name="admin-token"]');
  TOKEN = m ? m.content : "";
  if (m) m.remove();
}

export class ApiError extends Error {
  constructor(status, body) {
    const e = (body && body.error) || {};
    super(e.message || "The admin server answered " + status + ".");
    this.status = status;
    this.code = e.code || "http_" + status;
    this.details = e.details;
  }
}

const OFFLINE = { error: { code: "offline", message: "The admin server is not answering. Is it still running?" } };

export async function api(method, path, { body, rev } = {}) {
  const headers = { "X-Admin-Token": TOKEN };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (rev) headers["If-Match"] = '"' + rev + '"';
  let res;
  try {
    res = await fetch("/admin/api/v1/" + path, {
      method, headers, cache: "no-store", credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(0, OFFLINE);
  }
  const text = await res.text();
  let data = null;
  if (text) { try { data = JSON.parse(text); } catch (err) { data = null; } }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// An upload sends the file itself as the body, typed (the server refuses
// multipart and text bodies), through XHR for the progress events fetch
// does not give. onProgress gets a fraction from 0 to 1.
export function upload(path, file, { type, rev, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/admin/api/v1/" + path);
    x.setRequestHeader("X-Admin-Token", TOKEN);
    x.setRequestHeader("Content-Type", type || file.type || "application/octet-stream");
    if (rev) x.setRequestHeader("If-Match", '"' + rev + '"');
    if (onProgress) x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    x.onload = () => {
      let data = null;
      try { data = x.responseText ? JSON.parse(x.responseText) : null; } catch (err) { data = null; }
      if (x.status >= 200 && x.status < 300) resolve(data);
      else reject(new ApiError(x.status, data));
    };
    x.onerror = () => reject(new ApiError(0, OFFLINE));
    x.send(file);
  });
}

// A file the server makes, such as the product spreadsheet: fetched with the
// token, then handed to the browser to save under the name the server gives.
export async function download(path, fallbackName = "download") {
  let res;
  try {
    res = await fetch("/admin/api/v1/" + path, { headers: { "X-Admin-Token": TOKEN }, cache: "no-store", credentials: "same-origin" });
  } catch (err) {
    throw new ApiError(0, OFFLINE);
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch (err) { data = null; }
    throw new ApiError(res.status, data);
  }
  const blob = await res.blob();
  const m = (res.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (m && m[1]) || fallbackName;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
