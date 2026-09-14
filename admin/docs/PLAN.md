# Admin plan (2026-09-11)

The architecture the admin is built to. Written from a read of the repo on
2026-09-11; numbers and file states in it describe that day. `../DESIGN.md`
records the decisions that refine or override it.

## Status (2026-09-12)

Done:
- The first stage: the server, the JSON store, the security gate, and the
  Home, Products, product, Homepage, Navigation, Site text and Settings
  screens.
- Phase 0 wiring, with today's values: the store rules (settings.store,
  passed to shop.js as window.BGS_RULES), the category text and collection
  intros (copy.json, BGS_CATS), the homepage shelves (home.json), the text of
  the fixed pages (pages.json, BGS_COPY), the Arabic dictionary
  (translations.json, BGS_AR) and the scent quiz (quiz.json, BGS_QUIZ).
  Checkout and order confirmed stay in code. `HARDCODED.md` marks each row
  that moved.
- The screens stage: Inventory, Bulk editor, Import and export, Collections,
  Pages, Scent quiz, Translations, Files, Discounts, Publish and History, with
  uploads, the crop tool, film conversion as a background job, the media
  library and the trash. Orders, Customers and Analytics are shown switched
  off until the database.

Where the build differs from this plan:
- products/bulk takes changes as {id, rev, data}, not {id, rev, ops}.
- POST history/{id}/restore takes the rev in If-Match, like every other save,
  not expect_rev in the body.
- Backup pruning is on the History screen, not in Settings > Admin.
- GET publish/summary was added. It feeds the top-bar chip and never contacts
  GitHub.
- The second fetch before a push runs inside the background job, so a change
  after the review ends the job with the code review_stale, not an HTTP 412.
- pages.json holds the text of the fixed pages. Custom pages (Our story, FAQ)
  are not built and would need a key or a document of their own.
- The Arabic dictionary reaches shop.js as window.BGS_AR, not inside
  BGS_COPY, and the cutoff as BGS_RULES.sameday_cutoff_minutes, not
  sameday_cutoff_24h.
- Each rung of the volume ladder must save more than the rung before it, as
  well as need more items.
- The module names in server_design 1 and ui_design are the plan's.
  `../DESIGN.md` lists the modules that exist.

Not built from this plan: PATCH routes for products and documents, GET checks,
POST tools/derivatives, global search and the keyboard shortcuts, the SEO and
preferences screen, custom pages, the Settings > Admin panel, the sandboxed
device preview, draft autosave, the BroadcastChannel notices, before
thumbnails for changed media on the Publish screen, the "Check the live site"
button, and the check that the last build is not stale. A failed last build
does block a commit, and the clean-room rebuild catches stale generated files
at commit time.

Next: the owner's own PostgreSQL database for the admin (storage_layer
below), then Auth0 sign-in, then commerce.

## information_architecture

CURRENT STATE THAT SHAPES THE IA (read from the repo on 2026-09-11)
- 34 products (33 published) in 4 categories wired in code (attars, edp, bakhoor, gift-sets), plus settings, copy, home and navigation JSON. A lot of what visitors read is not in those files yet. build.py's shell() hardcodes the strip, search placeholder, footer and legal line. The home section headings, the Discovery band, promos, family tiles, PDP tabs, gift box, bag labels and the track, corporate, account and quiz copy are all template literals. shop.js hardcodes CAT_LABEL, CAT_INTRO (its 'all' intro still says 'oud oils, Reserve'), the Arabic dictionary, the quiz profiles and every store-rule number (150, 12, 300, 3/10%, 6/15%, box 25 and 10%, cutoff 14:00).
- Stored but inert today: navigation.main (NAV is built and emitted by nothing), navigation.footer, home.sections, copy.strip, copy.search_placeholder, copy.collection_intros, settings.store (only name is read), seo.default_title_suffix, social, analytics, payments, languages. Per product the inert fields are badge, seo_title, seo_description, image_alt, related, name_ar, story_ar and family to sillage.
- The IA follows one rule: a control exists only if it changes what a visitor sees. build.py applies the same rule to FACETS_LIVE. Stored-but-unrendered fields carry a 'Not shown on the site yet' badge, and screens that need Phase 0 wiring (see server_design) turn on when their wiring lands.

GLOBAL CHROME
- Top bar on the ink ground (#171310) with the light gold logo:
  - a permanent 'Local admin, not the live site' badge;
  - global search ('/' focuses; covers products, pages, files, settings);
  - build chip: 'Built 0.6 s ago', 'Build failed, change restored' or 'Content changed outside the admin: Rebuild';
  - changes chip: 'N saved, not committed' and 'M commits not live';
  - View store (new tab, rel=noopener noreferrer);
  - Publish (opens the Publish screen and never publishes directly).
- Contextual save bar (the Polaris pattern): while a form is dirty it replaces the top bar with 'Unsaved changes', Discard and Save (Cmd/Ctrl+S).
- Left nav in Shopify order: Home, Orders*, Products (All products, Inventory, Bulk editor, Import and export), Collections, Customers*, Content (Homepage, Pages, Navigation, Quiz, Translations, Files), Discounts, Analytics*, Online Store (SEO and preferences, Publish, History), Settings. Items marked * are visible but disabled, with one honest line: 'Arrives with the database' or 'Arrives with login'.

SCREENS AND KEY INTERACTIONS
1. Home. Every card is built from content and git; no invented metrics.
   - Work in progress: saved but not committed, committed but not live, last publish sha and time.
   - Build health.
   - Content gaps, each linking to a filtered list:
     - 25 of 34 products have no story;
     - 4 published gift sets have no photo (majlis-ritual-set, oud-lover-s-flight, eid-royal-hamper, dubai-in-a-bottle);
     - 0 products have SEO text, alt text or related products;
     - 4 tracked products are at 5 or fewer (suit-up 4, the-writer 1, soleil-frais 3, barcelona 5).
   - Lint warnings: copy that repeats a price or rule that no longer matches, claim words, em dashes.
   - 'Files still published but used by nothing'.
2. Products > All products. See features; also a 'Missing' filter set and saved views in localStorage (views only, never content or the token).
3. Product detail, in two columns (2/3 + 1/3).
   - Main column:
     - Title.
     - Story lines (0 to 6, counted).
     - Media grid: upload by picker or drop; drag reorder, where tile 1 reads 'Card image' and tile 2 'Hover image (box shot)'; per-tile menu with Move left/right, Make card image, Remove from product, Remove and trash file.
     - Pricing and variants by category:
       - edp: size, gender (Him/Her/Unisex, the facet values), price;
       - attars: variant table (label, price, default radio) with the bag-charges-default-size warning;
       - bakhoor: weight and price;
       - gift-sets: contents and price.
     - Inventory: Track quantity toggle and stock.
     - Scent notes (edp and attars).
     - Ingredients and barcode.
     - Related products and Search engine listing (after wiring).
   - Side column:
     - Status, with the line 'Draft hides it from the shop, not from the public GitHub repo'.
     - Category. A change warns that fields and card meta change.
     - Never discounted: a guarded toggle whose confirm dialog explains the Reserve badge and the ladder exclusion.
     - Merchandising: the stored-only fields, badged.
     - Where it appears: shelves, hero slides, reels, navigation, related, quiz, gift box picker. Each entry links to its editor.
   - Header: View on store (product.html?p=id), previous/next, History, More (Duplicate, Delete).
4. Products > Inventory. Tracked products only. Stock is editable inline; filter '5 or fewer' (the badge rule); one Save applies every row as one transaction.
5. Products > Bulk editor. Grid of the selection: name, status, default price, variant prices, stock, order.
   - Arrow-key navigation, Enter/F2 to edit, TSV paste from a spreadsheet.
   - Changed cells are tinted.
   - 'Save N changes' runs one transaction and one build.
   - Conflicting rows are listed with 'Reload row'.
6. Products > Import and export. Export all or the selection as CSV. Import runs in three steps:
   - choose a file;
   - review a dry-run table (created, changed, unchanged or error per row, with field-level before and after);
   - Apply or Cancel.
7. Collections. The four categories as cards:
   - label and intro;
   - circle tile (image, tint, cut-out);
   - homepage shelf size and 'see all' label;
   - product membership in manual order, with the same drag reorder as the product list.
   'Add collection' is disabled, with the reason: the category keys are wired into the filter, card meta and breadcrumb in code.
8. Content > Homepage. A section list in the page's real order, each opening a form: Hero, Category circles, USP strip, Quiz banner, Attars shelf, Discovery band, Never discounted shelf, Gift sets shelf, Scent families, Promos, Bakhoor shelf, EDP shelf, Reels.
   - Hero slides: add, duplicate, remove, drag reorder (at least one slide must remain).
     - Fields: eyebrow; headline (Enter inserts the newline that build.py turns into ' <br>'); body; two CTAs from a link picker; alt.
     - Image with two crop frames: desktop 2400x790 and phone 1110x600.
   - Reels: product picker, video upload, reorder.
   - Side pane: 'Open homepage' in a new tab, plus a sandboxed device-width preview (375, 768, 1280) for layout only.
9. Content > Pages.
   - Fixed pages as copy groups: PDP tabs and notes, Collection, Gift box, Bag labels, Track order, Corporate, Account, 404, the noscript line.
   - Locked groups shown read-only with a lock: Checkout, Order confirmed.
   - Custom pages (Our story, FAQ): create (slug, title, blocks: heading, paragraph, list), SEO, delete.
10. Content > Navigation.
   - Category bar and circles (one list feeds both catnav and catstrip): label, link picker, tint (enum read from flow.css), image, cut-out flag.
   - Tab bar: label, link, icon.
   - Footer columns, after wiring.
   - A warning chip flags two entries that share one destination (HANDOFF open decision 2).
11. Content > Quiz (after wiring).
   - Question cards with answers.
   - An answer-to-facets matrix.
   - Result profiles as product references; name, price, notes and barcode are read from the product and not retyped.
   - The disclaimer note.
12. Content > Translations (after wiring).
   - EN/AR dictionary table with RTL inputs, a coverage figure and a 'Missing' filter.
   - Per-product Arabic name and story coverage.
13. Content > Files. Grid and table of img, cat and video. Each file shows:
   - preview, dimensions and bytes;
   - 'used by' links;
   - sized-copy status (-600, -card-360, -thumb, -1320, -phone-750, -216, -486).
   A 'Not used but still published' group offers Move to trash. Uploads are by kind: banner, category photo, cut-out, logo, emblem, video.
14. Discounts.
   - Parameter cards: Volume ladder (units to percent rungs), Gift box (fee, discount at N items, percent), Gift with purchase (threshold, gift label).
   - Each card states what stays in code.
   - A disabled 'Discount codes' card.
15. Online Store > SEO and preferences.
   - Per-page title and description for the 11 pages and any custom pages, with a snippet preview.
   - Title suffix, og:image, site_url.
   - Social links.
16. Online Store > Publish. Three tabs: Not committed, Not live, Published (see publish_flow).
17. Online Store > History. A per-resource timeline of local saves and published versions, a side-by-side semantic diff, and 'Restore this version' (a normal save).
18. Settings.
   - Editable panels:
     - Store details;
     - Brand;
     - Shipping and delivery: free-over threshold, fee, same-day fee, cutoff HH:MM Dubai time, low-stock threshold;
     - Policies;
     - Languages.
   - Read-only locked panels: Payments, Checkout, Taxes (VAT 5% inclusive). Each reads 'Changed by a developer in code'.
   - Users: disabled until login.
   - Admin panel:
     - server info (python path and version, Pillow, ffmpeg);
     - backups (size, 'remove older than N days, keep the latest 50 per file');
     - audit log;
     - 'Rebuild now' and 'Regenerate image copies'.

## security_model

THREAT MODEL
Defends against:
(1) any website open in the owner's browser: CSRF against localhost, DNS rebinding, clickjacking;
(2) script running on the storefront preview, which shares the admin's origin http://localhost:4310;
(3) other machines on the same network;
(4) crafted or oversized uploads;
(5) path tricks in fields and URLs;
(6) content that would become stored XSS on the live site;
(7) unreviewed publishing.
It does not defend against malware, other local accounts or browser extensions running with the owner's privileges. Those can edit the files directly, which is why the admin stays loopback-only until Auth0 and a real server exist.

What the removed admin got wrong (git show 75c4872^:flow/admin/server.py). The new design fixes each point:
- It lived in flow/ and was downloadable from the live site.
- It had no Host or Origin check.
- POST /api/import and /api/restore parsed any body as JSON, so a cross-site no-cors fetch with a text/plain body could overwrite every content file and trigger a rebuild.
- It saved before building and kept the save when the build failed.
- Its backups had one-second names and were pruned to 20.

1. BINDING
- The server binds 127.0.0.1 only. flow/server.py binds '', which means every interface.
- Startup refuses a --host that is not a loopback literal.
- Startup also refuses to run if flow/admin exists.
- ::1 is not bound; browsers fall back to 127.0.0.1 for localhost.

2. HOST ALLOW-LIST (DNS REBINDING)
- Every request, storefront included, must carry Host exactly localhost:<port> or 127.0.0.1:<port> (case-insensitive).
- Anything else, or no Host at all, gets 421 with an empty body.
- A rebinding page arrives with Host attacker.example:4310 and never reaches a handler.

3. ORIGIN AND FETCH METADATA (CSRF)
- Every /admin/api request other than GET or HEAD must carry Origin http://localhost:<port> or http://127.0.0.1:<port>. A missing Origin or 'null' gets 403 forbidden_origin.
- When Sec-Fetch-Site is present, it must be same-origin for the API, and same-origin or none for the /admin page.
- OPTIONS returns 405 and no response ever carries Access-Control-Allow-*. Every cross-origin preflight, including Chrome's Private Network Access preflight, therefore fails.
- GET never changes state.

4. PER-RUN TOKEN
- Generated at start with secrets.token_urlsafe(32), held in memory only, never logged or written to disk.
- Inserted at serve time into the admin HTML as <meta name="admin-token">. That response is sent with Cache-Control: no-store, so the token never reaches a disk cache.
- The admin JS copies it into a module variable and removes the meta element.
- It never goes into localStorage, sessionStorage, cookies, URLs or BroadcastChannel messages. The storefront shares the origin and could read all of those.
- Every /admin/api request, GET included, sends X-Admin-Token, checked with hmac.compare_digest; missing or wrong gets 401. The custom header also forces a preflight, which fails cross-origin.
- A restart rotates the token; open tabs then show 'The admin restarted: reload'.

5. ISOLATION FROM THE SAME-ORIGIN STOREFRONT PREVIEW
Without these measures, storefront JS could fetch /admin, read the token and drive the API.
(a) GET /admin/ is served only to top-level navigations. When Fetch Metadata is present it must say Sec-Fetch-Mode: navigate and Sec-Fetch-Dest: document; otherwise 403. fetch() and iframes get nothing.
(b) The admin page carries Cross-Origin-Opener-Policy: same-origin and storefront pages do not. A window the storefront opens onto /admin lands in a separate browsing context group and its handle is severed, because COOP matches policy as well as origin.
(c) frame-ancestors 'none' and X-Frame-Options: DENY on the admin.
(d) The admin opens the store with target=_blank rel='noopener noreferrer' and never sets window.name. Its inline device preview is an iframe with sandbox='allow-scripts' and no allow-same-origin, so the framed store runs in an opaque origin and cannot reach window.parent. The bag and wishlist do not persist inside it, by design; the full-fidelity preview is the new tab.
(e) Storefront responses from this server carry Content-Security-Policy: connect-src 'none', or, once settings.json "auth" names a shopper sign-in domain, connect-src with that origin alone (widened on purpose on 2026-09-14): the account page posts a sign-in's code to its token endpoint, and that is the only call shop.js makes. A store page still cannot reach the admin API on this origin, so even a leaked token could not be replayed from it.
(f) Third-party scripts such as analytics pixels stay out of the local preview until the admin moves to its own origin with login.

6. REQUEST HYGIENE
- Each route has a method allow-list.
- API bodies must be Content-Type: application/json. text/plain, form and multipart bodies get 415, which closes the no-cors CSRF path.
- Uploads are the raw file as the body, typed image/jpeg, image/png, image/webp or video/mp4. None of these is CORS-safelisted, so they preflight.
- Content-Length is required (411) and checked before reading (413). Caps: JSON 2 MB, CSV 5 MB, product image 25 MB, banner 30 MB, category image or logo 10 MB, video 80 MB.
- Transfer-Encoding: chunked is refused.
- JSON parsing rejects duplicate keys (object_pairs_hook), nesting deeper than 20, and NaN or Infinity.
- The 15 s handler timeout from server.py stays.

7. PATH GUARDS
- The client never names a path to write; the server derives every path.
- Ids are matched before use:
  - product id: ^[a-z0-9]+(-[a-z0-9]+)*$, at most 64 characters, and not constructor, prototype, __proto__, toString or any other Object.prototype name;
  - document names: from a fixed set;
  - snapshot ids: ^\d{8}-\d{6}-\d{6}$;
  - staging and trash ids: server-issued hex.
- Paths stored in content must match ^assets/(img|cat|video)/[a-z0-9][a-z0-9._-]{0,100}\.(jpg|png|mp4)$. Product frames must match ^<id>-\d{1,3}\.jpg$.
- Every path goes through safe_join(root, rel), which:
  - rejects absolute paths, backslashes, NUL, '..' segments and leading dots;
  - requires os.path.realpath to stay under realpath(root) + os.sep;
  - requires os.lstat to find no symlink on any component.
- The storefront handler serves only the deploy's published set: flow/*.html, favicon.ico, robots.txt and assets/** minus assets/flow.css and assets/cat/SOURCES.txt. content/, tools/, build.py, edp_data.json and .backups return 404 locally, just as they do live.
- Admin UI files come from an explicit allow-list under admin/ui.
- The clean-room check extracts git archive output with its own member validation (regular files and directories only, no absolute or '..' names, no links). Python 3.9.6's tarfile has no extraction filters.

8. IMAGE UPLOADS
Checks:
- Magic bytes must agree with both Content-Type and Pillow's format: JPEG FF D8 FF, PNG 89 50 4E 47 0D 0A 1A 0A, WebP RIFF....WEBP.
- HEIC and SVG are refused with a message. SVG can carry script and everything in flow/assets is published.
- Decompression bombs: Image.MAX_IMAGE_PIXELS = 50_000_000, plus warnings.simplefilter('error', Image.DecompressionBombWarning), so an oversized image raises instead of warning. im.size is checked from the header before im.load().
- Refused outright: animated images, and a side over 12000 px.
- Refused as too small for their target: product frames under 1000 px, banners under 2400 px wide, phone crop regions under 1110 px.
Processing:
- ImageOps.exif_transpose.
- Convert to sRGB with ImageCms when an ICC profile is present (phone photos are Display P3; ImageCms is available in /usr/bin/python3's Pillow 11.3.0).
- Flatten alpha onto white for product frames, as the importers do.
- Crop and resize, then save a new file with no EXIF or other metadata, which removes GPS.
- The file stored is always the re-encoded one, named by the server. Uploaded bytes never land under flow/assets.
- Cut-outs must be PNG with real alpha: at least 90% of edge pixels below alpha 16. HANDOFF records four supplied cut-outs that were painted checkerboards.

9. VIDEO UPLOADS
- The upload is written to a staging file under flow/content/.backups/staging.
- ffprobe -v error -print_format json -show_format -show_streams, with a 20 s timeout, must find one h264 or hevc video stream, portrait, at least 540x960, at most 30 s long.
- It is then transcoded (timeout 180 s):
  ffmpeg -nostdin -protocol_whitelist file -f mov -i <staging> -an -t 30 -vf scale=540:960:force_original_aspect_ratio=increase,crop=540:960 -c:v libx264 -profile:v high -pix_fmt yuv420p -r 30 -b:v 650k -maxrate 900k -bufsize 1300k -movflags +faststart <out>
- A 480x854 still is cut at 0.5 s.
- Forcing the demuxer and whitelisting only the file protocol stops playlist or concat tricks that read other files or the network.
- Every subprocess gets an argv list, never shell=True.

10. CONTENT VALIDATION AGAINST STORED XSS ON THE LIVE SITE
Today shop.js inserts story lines, ingredients and size labels with innerHTML, build.py emits the USP strip, the quiz banner and card meta unescaped, and esc() does nothing about javascript: URLs. So the validator:
- refuses < and > in every text field, along with control characters, U+2014 and U+2015 (the repo rule), and '%%' (the trap that shipped 'VAT at 5%%');
- accepts an href only if it is an internal link in the link picker's grammar: a generated page name, an optional ?p=, ?cat= or ?q= value of [a-z0-9,-], and an optional #fragment. Social fields alone may take https on instagram.com, wa.me or tiktok.com.
Phase 0 also makes build.py and shop.js escape every content value, so neither layer is trusted alone.

11. CONFINEMENT
The admin process writes only to:
- the fixed flow/content/*.json names;
- flow/content/.backups/**: snapshots, journal, staging, trash, verify sandboxes, audit.jsonl, lock;
- server-generated .jpg, .png and .mp4 files in flow/assets/img, flow/assets/cat and flow/assets/video.
Subprocesses come from a fixed table:
- build.py;
- tools/make_derivatives.py;
- tools/make_favicon.py;
- git (fixed subcommands only);
- ffprobe and ffmpeg.
Each tool has an allowed-output list:
- build.py: flow/*.html, 404.html, robots.txt, assets/catalogue.js, assets/flow.min.css;
- make_derivatives: the sized copies and tools/derivatives.json;
- make_favicon: flow/favicon.ico and three PNGs.
The runner compares `git status --porcelain -z --ignored -- flow` plus a size and mtime scan before and after each run. Any other change fails the transaction and rolls it back.
Never run: import_images.py, import_new_edits.py, import_website_set.py and recover_pasted_velvet.py. They read Desktop folders and chat transcripts outside the repo and rewrite products.json wholesale.
The only network traffic is git fetch and push to origin. There is no 'import from URL'.

12. NEVER DEPLOYED, NEVER LINKED
- The admin lives in admin/ at the repo root. netlify.toml and pages.yml copy only flow/*.html, favicon.ico, robots.txt and flow/assets, so nothing under admin/ can be published.
- _redirects gains '/admin/*  /flow/404.html  404!' for the root-publish fallback.
- Publish checks, and a Phase 0 check in build.py, refuse any published file containing '/admin', 'localhost' or ':4310', and refuse if flow/admin exists.
- The admin source is public on GitHub; that is fine because it contains no secret.

13. RESPONSE HEADERS FOR /admin AND /admin/api
- Cache-Control: no-store
- X-Content-Type-Options: nosniff
- Referrer-Policy: no-referrer
- Cross-Origin-Resource-Policy: same-origin
- Cross-Origin-Opener-Policy: same-origin
- X-Frame-Options: DENY
- Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; font-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'
The UI uses no inline scripts and no style attributes; styles are set through CSSOM.

14. NEVER POSSIBLE FROM THE ADMIN
Enforced on the server, not only hidden in the UI:
- Editing payments or checkout. settings.payments, the COD cap and fee, VAT, and the checkout.html and confirmed.html copy are locked paths; a hand-crafted request gets 403 locked_field.
- Editing code. No endpoint reads or writes .py, .js, .css, .html, .toml or .yml, and uploads cannot produce .js, .css, .svg or .html.
- Pushing without the owner's confirmation, or with any form of force.
- Pulling, merging, rebasing, resetting, stashing or checking out, and changing git config, remotes or credentials.
- Writing outside flow/content and flow/assets, other than the listed tool outputs and .git through commit.
- Storing orders, customers, enquiries or any personal data in content files. The repo is public.
- Adding reviews or ratings by hand.
- Deleting files permanently. Removed files go to trash.
- Serving on a non-loopback address.

15. WITH AUTH0 LATER
Every check above stays. The token becomes an Auth0 session: an httpOnly SameSite=Strict cookie plus the Origin check and a CSRF token. Roles gate the locked areas, and the admin moves to its own origin, separate from the storefront.

## storage_layer

PRINCIPLE
build.py keeps reading flow/content/*.json, now and after PostgreSQL.
- Those files are the build input, and in git they are the record of what went live. CI cannot reach a database.
- The storage layer is therefore the editing store, and 'export the canonical snapshot to flow/content' is part of its interface.
- Validation, locked-field checks, guarded fields and referential integrity live in a service layer above the store (admin/bgsadmin/validate.py). Both implementations get identical rules.

INTERFACE (admin/bgsadmin/store/base.py)
Doc = (kind, id, rev, data). Kinds: 'product' (a collection keyed by id) and the singletons settings, copy, home, navigation, pages, quiz, translations (id '_'). rev is an opaque string.

class ContentStore:
    def read(self, kind, id) -> Doc                          # NotFound
    def list(self, kind, where=None, order_by=None) -> list[Doc]
    def collection_rev(self, kind) -> str                   # guards reorder, bulk, CSV apply
    def transaction(self, reason, actor) -> Txn             # context manager, one writer at a time
    def history(self, kind, id, limit=50) -> list[Revision] # local saves + published versions
    def revision(self, revision_id) -> Doc
    def export_snapshot(self) -> dict[str, bytes]           # canonical bytes of flow/content/*.json
    def recover(self) -> list[str]                          # undo interrupted transactions at startup

class Txn:
    def get(self, kind, id) -> Doc
    def create(self, kind, id, data) -> str                 # Conflict if the id exists
    def put(self, kind, id, data, expect_rev) -> str        # PreconditionFailed(current_rev, current_data)
    def patch(self, kind, id, ops, expect_rev) -> str       # RFC 6902 subset: replace, add, remove, move
    def delete(self, kind, id, expect_rev)
    def reorder(self, kind, ids, expect_collection_rev)
    def add_file(self, rel_path, staged_file)               # media created in this transaction
    def trash_file(self, rel_path)                          # moved, restorable
    def before_commit(self, hook)                           # derivatives, build: failure aborts the txn
    def commit(self) / rollback(self)

Errors: NotFound, Conflict, PreconditionFailed, LockedField, ValidationError(list), Busy(operation), BuildFailed(problems).

JSON IMPLEMENTATION (store/jsonstore.py), NOW
File map
- 'product' maps to flow/content/products.json: one object keyed by id; key order preserved; new products appended with order = max + 1.
- Singletons map to flow/content/<kind>.json. pages.json, quiz.json and translations.json are created by Phase 0.

Canonical form
- json.dumps(obj, indent=2, ensure_ascii=False) + '\n'.
- products, settings, copy and navigation already round-trip byte for byte (checked). home.json does not: its reels items are hand-written one per line. Phase 0 commits a one-time normalization so every later diff shows only real edits.

Revisions
- Product rev: the first 16 hex of sha256 of that product's canonical JSON. Edits to different products therefore never conflict, even though they share a file: under the lock the store re-reads products.json, replaces one entry and writes.
- Singleton rev and collection rev: sha256 of the file bytes.
- The store caches (mtime_ns, size, sha) per file and re-parses when either changes. That is how edits from a terminal, a Claude session or an importer are noticed, both as 412s and as the 'changed outside the admin' chip.

Locking
- One process-wide threading.Lock guards every mutation, taken without waiting. A second writer gets 423 Busy naming the running operation.
- fcntl.flock on flow/content/.backups/.admin.lock stops a second admin process.
- Reads take no lock, because files are only ever replaced, never rewritten in place.

Atomic write
1. tempfile.mkstemp in the same directory, with a dot prefix.
2. write, flush, os.fsync, then fcntl.fcntl(fd, F_FULLFSYNC). On macOS plain fsync does not flush the drive cache; F_FULLFSYNC is available here (checked).
3. chmod 0644, os.replace, then fsync the directory fd.
4. Stray dot-.tmp files are swept at startup.

Transactions: journal plus snapshot
1. Create flow/content/.backups/txn/<utc-stamp>-<rand>/manifest.json with {state: prepared, reason, actor, files: [{path, before_sha, snapshot}], created: []}.
2. Copy every file the transaction touches, plus the whole generated set, into that directory. The generated set is flow/*.html, 404.html, robots.txt, assets/catalogue.js, assets/flow.min.css and tools/derivatives.json, about 300 KB.
3. Atomic-write the content and move staged media into place; state becomes applied.
4. Run before_commit hooks: make_derivatives.py when media changed (0.3 s measured with nothing to do), then build.py (0.57 s measured).
5. On success, state becomes committed. The content snapshots stay as backups.
6. On any failure:
   - restore every snapshot byte for byte;
   - delete the files this transaction created;
   - re-hash to verify;
   - set state to rolled_back;
   - return the build's problem list.
Why the outputs are snapshotted: build.py writes catalogue.js and every page before its checks run. On a scratch copy, a price change plus an image with no sized copies exited 1 with the new price already in index.html.
recover() rolls back any manifest still in prepared or applied when the server starts.

Backups, trash, audit
- Every commit leaves the previous content files at flow/content/.backups/<name>.<YYYYmmdd-HHMMSS-ffffff>.json. The six existing <name>.<YYYYmmdd-HHMMSS>.json backups stay readable.
- Nothing is pruned automatically. Settings > Admin offers 'remove backups older than N days, keeping the latest 50 per file'. The directory is already gitignored and outside the published set.
- Media removed through the admin is moved with its sized copies to .backups/trash/<stamp>/assets/..., restorable from Files.
- audit.jsonl gets one line per transaction: {at, actor (OS user now, the Auth0 subject later), action, resource, from_rev, to_rev, txn, build_ms, ok, problems}.

History
- Local revisions come from the backups.
- Published revisions come from git: git log --format='%H%x00%aI%x00%s' -- flow/content/<file> and git show <sha>:flow/content/<file>, narrowed to one product or document.
- Restore is a normal transaction, validated against today's schema, with defaults filled for keys an old version lacks.

POSTGRESQL IMPLEMENTATION (store/pgstore.py), WITH-DATABASE
Tables
- products(id text primary key with the same check, category text, status text check (status in ('active','draft','archived')), sort_order int, data jsonb, rev bigint, updated_at timestamptz, updated_by text)
- documents(key text primary key, data jsonb, rev bigint, updated_at, updated_by)
- media(path primary key, kind, sha256, width, height, bytes, created_at, created_by)
- revisions(id bigserial, entity, entity_id, rev, data jsonb, actor, at, reason, txn uuid), written in the same transaction as the change
- audit_log
- publishes(id, at, actor, commit_sha, remote_before, remote_after, files jsonb)
data keeps the JSON files' shape at first, a lift and shift, so the service layer and the export do not change. Variants and images can be normalized into tables later behind the same interface.

Locked areas are enforced in the database as well: payment, checkout and tax settings sit in a table the admin role may only SELECT.

Concurrency
- UPDATE products SET data=$1, rev=rev+1 WHERE id=$2 AND rev=$3. Zero rows means PreconditionFailed.
- READ COMMITTED, with SELECT ... FOR UPDATE on the rows being changed.
- pg_advisory_xact_lock around export and build, so two saves never interleave on flow/content.

Save path
BEGIN; write rows and revisions; export_snapshot() to flow/content (same atomic writes and output snapshot); run derivatives and build.py; COMMIT only if the build passed, else ROLLBACK and restore the files. Only active products are exported, which finally makes drafts private (today a draft is public in the repo).

Migration
A one-off script reads through JSONStore and writes through PGStore, then compares export_snapshot() of both byte for byte. The same comparison runs in the test suite so the two implementations cannot drift. psycopg is the first non-stdlib dependency and arrives with that phase in its own venv.

Never in either store's export
Orders, customers, enquiries and reviews live in their own Postgres tables, outside the repo, and are never exported to flow/content.

## publish_flow

FOUR STATES
- Saved: on disk and built; visible at http://localhost:4310/.
- Committed: in local git history.
- Live: pushed to origin/main; Netlify and GitHub Pages both deploy on push.
Every move to the next state is a separate, explicit owner action.

1. SAVE (every form, upload, reorder, restore)
- Steps: validate, check the rev, open a transaction, atomic write, make_derivatives when media changed, build.py, then commit or roll back (storage_layer).
- Git is never touched.
- The storefront preview reflects the change immediately; the server sends no-store on every response.
- A failed build returns the problem list, and the files on disk are exactly what they were before.
- If the tree did not build before the change (a developer broke build.py, say), saving pauses and a banner shows the problems. If the problem is missing sized copies, the banner offers 'Regenerate image copies'.

2. PREVIEW
- 'View on store' opens the exact page in a new tab (product.html?p=<id>, collection.html?cat=<key>, index.html).
- The in-admin device preview is sandboxed and for layout only.
- The storefront server serves exactly the deploy's file set, so a page that works in the preview cannot 404 live because it depended on content/, tools/ or flow.css.

3. REVIEW AND COMMIT (Publish > Not committed)
Changes are partitioned from `git status --porcelain=v1 -z --untracked-files=all` (run with GIT_OPTIONAL_LOCKS=0) into:
- Content: flow/content/*.json.
- Media: flow/assets/img, cat and video.
- Generated: flow/*.html, 404.html, robots.txt, assets/catalogue.js, assets/flow.min.css, tools/derivatives.json, plus favicon.ico and the icon PNGs if make_favicon ran.
- Build-affecting code: flow/build.py, flow/assets/shop.js, flow/assets/flow.css, flow/edp_data.json.
- Other: everything else (tools/*.py, HANDOFF.md, admin/, deploy files).
The admin-owned set is Content + Media + Generated.

What the owner sees:
- Customer-facing changes as sentences from a semantic diff against HEAD, for example 'Be Mine: price AED 85 -> AED 90' or 'Hero slide 2: headline changed'.
- Before and after thumbnails for media.
- Generated files as a count, expandable.
- Blocking checks and warnings with links.

Commit is enabled only when:
- the last build passed and is not stale (the content hash at build time equals the content hash now);
- no build-affecting code is dirty. The generated pages embed ?v= hashes of shop.js and flow.css, so committing them without that code would make CI's rebuild differ and both deploys fail. The owner is told 'a developer has uncommitted code changes; commit those first';
- no merge, rebase, cherry-pick or bisect is in progress;
- the branch is main.
Uncommitted changes outside the admin-owned set are listed as 'not included' and never staged. (Right now HANDOFF.md, flow/server.py, flow/assets/shop.js and flow.css are dirty in the working tree, so Commit would stay disabled until the developer commits them.)

The commit itself:
- The request carries {message, paths_digest}, where paths_digest is sha256 of the (path, blob sha) list the owner reviewed. The server recomputes it and refuses with 409 if anything moved, for example a save in another tab.
- The message is generated in the repo's style: a sentence-case imperative saying what changed, such as 'Change Be Mine to AED 90 and add its fifth photo'. It is editable, with the subject capped at 72 characters, no em dash, and no trailer or attribution line of any kind.
- Pre-verification in a clean room: `git archive HEAD flow` is extracted into flow/content/.backups/verify/<id>/, the admin paths are overlaid from the working tree, file hashes are taken, build.py runs there, and the tree is hashed again. Any changed or new file means the commit would fail CI, and nothing is committed. This is netlify.toml's `git status --porcelain -- .` check, run on the exact tree about to be committed.
- Then `git add -- <new admin paths>` and `git commit --only -m <msg> -- <admin paths>`. --only commits just those paths and leaves anything the developer has staged alone.
- Post-check: `git status --porcelain -- <admin paths>` must be empty.
- The sha is recorded in flow/content/.backups/publish-log.jsonl as made in the admin.
- If git's index.lock is held (a terminal git is running), the commit fails with a message. The lock file is never deleted.

4. GO LIVE (Publish > Not live)
a) Fetch
'Check GitHub' runs `git fetch --no-tags origin main` with GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=/usr/bin/false and a 60 s timeout. It runs only on opening this tab or clicking refresh, never on a timer. Offline means no publishing, and the screen says so.

b) Preconditions
Each renders as a pass or fail row. Any failure disables the button and says why:
- On branch main, HEAD not detached, no in-progress operation.
- `git merge-base --is-ancestor origin/main HEAD` succeeds. Otherwise the screen says: 'GitHub has N commits this computer does not have. Nothing will be pushed. A developer must bring them in from the terminal.' The admin never pulls, merges or rebases.
- HEAD is at least one commit ahead.
- The clean-room rebuild of HEAD passes (git archive HEAD, build.py, byte compare, no new files). The result is cached by sha.
- Published-file checks on HEAD:
  - no U+2014 anywhere in flow/*.html, 404.html, assets/*.js or assets/flow.min.css (the repo rule's sweep);
  - no '/admin', 'localhost' or ':4310' in any published file;
  - flow/admin does not exist;
  - only jpg, png, mp4, js, css, ico and txt under flow/assets;
  - no single file over 25 MB.
- A secret scan of `git diff origin/main HEAD` finds nothing: private-key headers, AKIA, ghp_, sk_live_, .env files.
- Saved-but-uncommitted admin changes produce a warning, not a block: 'These saved changes are not in a commit and will not go live.' A push only ever sends commits.

c) What goes live, exactly
- Commits: `git log --format=%H%x00%an%x00%aI%x00%s origin/main..HEAD`, each with its `git show --name-status`. Each commit is labelled 'Made in the admin' (sha found in the publish log) or 'Made outside the admin'. The second kind is amber and needs its own tick. main is 3 commits ahead of origin today, all developer commits, and a push publishes them too.
- Files that will change on the site: `git diff --name-status -z origin/main HEAD -- ':(glob)flow/*.html' flow/favicon.ico flow/robots.txt ':(glob)flow/assets/**'`, minus flow/assets/flow.css and flow/assets/cat/SOURCES.txt, which are not published. Grouped as Pages, Images (with thumbnails), Video, Scripts and styles, with sizes.
- What customers will see differently: the semantic diff of flow/content/*.json between origin/main and HEAD, for example 'Price AED 85 -> 90', 'Draft -> Active: Majlis Ritual Set', 'Taken off the site: ...'. Never-discounted changes are highlighted.
- What rides along without being published (docs, tools, admin code), listed separately.
- Where it goes: the Netlify site and GitHub Pages.

d) Owner confirmation
- A dialog repeats the counts and the short sha. The owner types PUBLISH, plus the extra tick if external commits are included.
- The request is {preview_id, local_sha, remote_sha, confirm: 'PUBLISH', include_external}. preview_id = HMAC(token, local_sha + remote_sha + digest of the shown file list), valid for 10 minutes.

e) Push
- The server fetches again. If origin/main is no longer remote_sha, or HEAD is no longer local_sha, it returns 412 'Something changed since you reviewed: review again'.
- It then runs `git push --porcelain --no-tags origin <local_sha>:refs/heads/main`, with the same environment and a 120 s timeout, as a background job the UI polls.
- Pushing the reviewed sha rather than the branch name means exactly the reviewed commit goes live, even if main moves meanwhile.
- The argv comes from constants and the sha must match ^[0-9a-f]{40}$. A guard refuses any argument that starts with '+' or equals --force, -f, --force-with-lease, --mirror, --delete, -d or --prune. There is no code path that adds one.
- A rejection (non-fast-forward, auth, network) shows a stderr summary, and nothing is retried. The admin never asks for credentials; if the keychain has none, it tells the owner to push from Terminal.

f) After
- Fetch again and confirm origin/main == local_sha.
- Append to the publish log (and to the publishes table later).
- Show 'Netlify and GitHub Pages have started deploying'. There is no invented deploy status.
- An optional 'Check the live site' button fetches the live index.html and compares its catalogue.js?v= token with HEAD's.
- One publish can carry many saves and commits. Every push costs two deploys, so batching is encouraged.

UNDO
Reverting a live change means restoring the earlier version through History, which is a normal save, then commit and publish again. History is never rewritten: no revert --no-commit tricks, no reset, no amend of published commits.

NEVER AUTOMATIC
- Pushing: never on save, commit, timer or startup, and never retried.
- Committing: never on save.
- Pull, merge, rebase, reset, stash, checkout, branch, tag or amend of any kind.
- Force of any kind.
- Changing remotes, config or credentials.
- Running importers.
- Publishing from a branch other than main, a failed or stale build, a tree that fails the clean-room check, or files outside the admin-owned set in an admin commit.
- Resolving conflicts on the owner's behalf.

## server_design

0. PREREQUISITE: PHASE 0 CODE WIRING (normal developer commits, reviewed, never made by the admin)
The admin cannot make 'everything visible editable' until the storefront reads it from content.

build.py
- Move every visitor-visible literal into content, with today's strings as the migrated values:
  - into copy.json: the strip and its links, search placeholder, footer columns, legal line and address, Discovery band (tied to the discovery-trio product so its price follows the product), promos, family tile labels, PDP tabs (how to apply, delivery and returns, the reviews empty state, the credit-back note, facts rows), gift box copy, cart progress labels, track, corporate and account copy, the 404 and noscript lines;
  - into home.sections: the section headings;
  - computed: shelf 'see all' counts;
  - picker ids: the gift box picker (today attar_cards(6));
  - into settings.seo.pages: PAGE_DESC;
  - into settings.seo: the title suffix.
- Escape every content value: the USP strip, the quiz banner, and the _meta parts.
- Emit into catalogue.js:
  - window.BGS_RULES from settings.store: new keys volume_ladder, gift_with_purchase, sameday_cutoff_24h, low_stock_at;
  - window.BGS_COPY: CAT_LABEL, CAT_INTRO, bag and box labels, the AR dictionary from translations.json;
  - per-product related, image_alt and seo fields.
- Render content/pages.json through one generic template, append those pages to PAGES, and delete the custom pages it previously wrote but no longer does. They carry a generator marker, so the '*.html not written by build.py' check stays true.
- Fail if any output contains '/admin'.

shop.js
- Read BGS_RULES, with fallbacks equal to today's constants: 150, 12, 25, 14:00, 300, 3/10, 6/15, box 25 and 10%, low stock 5.
- Read CAT_LABEL, CAT_INTRO and AR from BGS_COPY.
- Render related products.
- Take the quiz from quiz.json by product id.
- Set story, ingredients and names with textContent or esc.
- recalc's structure, the halo exclusion, the VAT-inclusive formula and the 1 to 20 clamp are not touched.

Acceptance
With migrated content, build.py output is byte-identical to today's. Visible fixes land as separate commits: the footer links, the 'AED 89' quiz price and null names, and the stale 'oud oils, Reserve' intro.

Hygiene
- Normalize home.json formatting once.
- Delete flow/server.py.
- Point .claude/launch.json 'bgs-flow' at runtimeExecutable /usr/bin/python3, args ['admin/server.py'], port 4310. /usr/bin/python3 is 3.9.6 with Pillow 11.3.0.
- .gitignore: flow/content/.*.tmp and admin/**/__pycache__/.
- _redirects: the /admin/* refusal line.
- Optionally a deploy step that fails if _site contains 'admin'.
- Update HANDOFF §4 and §7.

1. FILE LAYOUT (repo root, outside flow/)
admin/
  server.py              entry point: args, startup checks, recovery, token, serve
  README.md              how to run, what it can and cannot do
  bgsadmin/
    config.py            REPO, FLOW, CONTENT, BACKUPS, ASSETS, PORT, allowed hosts and origins, limits, PUBLISHED rule, TOOL table
    httpd.py             Server(ThreadingMixIn, TCPServer) + Handler: security gate, dispatch, JSON I/O, errors
    routes.py            route table (method, compiled regex with named, pre-validated groups, handler, flags)
    security.py          host, origin, fetch-metadata and token checks, safe_join, header sets, CSP strings
    static.py            storefront preview (published set, Range, 404.html) and admin UI allow-list
    schema.py            field schemas per resource and category; locked, guarded, rendered flags. Icon keys and category keys are read from build.py with ast (no import: build.py builds on import); tints from flow.css
    validate.py          types, bounds, regexes, text rules, href grammar, cross-field rules, referential integrity
    lint.py              warnings: rule and price mentions vs data, claim words, empty stories, unused published files, cut-out alpha
    diff.py              semantic JSON diff -> sentences
    store/base.py, store/jsonstore.py   (pgstore.py later)
    media.py             staging, Pillow pipelines per kind, naming, trash and restore
    video.py             ffprobe / ffmpeg
    tools.py             allow-listed subprocess runner with an expected-output check
    gitops.py            read-only queries; commit --only; fetch; push by sha; clean-room verify
    csvio.py             export and import (dry-run plan, apply)
    jobs.py              background jobs (push, video) with polling
    audit.py
  ui/                    index.html, admin.css, app.js, lib/, components/, screens/ (see ui_design)
  tests/                 stdlib unittest (section 8)

2. PROCESS AND STARTUP
`python3 admin/server.py [--port 4310] [--storefront-only]`
- Resolves REPO from __file__.
- Refuses to start if:
  - the host is not loopback;
  - flow/admin exists;
  - flow/content is missing;
  - the port is taken (message, exit 1).
- Runs store.recover(), sweeps stray .tmp and staging files, and generates the token.
- Probes Pillow, ImageCms, ffmpeg and ffprobe. A missing one disables the matching uploads with a message instead of failing later.
- Records the content hash of the last known good build.
- Serves with class Server(socketserver.ThreadingMixIn, socketserver.TCPServer): allow_reuse_address = True, daemon_threads = True, and handle_error that ignores BrokenPipeError and ConnectionResetError. That is today's server.py, bound to ('127.0.0.1', port) instead of ''. TCPServer is used rather than HTTPServer because HTTPServer.server_bind calls socket.getfqdn, which can stall on macOS.
- Handler behaviour: HTTP/1.0; timeout = 15; log_message silent for static requests and one line per mutation.
- Prints the two URLs: http://localhost:4310/ and http://localhost:4310/admin/.
- --storefront-only mounts no admin routes and generates no token, for sessions that only need the preview.
- On Ctrl+C the server waits for a running transaction to finish or roll back, then shuts down.

3. ROUTING AND STATIC SERVING
Security gate, in order, for every request:
1. Host allow-list.
2. Method allow-list for the route.
3. For /admin/*, Fetch Metadata rules.
4. For /admin/api/*, token, then Origin on non-GET, then Content-Type and Content-Length.
Only then dispatch.

Storefront, GET/HEAD for everything not under /admin:
- Unquote the path; '/' maps to index.html; the query is ignored.
- The path must be in the published set via safe_join(FLOW).
- Headers: Cache-Control: no-store, no-cache, must-revalidate, max-age=0; Pragma: no-cache; Expires: 0 (today's behaviour), plus nosniff and connect-src 'none'.
- Single-range Range support: bytes=a-b, a- and -n give 206 with Content-Range; unsatisfiable gives 416; Accept-Ranges: bytes. Safari will not play mp4 without it, and http.server has none.
- MIME types: .mp4 video/mp4, .js text/javascript, .css text/css, .ico image/x-icon.
- A miss returns flow/404.html with status 404, as today.

Admin UI
- /admin redirects 308 to /admin/.
- /admin/ serves ui/index.html with the token substituted.
- /admin/ui/<allow-listed file> serves the file with no-store.

4. API CONTRACT (prefix /admin/api/v1; JSON bodies; responses application/json; charset=utf-8)
Conventions
- Every update needs If-Match: "<rev>" (428 rev_required when missing; 412 stale_rev with {current_rev, current} when it does not match).
- Every mutation that changes content returns {rev, build: {ok, ms, problems}}.
- Mutations that touch several documents take expect_collection_rev.
- Guarded fields must be listed in confirm_guarded: ["never_discount"], or the server answers 428 guarded_field.

Session and meta
- GET session -> {repo, branch, head, python, pillow, ffmpeg, build: {ok, at, ms, problems, stale}, changes: {uncommitted, unpushed}}
- GET schema -> {resources: {product: {fields: [{path, type, label, help, required, min, max, maxLength, pattern, enum, visibleWhen, rendered, locked, guarded}]}, ...}, icons, tints, categories, limits}
- GET status -> {content_revs, build, changes, external_change: bool}. Polled every 3 s while the tab is visible.

Products
- GET products?status=&category=&q= -> {collection_rev, items: [{id, rev, data}]}
- POST products {id, data} -> 201 {id, rev, build}
- GET products/{id} -> {id, rev, data, refs: [{where, label, admin_link}]}
- PUT products/{id} {data, confirm_guarded?}
- PATCH products/{id} {ops: [{op: replace|add|remove|move, path: '/sizes/1/price', value}], confirm_guarded?}
- DELETE products/{id} -> 204, or 409 {refs}
- POST products/{id}/duplicate {new_id, name} -> 201
- POST products/reorder {expect_collection_rev, category, ids: [...]}. Reassigns that category's existing order values in the new sequence.
- POST products/bulk {changes: [{id, rev, ops}]} -> 200 {revs} | 412 {conflicts: [{id, current_rev}]} | 422 {errors: {id: [...]}}. All or nothing.
- GET products/export.csv?ids= -> text/csv; charset=utf-8 with BOM
- POST products/import {csv, mode: 'dry-run'} -> {plan_id, base_rev, rows: [{line, id, action: create|update|unchanged|error, changes, errors}]}
- POST products/import {plan_id, mode: 'apply'} -> {revs, build}, or 412 if products changed since the dry run.

Media
Two steps, so heavy validation stays outside the transaction and crops are possible:
1. POST media/staging, with a raw body typed image/jpeg, png, webp or video/mp4. Validates and re-encodes (images to a metadata-free master; video is only probed). Returns 201 {staging_id, width, height, duration?}, expiring after 24 h. Previews in the UI are client-side blob: URLs, so no token-less GET is needed.
2. POST media/attach {staging_id, expect_rev, target}, where target is one of:
   - {kind: 'product-image', product, position}
   - {kind: 'banner', slide, crop_desktop: {x, y, w, h}, crop_phone: {...}}
   - {kind: 'category-photo', index, crop}
   - {kind: 'cutout', index}
   - {kind: 'logo', variant: 'dark'|'light'}
   - {kind: 'emblem'}
   - {kind: 'reel', index, product}
   Returns {paths, rev, build}. Video attach returns 202 {job}.
Naming:
- Product frames get n = 1 + the highest existing <id>-<n>.jpg on disk, referenced or not, so an unreferenced but published file is never overwritten.
- Banners are banner-<n>.jpg (2400x790) and banner-<n>-phone.jpg (1110x600).
- Category photos are cat/<slug>.jpg as a 432 square; content points at the -216 copy.
- Cut-outs are cat/<slug>.png, normalized to a 204x240 canvas and quantized to 256 colours, like the existing four.
- Logos overwrite logo-gold.png or logo-gold-light.png after trashing the old file, because make_derivatives only knows those names.
- The emblem becomes logo-emblem.png, then make_favicon runs.
- Reels are video/<slug>.mp4 plus a .jpg still.
Other media routes:
- GET media?kind=&unused=1 -> {items: [{path, kind, bytes, width, height, used_by, published: true, copies: {ok, missing, stale}}]}
- POST media/trash {path} -> 409 if referenced; else {trash_id}
- POST media/restore {trash_id}

Documents
- GET documents/{settings|copy|home|navigation|pages|quiz|translations} -> {rev, data, locked: [json pointers], rendered: {pointer: bool}}
- PUT documents/{name} {data}
- PATCH documents/{name} {ops}
A change to a locked pointer gets 403 locked_field, even inside a PUT: the server diffs the incoming document against the current one.

History, checks, tools
- GET history?resource=products/be-mine -> {items: [{id, source: 'local'|'git', at, summary}]}
- GET history/{id}?resource= -> {data, diff}
- POST history/{id}/restore {resource, expect_rev}
- GET checks -> {blocking: [...], warnings: [...]}
- POST build -> {ok, ms, problems}
- POST tools/derivatives -> {ok, output}

Publish and jobs
- GET publish/changes
- POST publish/commit {message, paths_digest} -> {sha} | 409 changes_moved | 422 checks_failed
- POST publish/fetch -> {remote_sha, fetched_at}
- GET publish/preview -> {preview_id, local_sha, remote_sha, commits, published_files, semantic, riding_along, checks}
- POST publish/push {preview_id, local_sha, remote_sha, confirm, include_external} -> 202 {job}
- GET jobs/{id} -> {state: queued|running|done|failed, log_tail, result}
- GET publish/log

Errors
Always {error: {code, message, details}}. The message is plain English for the UI; details are for display and never contain tracebacks.
- 400 bad_json
- 401 bad_token
- 403 forbidden_origin | not_navigation | locked_field
- 404 not_found
- 405 method
- 409 exists | referenced | changes_moved
- 411 length_required
- 412 stale_rev | review_stale
- 413 too_large
- 415 unsupported_media_type
- 421 bad_host
- 422 validation (details: [{path, code, message}]) | build_failed ({problems, restored: true}) | checks_failed
- 423 busy ({operation})
- 428 rev_required | guarded_field
- 500 internal (logged)
- 502 tool_failed (exit code, stderr tail)
- 503 unavailable (Pillow or ffmpeg missing)

5. CONCURRENCY AND WRITES
- One operation lock serializes saves, uploads-attach, builds, commits and pushes. The lock is taken without waiting and names the running operation for the 423 response.
- Staging validation and GETs run in parallel.
- File locking, atomic writes and journal recovery are as in storage_layer.
- The browser side: BroadcastChannel tells other admin tabs {resource, rev} (never content, never the token), and the 412 path covers everything else.

6. TOOLS
tools.py table:
- build: [sys.executable, 'build.py'], cwd=FLOW, timeout 60
- derivatives: [sys.executable, 'tools/make_derivatives.py'], timeout 300
- favicon: [sys.executable, 'tools/make_favicon.py']
- probe and transcode: ffprobe and ffmpeg argv builders
Every run:
- gets env {PATH, HOME, LANG=en_US.UTF-8, PYTHONDONTWRITEBYTECODE=1} and capture_output;
- has 'build failed:' lines parsed into problems;
- is followed by the expected-output check (security_model 11).
gitops.py runs git with -c core.quotepath=off, LC_ALL=C and -z parsing throughout, GIT_OPTIONAL_LOCKS=0 for read-only calls, and GIT_TERMINAL_PROMPT=0 for network calls. The allowed subcommands are status, diff, log, show, rev-parse, merge-base, archive, add, commit --only, fetch and push.

7. VALIDATION RULES (server-side; the client mirrors them for feedback only)
Per category, what _meta and the facets need:
- edp: size and gender (Him, Her, Unisex);
- attars: at least one size, labels unique, price equal to one size's price;
- bakhoor: size;
- gift-sets: contents.
Field rules:
- name: 1 to 60 characters.
- story: up to 6 lines of up to 140 characters.
- price: integer 1 to 100000. stock: null or integer 0 to 100000.
- barcode: ^\d{8,14}$, with an EAN-13 check-digit warning.
- related: up to 4 existing ids, not the product itself.
- images: each name matches the frame regex and the original plus -card, -600, -card-360 and -thumb all exist.
- icon: must be in P. tint: must be in flow.css's c-* classes.
- cutout: needs real alpha.
- Rule bounds:
  - free delivery threshold: 0 to 2000;
  - fees: 0 to 500;
  - cutoff: 06:00 to 22:00;
  - ladder: rungs strictly increasing in units, each percent 0 to 50.
- Text and href rules: as in security_model 10.
Warnings only, never blocking:
- size label format;
- claim words (HANDOFF's list: finest, purest, guaranteed, award, trusted, proven, clinically);
- longevity and projection words in stories while longevity and sillage are empty;
- copy that states a rule or price that no longer matches the data.

8. TESTS (stdlib unittest, run with /usr/bin/python3)
- security: wrong Host gives 421; cross-site and missing Origin give 403; a text/plain POST gives 415; a missing token gives 401; OPTIONS gives no CORS headers; GET /admin/ with Sec-Fetch-Mode: cors gives 403; traversal attempts (%2e%2e, backslash, symlink, absolute, NUL) give 404 or 400; a decompression-bomb PNG, a polyglot and an SVG are refused.
- store: atomic replace; 412 on a stale rev; per-product revs do not collide; crash recovery from a prepared manifest.
- build rollback on a temp copy of flow/: a missing-image failure leaves every file byte-identical.
- publish, against a temp repo with a local bare remote: fast-forward only; a diverged remote is refused; the sha refspec is used; argv never contains force; the clean room catches a stale output.
- An export_snapshot equality test between the JSON and Postgres stores, once Postgres exists.

## ui_design

STRUCTURE (no build step)
- admin/ui/index.html is a static shell. It loads admin.css and <script type="module" src="app.js">; native ES modules need no bundler.
- The server substitutes the token into a meta tag. The page has no inline script or style, as the CSP requires.
- Modules:
  - app.js: bootstrap and hash router (#/products, #/products/be-mine, #/content/home/hero/2, #/publish)
  - lib/api.js: fetch wrapper that adds X-Admin-Token and If-Match, maps error codes to UI states, never auto-retries a mutation
  - lib/upload.js: XHR for upload progress, sending the File as the raw body
  - lib/state.js: document cache keyed by resource with rev, drafts, dirty tracking, BroadcastChannel notices of {resource, rev} only
  - lib/dom.js: h(tag, attrs, ...children), which only ever sets textContent and properties, never innerHTML, so a product name edited by hand elsewhere cannot run in the admin
  - lib/forms.js: schema-to-form renderer
  - lib/dnd.js: pointer-events reorder with a keyboard mode
  - lib/keys.js: shortcuts
  - lib/format.js: AED, dates, plurals
  - components/: savebar, dialog (native <dialog>), toast, banner, badge, text-field, lines-editor, money-field, variant-table, media-grid, crop, link-picker, product-picker, bulk-grid, diff-view, status-chip, empty-state
  - screens/: one module per screen in the IA, imported lazily with dynamic import().
- admin/ui is served with no-store, so admin JS edits apply on reload and there is no ?v= token to forget.

SCHEMA-DRIVEN FORMS
- GET schema supplies the field list per resource and category. forms.js maps each field type to a component:
  - text, textarea, lines (story), int, money (AED, integer)
  - bool, enum, href (link picker)
  - image, images, video
  - product-ref, product-refs, icon, tint
  - rows: an array editor with add, duplicate, remove, reorder and min/max counts
- Flags drive presentation:
  - visibleWhen shows fields by category;
  - rendered:false adds the 'Not shown on the site yet' badge;
  - locked renders read-only with a lock and the reason;
  - guarded opens a confirm dialog and sends confirm_guarded;
  - maxLength shows a live counter.
- Client checks mirror the server's rules for instant feedback: em dash (with a one-click 'replace with a hyphen or colon' fix), < and >, '%%', the href grammar, number bounds, the default-variant price rule.
- On save, the server's 422 list is mapped onto fields by JSON pointer, and an error summary at the top links to each field.
- The same schema module is used for Phase 0 wiring. One Python module is the source of truth; the JS only renders it.

SAVE BAR, DIRTY STATE, GUARDS
- Dirty means a deep comparison of the draft with the loaded document differs.
- While dirty, the Polaris-style contextual save bar replaces the top bar: 'Unsaved changes', Discard, Save. Cmd/Ctrl+S saves; Esc on the bar asks before discarding.
- During a save the fields lock and the bar shows 'Saving and rebuilding'. On success the rev updates, the build chip shows 'Built in 0.6 s', and a toast offers 'View on store'.
- build_failed shows a critical banner with the problems and 'Your change was not applied'. The draft stays so the owner can fix it.
- 412 shows a dialog: 'This changed since you opened it (another tab, a terminal or a Claude session)'. The options are Review differences (diff-view of the current version against the draft), Take theirs, or Re-apply mine on top (re-sends the draft with the new rev).
- Navigation guard: the router cancels a hashchange while dirty and asks 'Leave without saving?'. beforeunload is set while dirty.
- Drafts are autosaved (debounced) to sessionStorage under bgs-admin-draft:<resource>:<rev> and offered back after a reload or an admin restart. They hold content only, never the token.

DRAG REORDER (lists, variants, media, slides, nav entries, category members)
- Pointer Events, not HTML5 drag and drop, so it works with trackpad, mouse and touch; a FLIP animation that reduced motion disables.
- Every handle is a button. Space lifts, arrows move, Space drops, Esc cancels. An aria-live message says 'Be Mine, position 3 of 9'. Move up and Move down menu items cover the same moves.
- Product reorder inside a category sends the id sequence with expect_collection_rev.

IMAGE AND VIDEO UPLOAD
- A drop zone plus <input type=file multiple accept='image/jpeg,image/png,image/webp'> (or video/mp4).
- Client pre-checks: type, size cap, and minimum pixels read with createImageBitmap. A HEIC gets 'Export as JPEG first'.
- Files go one at a time with a per-file progress bar, into staging, and then attach.
- Banners open the crop tool: the image with two fixed-ratio frames (2400:790 desktop, 1110:600 phone) that can be dragged and resized by pointer or arrow keys (Shift for larger steps). Normalized rectangles are sent; nothing is drawn to a canvas.
- The media grid shows 'Card image' and 'Hover image' labels, an alt-text field per product (after wiring), and a warning when a product has a single frame (no hover swap).
- Video shows its duration and dimensions and a 'Transcoding' job state.

BULK EDIT
- A <table role=grid> with a sticky header and name column.
- Cell editors by type. Arrows move; Enter or F2 edits; Tab goes to the next cell; Esc reverts a cell; Cmd/Ctrl+Z steps back through a client undo stack.
- Pasting TSV from a spreadsheet fills a range from the focused cell, validating each cell.
- Changed cells get a --gold-l tint and invalid cells a red outline with a message.
- 'Save N changes' sends products/bulk. A 412 marks the stale rows with Reload row.

CSV
- Export: fetch with the token, turn the response into a Blob, click a temporary <a download>. The admin runs in the owner's normal browser, so downloads work.
- Columns follow Shopify's CSV where they map:
  Handle (id), Title, Status, Category, Price, Default size, Size 1 label, Size 1 price ... Size 4, Stock, Gender, Top, Heart, Base, Ingredients, Barcode, Contents, Never discounted, Order, Image 1 ... Image 8 (file names), SEO title, SEO description, Image alt, Name (Arabic), Story line 1 ... 6.
- Import: read the file with FileReader as text; send it as JSON {csv, mode: 'dry-run'}; show the plan table with filters; Apply sends plan_id.
- Never-discounted changes in a CSV get their own confirm step.

KEYBOARD AND ACCESSIBILITY (WCAG 2.1 AA)
Structure:
- A skip link, then landmarks: header, nav, main, aside.
- One h1 per screen, and focus moves to it on each route change.
- A polite aria-live region for save, build and publish states.
Forms:
- Every input has a visible label; placeholders are never the only label.
- Errors are tied to fields with aria-describedby and aria-invalid.
Dialogs:
- Native <dialog>.showModal traps focus, and focus returns to the opener on close.
Visual:
- Focus rings are 2px --primary with a 2px offset: 3.88:1, above the 3:1 non-text minimum.
- Text colour is never the gold primary; --gold-d is used (5.91:1).
- Status is never colour alone; each has an icon and a word.
- Targets are at least 24px.
- prefers-reduced-motion is respected.
- Layout is responsive down to 375px, with the left nav collapsing to a drawer.
Shortcuts:
- '/' search; Cmd/Ctrl+S save; 'g' then 'p' products; 'g' then 'h' homepage; '?' opens the list.

LOOK: POLARIS STRUCTURE, BGS MATERIALS
Palette (flow.css's tokens, copied into admin.css):
- Top bar on --secondary #171310 with logo-gold-light-486.png.
- Canvas --alt #faf7f2.
- Cards white with a 1px --line #e6e0d6 border, 12px radius and the storefront's shadow 0 1px 2px rgba(23,19,16,.05).
- Text --ink, secondary text --mut #6b6154, dividers --hair.
Type:
- "Helvetica Neue", Helvetica, Arial, sans-serif, the storefront stack.
- Body 13px/20px; headings 600 weight at 20, 16 and 14px.
Buttons and badges:
- Primary buttons solid --secondary (Polaris primaries are near-black too); secondary white with a border; destructive --red #b3261e.
- Gold is kept for emphasis: focus rings, the Never discounted badge (--gold-d on --gold-l), the Publish button's count bubble.
- Other badges: Active (--green on a light green wash), Draft (neutral), Low stock (--red), 'Not shown on the site yet' (neutral outline), Locked (lock icon, grey).
Layout:
- Page width 1000px, detail pages 2/3 + 1/3, tables with 44px rows.
Honest states:
- Empty states say what is true: 'No orders: checkout does not send orders yet'.
Icons:
- admin/ui/icons.js keeps its own copy of the storefront's line-icon paths, drawn at 1.6 stroke so the two feel related.

## risks

- Phase 0 is a prerequisite, not polish. Today most visitor-visible text and every store-rule number is hardcoded in build.py and shop.js, and several content keys are inert: navigation.main, navigation.footer, home.sections, copy.strip, copy.collection_intros, settings.store. The owner's 2026-09-11 footer edit in navigation.json had no effect on the footer. An admin shipped before the wiring would show controls that do nothing.
- Visible content is already wrong in code, where only a developer can fix it. The quiz shows 'AED 89' for every result while the sprays cost AED 85, and keeps 8 of 9 names null although all nine barcodes are products. The collection 'all' intro in shop.js says 'oud oils, Reserve'. The footer's Bakhoor and EDP links go to an unfiltered collection. Family tiles link to collection.html?family=..., which the filter engine ignores. The slot placeholders ('[ count ]', '[ address, hours, phone ]') are shown to visitors.
- Stored XSS reaches the live site if content validation or Phase 0 escaping is skipped. shop.js uses innerHTML for story lines, ingredients and size labels; build.py leaves the USP strip, quiz banner and card meta unescaped; esc() does not stop javascript: hrefs.
- Same-origin preview: the storefront and the admin share http://localhost:4310, so any script on a storefront page, a future analytics pixel included, is one token away from the admin API. The measures (navigate-only admin HTML, COOP on the admin, frame-ancestors none, a sandboxed preview iframe, connect-src 'none' on preview pages) must all ship together. A separate origin with login is the lasting fix.
- The working tree is not clean and the admin will meet that. HANDOFF.md, flow/server.py, shop.js, flow.css, navigation.json and every generated page are modified and uncommitted, and main is 3 commits ahead of origin. Admin commits must be path-limited (git commit --only), Commit must be blocked while build-affecting code is dirty, and Go live must show developer commits riding along.
- The repository is public. Draft products (seasonal-slot today), unannounced launches and anything typed into content are readable on GitHub after a push. Personal data (orders, customers, enquiries, consent) must never enter the JSON store. Private drafts only arrive with Postgres.
- Taking a photo off a product does not take it off the internet. The deploys copy all of flow/assets, so an unreferenced file stays published at its URL until it is moved out, as happened with the Imperial Crown cocktail glass. The Files screen and trash exist for this.
- build.py writes catalogue.js and every page before its checks run. A failed build without output snapshots would leave a half-applied site on disk; this was confirmed on a scratch copy.
- Other writers clobber admin work. Claude sessions and terminal edits change the same JSON. import_website_set.py rewrites products.json wholesale and deletes frames numbered above what a re-import supplies, which would remove admin-uploaded frames. The per-document revs, the external-change detection and a HANDOFF note on running importers only with the admin stopped are the mitigations.
- Copy repeats data, and the repeats go stale. Hero slides state AED 399, AED 650 and 1295 and 'Thirteen attars'; the Discovery band states AED 129; the USP strip and PDP state AED 150, 2:00 PM and AED 300. A price or rule edit makes these false statements, which the no-invented-claims rule treats seriously. Placeholders tied to data and the mentions lint are required, not optional.
- Editable store rules are operational promises (HANDOFF open decision 6): free delivery, same-day, COD, mystery oud, voucher. The admin cannot know whether they are true, so the publish review repeats every changed promise for the owner to confirm. The credit-back voucher, gift wrap price and BGS One numbers are stated on the site and enforced by no code.
- The variant pricing bug makes variant edits misleading: the bag charges the default size whatever chip is chosen (HANDOFF open decision 15). The fix lives in locked cart code.
- Local-only security rests on browser behaviour (Origin, Fetch Metadata, COOP) and on the bind address. Binding to all interfaces, as flow/server.py does today, would expose an unauthenticated write API to the network. Malware or extensions with the owner's privileges bypass everything.
- Python 3.9 is past end of life and /usr/bin/python3 is 3.9.6. The stdlib server only faces loopback, but 3.9.6's tarfile lacks extraction filters (manual member checks are required) and newer security fixes are missing. Moving to a newer Python belongs with the Postgres phase; build output is already byte-identical under 3.9, 3.12 and 3.13.
- Pillow and ffmpeg parse untrusted bytes. The pixel cap, the bomb warning as an error, header checks, re-encoding, the forced demuxer, the protocol whitelist and timeouts reduce but do not remove that risk. HEIC from iPhones is refused until a converter is chosen.
- Media bloat is permanent in a public git repo. Uncapped uploads (25 MB photos, long videos) would grow every clone. Re-encoding to the house specs (1000 px q72 frames, about 0.5 to 1 MB reels) and size caps keep new media close to what is there.
- Every push costs two deploys (Netlify and GitHub Pages). At 100k visits a day, Netlify's credits and GitHub Pages' terms (HANDOFF open decision 12) matter, so the flow batches many saves into one publish.
- Preview is not production. Local no-store headers and the preview-only CSP differ from Netlify's immutable caching and GitHub Pages' ten-minute cache, so a published change can take minutes to show on Pages.
- Postgres migration drift: if the service layer leaks JSON-file assumptions (rev as a file hash, whole-file writes), PGStore will behave differently. The byte-for-byte export_snapshot equality test is the guard.
- Scope creep toward Shopify parity. Disabled Orders, Customers and Analytics entries must stay honest ('Arrives with the database') and never show sample or invented numbers.
- Token rotation on restart can lose in-progress edits unless drafts are kept in sessionStorage. That storage is same-origin with the storefront, so it may hold content but never the token.
- launch.json runs python3 -m http.server today, not server.py. If it is not repointed at /usr/bin/python3 admin/server.py, the Browser pane keeps serving a cacheable preview without the admin, and a python3 without Pillow would break uploads and derivatives.