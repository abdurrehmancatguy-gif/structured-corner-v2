/* The shop's cache.
 *
 * Every asset URL the pages ask for carries ?v=<hash of the file>, so a given
 * URL always answers with the same bytes: when a photo or a script changes, the
 * pages ask for a new URL. That makes those URLs safe to keep forever, which is
 * what Netlify was told to do (netlify.toml sends assets as immutable for a
 * year). GitHub Pages, which is where the site is served from, sends
 * Cache-Control: max-age=600 on everything and cannot be told otherwise, so
 * ten minutes after a visit the browser asks the server about every file again.
 *
 * This worker is the part of that we can run ourselves. It keeps the versioned
 * files in a cache of its own and answers from it without going to the network,
 * so a second visit paints from disk. Pages are taken from the network first
 * and only fall back to the cache, so a deploy is seen at once and the shop
 * still opens when the connection drops.
 *
 * Nothing here decides what is cached by hand: the ?v= in the URL does.
 */
var CACHE = "bgs-1";

self.addEventListener("install", function (e) {
  // No file list to warm: the first page fills the cache as it is read.
  self.skipWaiting();
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.map(function (n) {
      return n === CACHE ? null : caches.delete(n);   // an older worker's cache
    }));
  }).then(function () {
    return self.clients.claim();
  }));
});

/* A versioned file: assets/..., asked for with the ?v= the page carries. */
function versioned(url) {
  return url.pathname.indexOf("/assets/") !== -1 && url.searchParams.has("v");
}

/* Keep one copy per file. The cache is asked for the same path ignoring the
   query, which returns the entries for the older ?v= of this file, and those
   go. Without it every deploy would leave its photographs behind. */
function store(req, res) {
  return caches.open(CACHE).then(function (cache) {
    return cache.keys(req, { ignoreSearch: true }).then(function (old) {
      return Promise.all(old.map(function (k) {
        return k.url === req.url ? null : cache.delete(k);
      }));
    }).then(function () {
      return cache.put(req, res);
    });
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== location.origin) return;         // fonts and anything else off-site
  if (url.pathname.indexOf("/admin") !== -1) return;  // the admin is not the shop
  // Film is left to the browser. A player asks for a piece of the file at a
  // time (a Range request), and a cache can only answer with the whole of it,
  // which some browsers refuse to play.
  if (req.headers.has("range") || req.destination === "video" || req.destination === "audio") return;

  if (versioned(url)) {
    e.respondWith(caches.match(req).then(function (hit) {
      return hit || fetch(req).then(function (res) {
        if (res.ok && res.type === "basic") store(req, res.clone());
        return res;
      });
    }));
    return;
  }

  if (req.mode === "navigate") {
    // The page itself: the network decides, the cache catches a failure. The
    // copy is kept under the path alone, so product.html?id=vibe and the next
    // product are the one page they are, and it is read back the same way.
    var page = new Request(url.origin + url.pathname);
    e.respondWith(fetch(req).then(function (res) {
      if (res.ok && res.type === "basic") {
        var copy = res.clone();
        caches.open(CACHE).then(function (cache) { cache.put(page, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(page).then(function (hit) {
        return hit || Response.error();
      });
    }));
  }
});
