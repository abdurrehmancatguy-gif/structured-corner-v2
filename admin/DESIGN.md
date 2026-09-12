# BGS Corner admin: design decisions

The admin is a local, Shopify-style back office for the storefront in `flow/`.
Everything a visitor sees is editable in it except payments, checkout and the
core pricing logic, which stay locked in code. There is no login and no
database yet: the content JSON files in `flow/content/` are the store, behind a
storage layer PostgreSQL will implement later, and the admin only ever listens
on the owner's own machine.

The full architecture is in `docs/PLAN.md`; the inventories it rests on are
`docs/HARDCODED.md` (every visitor-visible value in build.py and shop.js) and
`docs/CONTENT-MODEL.md` (every content field, its readers and the media
pipeline). This file records the decisions that refine or override the plan,
and the conventions every contributor follows.

## Where it runs

- `admin/server.py` is the one local server. It serves the storefront preview
  from `flow/` at `http://localhost:4310/` (the deploy's published file set
  only), the admin at `http://localhost:4310/admin/` and the API at
  `/admin/api/v1/`. It binds `127.0.0.1` and nothing else.
- `flow/server.py` stays as a two-line shim that starts `admin/server.py` with
  the same arguments, so `python3 flow/server.py 4310` keeps working. No
  admin code lives in `flow/`: that directory is published. The `bgs-flow`
  entry in `.claude/launch.json` still runs `python3 -m http.server` on
  `flow/`, which serves the store without the admin.
- Flags: `--port N` (default 4310); `--repo PATH` (serve and edit another
  checkout, used by every test); `--storefront-only` (no admin routes, no
  token); `--no-push` (the push endpoint answers 403; all automated testing
  runs with it).
- Runtime: `/usr/bin/python3` (3.9.6) standard library plus Pillow 11.3
  (ImageCms included). ffmpeg and ffprobe from `/opt/homebrew/bin`, probed at
  startup; a missing tool disables the matching uploads with a message.
  No third-party Python packages, no npm, no build step for the UI.

## Layout

```
admin/
  server.py            entry point: flags, startup checks, recovery, token, serve
  DESIGN.md            this file
  README.md            how to run it, every screen, every test file
  docs/                PLAN.md, HARDCODED.md, CONTENT-MODEL.md
  bgsadmin/
    app.py             the running admin: configuration, token, routes, store and build state
    config.py          paths derived from --repo, port, hosts, limits, the published-file rule
    httpd.py           threaded server and handler: security gate, dispatch, JSON and raw bodies, errors
    security.py        Host, Origin, Fetch Metadata and token checks, safe_join, header sets, CSP
    static.py          storefront preview (published set, Range, 404.html) and the admin UI allow-list
    routes.py          Route and Raw; collects ROUTES from every module in bgsadmin/api/
    errors.py          ApiError, the one error type the API raises
    jsonutil.py        strict JSON in, canonical JSON out
    jobs.py            background jobs on their own threads, polled with GET jobs/<id>
    api/               one module per area: meta (session, schema, status, rebuild), products,
                       documents, collections, bulk, media, history, publish, jobs
    schema/            one module per resource: products, settings, copy, home, navigation,
                       pages, quiz, translations
    service.py         helpers the API modules share: which pointers a change touches,
                       the locked and read-only checks, the save response
    validate.py        types, bounds, text and href rules, cross-field and referential checks
    lint.py            warnings that never block a save
    store/base.py      the ContentStore interface (docs/PLAN.md, storage_layer)
    store/jsonstore.py the JSON implementation: revs, transactions, snapshots, atomic writes, recovery
    tools.py           allow-listed subprocess runner with the expected-output check
    media.py, video.py upload checks and pipelines per kind
    medialib.py        the media library: published files, where each is used, copies, trash
    diff.py            what changed between two versions, as short sentences
    gitops.py          read-only queries, commit --only, fetch, push by sha, clean-room verify
    publishing.py      what a commit and a publish carry, and the checks in front of them
    csvio.py           the product CSV export and the import's dry-run plan
  ui/
    index.html admin.css app.js icons.js
    lib/               api.js, dom.js, ui.js, forms.js, editor.js, bulk.js, media.js
    components/        crop.js, media-grid.js, upload-field.js
    screens/           one module per screen
    css/               one stylesheet per screen that needs its own
  tests/               stdlib unittest, one port per file (README.md lists them), box.py, cdp_pipe.py
  devtools/            compare_build.py, dom_diff.py
```

### Extension points (so several people can add areas without editing shared files)

- **API**: each `bgsadmin/api/<area>.py` defines `ROUTES`, a list of
  `Route(method, pattern, handler, body, limit, types)`. `routes.py` imports
  every module in the package with `pkgutil`, in name order; nobody edits a
  central route table. Patterns are compiled regexes with named groups; each
  group is validated before the handler runs (product ids, document names,
  snapshot ids as in the plan). `body` is None, `"json"` (parsed before the
  handler runs, capped at `limit` or the 2 MB default) or `"raw"`.
- **Raw uploads**: `Route(..., body="raw", limit=..., types=...)` takes a
  file sent as the request body itself. The route refuses to load without
  both a size limit and the accepted content types. The server checks the
  type and length first and does not read the body; the handler takes it
  once, with `req.save_body(path)` to stream it to a file or
  `req.read_body()` for a small one. `POST media/staging` is the one raw
  route today.
- **Other responses**: a handler returns a dict for JSON, or `routes.Raw(data,
  ctype, headers, status)` for anything else. A Raw response goes out with
  the admin's usual security headers plus its own. The product CSV export
  uses it.
- **Background jobs**: `jobs.start(kind, fn)` runs `fn(log)` on its own thread
  and returns a Job at once; the handler answers 202 with the job id and the
  UI polls `GET jobs/<id>` for `state` (queued, running, done or failed),
  `log_tail`, `result` and `error`. An ApiError raised inside keeps its code
  and message. The last 50 finished jobs are kept, and nothing survives a
  restart. Film conversion and the push use it.
- **Schema**: each `bgsadmin/schema/<resource>.py` exports `RESOURCE` (name,
  label, kind, intro) and `FIELDS`, a list of field dicts: `path` (JSON
  pointer, `*` for array items), `type` (text, textarea, lines, int, money,
  bool, enum, href, image, images, video, product-ref, product-refs, icon,
  tint, rows, dictionary, tags), `label`, `help`, `required`, `min`, `max`,
  `maxLength`, `pattern`, `enum`, `visibleWhen` (for example
  `{"category": ["attars"]}`), `rendered` (false shows "Not shown on the site
  yet"), `locked` (with a `lockedReason`), `readonly` (the reason, for things
  changed elsewhere) and `guarded`. `group` names the card a field sits in and
  `section` a heading inside a long group; `upload` names the upload that
  fills an image or video field, and `default` is the value the site reads
  when a key is missing. The docstring in `schema/__init__.py` lists every
  key. `GET /admin/api/v1/schema` returns them all; the UI renders forms
  from it and never hardcodes field lists.
- **Documents**: a schema module whose kind is `"document"` is a whole file,
  `flow/content/<name>.json`. `schema.document_names()` lists them, and the
  store, the routes (`GET` and `PUT documents/<name>`), the status poll,
  History and the media and product reference checks all read that list.
  Adding a document means adding its module and its file; nothing else is
  edited. pages, quiz and translations were added this way.
- **UI**: `ui/app.js` holds the whole left navigation from the plan's
  information architecture. Each entry maps to `ui/screens/<name>.js`, loaded
  with dynamic `import()`. Every entry now has its screen. Entries that need
  the database or login are shown switched off with the reason; today those
  are Orders, Customers and Analytics, which read "Arrives with the
  database". `screens/todo.js` stays as the "Not built yet" page for an entry
  whose module is missing. Adding an area means adding a screen module and an
  API module.
- **Sub-routes**: `#/products/<id>` opens one product. Any other address
  deeper than a navigation entry belongs to that entry, and the rest reaches
  its screen as `sub`: `#/history/products/be-mine` gives History the sub
  `products/be-mine`. Screens that use it: Collections (`<key>`), Pages
  (`<group>`), Files (`images`, `categories`, `films`, `trash`), History
  (`products/<id>` or `documents/<name>`, then an optional version id) and
  Publish (`live`, `log`).
- **A screen's own stylesheet**: `useCss(name)` from `lib/dom.js` adds
  `admin/ui/css/<name>.css` to the page once. Screens built side by side
  never edit `admin.css`. The CSP allows no inline style, so styles live in
  these files.
- **The top bar**: a screen module can export `topbar(app)`; `app.js` calls it
  once at boot for each name in its list (today only `publish`), so a chip
  shows on every screen. It can listen to the status poll through
  `app.hooks.status` and draw into `app.topSlot`.
- **Editors**: `lib/editor.js` `mountEditor` gives any screen the save bar,
  the unsaved-changes guard, Cmd or Ctrl+S, and the handling of 412, 422 and
  a failed build. The document, product, Collections, Discounts, Pages,
  Scent quiz and Translations screens are built on it.
- **Field types without a generic control**: `forms.js` has no control for
  `dictionary` or `tags`, so a document that uses them needs its own screen,
  as Translations and the Scent quiz have.

## Locked, always, enforced on the server

- `settings.payments`, VAT (`settings.store.vat_rate_percent`,
  `vat_inclusive`), the COD cap and fee, and the checkout and order-confirmed
  page copy. A request that changes a locked JSON pointer gets 403
  `locked_field`, even inside a whole-document PUT.
- The pricing engine (`recalc` in shop.js), the never-discount enforcement,
  the quantity clamp: code, not content.
- No endpoint reads or writes `.py`, `.js`, `.css`, `.html`, `.toml` or
  `.yml`; uploads can only produce server-named `.jpg`, `.png` and `.mp4`.
- No personal data in content files: the repository is public.

## Security

As `docs/PLAN.md` security_model, items 1 to 15, all of them. In short: bind
127.0.0.1; Host allow-list (421); Origin and Fetch Metadata on the API (403);
a per-run token in a meta tag, required as `X-Admin-Token` on every API call
(401); the admin HTML only for top-level navigations, with COOP same-origin,
`frame-ancestors 'none'` and a strict CSP with no inline script or style;
storefront preview responses carry `connect-src 'none'`; JSON-only bodies
(415), raw typed uploads, size caps, no chunked bodies; `safe_join` on every
path; Pillow bomb limits and re-encoding; ffmpeg with a forced demuxer and the
file protocol only; content validation against stored XSS (no `<` or `>` in
text, internal-only hrefs); a fixed subprocess table with output checks.

## Saving and publishing

- Save: validate, check the rev, open a transaction, write atomically, run
  `tools/make_derivatives.py` if media changed, run `build.py`, then commit or
  roll back every touched file (content and generated) byte for byte. Git is
  never touched by a save.
- Commit and go live: as `docs/PLAN.md` publish_flow, with the differences
  its status section lists. Commit only the admin-owned paths with
  `git commit --only` after the clean-room rebuild check. Go live pushes the
  reviewed sha, fast-forward only, after the owner types PUBLISH. Never
  force, pull, merge, rebase, reset, stash or change config. Commit messages
  follow the repo's style: plain sentence-case imperative, no em dash, no
  trailer or attribution line of any kind.

## Look

Polaris structure, BGS materials, and the storefront's own rounded scale:
cards and panels 20px, small boxes inside them 14px, every button and control
a pill. Palette and type from `flow/assets/flow.css`'s tokens (ink `#171310`,
canvas `#faf7f2`, lines `#e6e0d6`, gold for focus rings and emphasis, never
for body text). Helvetica Neue stack. No emoji. Honest empty states; no
sample or invented numbers anywhere.

## Content wiring (phase 0)

The admin can only edit what the storefront reads. `docs/HARDCODED.md` lists
every value that was typed into `build.py` and `shop.js`; phase 0 moves them
into content with today's values, adds schema entries for them, and makes
`build.py` and `shop.js` escape every content value.

Done so far: the store rules, the category text and collection intros, the
homepage shelves, the text of the fixed pages except checkout and order
confirmed, the Arabic dictionary and the scent quiz. `docs/HARDCODED.md` marks
each of those rows `now-content` or `partly-content` and says where it lives.
`build.py` passes what `shop.js` needs as window globals in `catalogue.js`
(`docs/CONTENT-MODEL.md` lists them), and `shop.js` keeps today's text as the
fallback for each one.

Acceptance for each move: `admin/devtools/compare_build.py` finds every
generated file identical after dropping `?v=` tokens and decoding entities,
apart from the new globals in `catalogue.js`, and `admin/devtools/dom_diff.py`
finds the same text, links and media on every page after the scripts run.
Visible fixes found on the way landed as separate, named changes: the
all-products intro that still said Reserve, and the quiz's product names,
AED 89 price, meta line, See it link and a stale note sentence.

## Rules for everyone working on this

- Never push. Never run the push endpoint against the real repository; tests
  use temporary clones with a local bare remote, and every automated run uses
  `--no-push`.
- Mutating tests run against a temporary clone (`--repo`), never against the
  real `flow/content`. Use ports 4700 to 4799 for test servers; 4310 is the
  owner's preview.
- No em dash characters anywhere, code comments included. No attribution or
  "generated with" text. No invented numbers or claims in copy or UI.
- Images come from content data, never hardcoded in templates or scripts.
- Comments explain why, in plain sentences, like the rest of the repo.
