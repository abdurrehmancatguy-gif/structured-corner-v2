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
  the same arguments, so the existing preview configuration keeps working. No
  admin code lives in `flow/`: that directory is published.
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
  README.md            how to run it and what it can and cannot do
  docs/                PLAN.md, HARDCODED.md, CONTENT-MODEL.md
  bgsadmin/
    config.py          paths derived from --repo, port, hosts, limits, the published-file rule, the tool table
    httpd.py           threaded server and handler: security gate, dispatch, JSON I/O, errors
    security.py        Host, Origin, Fetch Metadata and token checks, safe_join, header sets, CSP
    static.py          storefront preview (published set, Range, 404.html) and the admin UI allow-list
    routes.py          discovers every module in bgsadmin/api/ and collects its ROUTES
    api/               one module per area (session, products, documents, media, history, publish, ...)
    schema/            one module per resource (products.py, settings.py, copy.py, home.py, navigation.py, ...)
    validate.py        types, bounds, text and href rules, cross-field and referential checks
    store/base.py      the ContentStore interface (docs/PLAN.md, storage_layer)
    store/jsonstore.py the JSON implementation: revs, transactions, snapshots, atomic writes, recovery
    tools.py           allow-listed subprocess runner with the expected-output check
    media.py, video.py upload pipelines per kind
    gitops.py          read-only queries, commit --only, fetch, push by sha, clean-room verify
    diff.py, lint.py, csvio.py, jobs.py, audit.py
  ui/
    index.html admin.css app.js icons.js lib/ components/ screens/
  tests/               stdlib unittest: /usr/bin/python3 -m unittest discover -s admin/tests
```

### Extension points (so several people can add areas without editing shared files)

- **API**: each `bgsadmin/api/<area>.py` defines `ROUTES`, a list of
  `Route(method, pattern, handler, flags)`. `routes.py` imports every module in
  the package with `pkgutil`; nobody edits a central route table. Patterns are
  compiled regexes with named groups; each group is validated before the
  handler runs (product ids, document names, snapshot ids as in the plan).
- **Schema**: each `bgsadmin/schema/<resource>.py` exports `RESOURCE` (name,
  kind, file) and `FIELDS`, a list of field dicts: `path` (JSON pointer, `*`
  for array items), `type` (text, textarea, lines, int, money, bool, enum,
  href, image, images, video, product-ref, product-refs, icon, tint, rows),
  `label`, `help`, `required`, `min`, `max`, `maxLength`, `pattern`, `enum`,
  `visibleWhen` (for example `{"category": ["attars"]}`), `rendered` (false
  shows "Not shown on the site yet"), `locked` (with a `lockedReason`) and
  `guarded`. `GET /admin/api/v1/schema` returns them all; the UI renders
  forms from it and never hardcodes field lists.
- **UI**: `ui/app.js` holds the whole left navigation from the plan's
  information architecture. Each entry maps to `ui/screens/<name>.js`, loaded
  with dynamic `import()`. An entry whose screen does not exist yet shows a
  plain "Not built yet" state; entries that need the database or login are
  shown disabled with "Arrives with the database" or "Arrives with login".
  Adding an area means adding a screen module and an API module.

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
- Commit and go live: as `docs/PLAN.md` publish_flow. Commit only the
  admin-owned paths with `git commit --only` after the clean-room rebuild
  check. Go live pushes the reviewed sha, fast-forward only, after the owner
  types PUBLISH. Never force, pull, merge, rebase, reset, stash or change
  config. Commit messages follow the repo's style: plain sentence-case
  imperative, no em dash, no trailer or attribution line of any kind.

## Look

Polaris structure, BGS materials, and the storefront's own rounded scale:
cards and panels 20px, small boxes inside them 14px, every button and control
a pill. Palette and type from `flow/assets/flow.css`'s tokens (ink `#171310`,
canvas `#faf7f2`, lines `#e6e0d6`, gold for focus rings and emphasis, never
for body text). Helvetica Neue stack. No emoji. Honest empty states; no
sample or invented numbers anywhere.

## Content wiring (phase 0)

The admin can only edit what the storefront reads. `docs/HARDCODED.md` lists
every value still typed into `build.py` and `shop.js`; phase 0 moves them into
content with today's values, adds schema entries for them, and makes
`build.py` and `shop.js` escape every content value. Acceptance: for every
generated page, the old and new output are identical after `html.unescape`
(entities such as `&middot;` may become the character they stand for), and
screenshots at 390 and 1440 wide are pixel-identical. Visible fixes found on
the way (the quiz's AED 89, the 'all' intro that still says Reserve,
placeholder slots shown to visitors) land as separate, named changes.

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
