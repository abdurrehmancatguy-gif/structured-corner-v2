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
    throw new ApiError(0, { error: { code: "offline", message: "The admin server is not answering. Is it still running?" } });
  }
  const text = await res.text();
  let data = null;
  if (text) { try { data = JSON.parse(text); } catch (err) { data = null; } }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}
