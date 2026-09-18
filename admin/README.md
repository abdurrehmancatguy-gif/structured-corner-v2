# BGS Corner admin

A back office for the storefront in `flow/`, run on your own computer. It
edits the content files in `flow/content/`, rebuilds the site after every
save and shows the result on a local preview. Committing and going live are
separate steps on the Publish screen.

## Open it

```bash
cd /Users/ajoomama/github/structured-corner-v2
/usr/bin/python3 admin/server.py
```

Then go to http://localhost:4310/admin/ (the store itself is at
http://localhost:4310/). `python3 flow/server.py 4310` starts the same
server. Use `/usr/bin/python3`: it has Pillow, which uploads need. Films
also need ffmpeg and ffprobe in `/opt/homebrew/bin`; without them the film
uploads say so and the rest works.

The `bgs-flow` entry in `.claude/launch.json` still runs
`python3 -m http.server 4310 --directory flow`. That shows the store only,
without the admin.

Options:

- `--port N`: another port (4310 by default).
- `--no-push`: the Publish screen shows everything but cannot push. Every
  test runs with it.
- `--storefront-only`: the store preview alone, with no admin.
- `--repo PATH`: serve and edit another checkout. The tests use it with a
  temporary clone.
- `--store json` or `--store postgres`: which store holds the content.
  Without it, this checkout's `admin/local/store.json` chooses (dbtool
  writes it, see Database), and the JSON files are the default. `--store
  json` always edits the files, even on a checkout switched to the database.
- `--dsn "host=/tmp port=5432 dbname=bgs_corner user=bgs_corner_app"`: the
  database for `--store postgres`, when it is not the one this checkout
  already has. Never put a password in it.

On a checkout switched to the database, start the admin with its own
virtualenv, which has psycopg:

```bash
admin/.venv/bin/python admin/server.py
```

It prints which store it runs on (`store       PostgreSQL bgs_corner as
bgs_corner_app (18.6)`). It never falls back to the files: when PostgreSQL
is not answering it does not start (exit status 3), and it refuses to start
(exit status 2) on a database that belongs to another checkout, is not up to
date, or is used by another admin.

## Screens

The left navigation, in order:

- **Home:** how many products there are, how many are active and how many
  are drafts, and what needs attention: active products without a photo,
  products without a story, and products at 5 or fewer in stock. A banner
  says when the content files were changed outside the admin.
- **Products:** list, search, filter, reorder within a category, add (as a
  draft), duplicate, delete, and edit every field: title, story, prices and
  sizes, stock, status, category, scent notes, ingredients, barcode, and the
  fields kept for later (Arabic, SEO, related products and the rest). The
  Photos card shows the card image first and the hover image second; photos
  are uploaded by picker or drop, dragged into order, made the card image,
  removed, or removed and moved to the trash. Each product links to its
  History.
  - **Inventory:** every product whose stock is tracked, with the stock
    edited in place. A filter shows the products at or under the low-stock
    number in Settings. One save sends every changed row.
  - **Bulk editor:** a spreadsheet grid of title, status, price, the attars'
    size prices and stock, with keyboard moves, undo and redo, and paste
    from a spreadsheet. Category and position are read-only. One save sends
    every change, all or nothing.
  - **Import and export:** export every product, or the ones a search,
    category and status pick, as a CSV. An import is checked first and shows
    each row as new, changed, unchanged or an error, with before and after.
    Apply saves the whole file or nothing. A change to Never discounted
    needs its own confirmation.
- **Collections:** Attars, Bakhoor, EDP sprays, Gift sets and the
  all-products page. Each opens its name, breadcrumb name and intro, its
  homepage shelf (heading, how many cards, the see-all link), its homepage
  circle (label, colour, picture style) and its products in the shop's
  order, moved up and down. One save writes Site text, Homepage and
  Navigation together. The circle picture is shown without an upload: change
  it under Navigation or Files. Add collection is switched off, because the
  categories are wired into the shop's code.
- **Orders, Customers, Analytics:** shown switched off. They arrive with the
  database.
- **Homepage:** banner slides (text, buttons, links, alt text, and a new
  picture through the crop tool, with one frame for desktop and one for
  phones), each shelf's heading, card count and see-all link, the scent
  families heading, and the product films. A new film is converted in the
  background.
- **Navigation:** the category bar and homepage circles, with a photo or
  cut-out upload for each circle, the phone tab bar and the footer.
- **Site text:** the top strip, the search hint, the homepage strip, the
  scent quiz band, and each collection's name, breadcrumb name and intro.
- **Pages:** the words on the fixed pages, one group at a time: Header and
  footer, Homepage bands, Collection, Product page, Gift box, Bag, Track
  order, Corporate, Account and 404. Each group has a View page link.
  Checkout and Order confirmed are listed as locked: a developer changes
  them in code.
- **Scent quiz:** the questions and their answers (reworded, never added or
  removed: an answer's key joins it to what it looks for), a grid of the
  facets each answer looks for, where a facet can count twice, the result
  profiles as products with their notes and facets, and the words on the
  result and the page. The result takes the matched product's name, price,
  meta line and barcode from the product itself.
- **Translations:** the Arabic the language switch in the top strip puts in
  place of the shop's labels, as one English and Arabic table with search, a
  Missing filter, coverage, add and remove, and a mark on entries whose
  English the built site no longer shows. It also counts each product's
  Arabic name and story, which the shop does not show yet.
- **Files:** every picture and film the site publishes, under Images,
  Category pictures and Films, plus the Trash. Each file shows its size,
  dimensions, where it is used and whether its sized copies are current.
  Files nothing uses come first, with Move to trash; the trash has Restore.
  New banners, logos, the emblem, category photos, cut-outs and films are
  uploaded here. Product photos are added on the product's own page.
- **Discounts:** the bag's volume discount (1 to 4 rungs), the gift box fee
  and discount, and the gift with purchase threshold and label, each with a
  plain preview and a list of what stays in code. The Discount codes card is
  switched off until the database, because codes need orders to check
  against. The gift box card says that its "Add box to bag" button does not
  put the box in the bag.
- **Publish:** what was saved since the last commit, in plain sentences and
  by file, committed once you have read it, after the admin rebuilds the site
  from exactly those files the way both deploys will. Then a check of GitHub
  lists every commit, file and content change a push would send, and pushes
  the reviewed commit when you type PUBLISH. Started with `--no-push`, it
  shows all of that but cannot push. The top bar shows how many saves are
  not committed, or how many commits are not live.
- **History:** every saved version of a product or a page, from the backups
  on this computer and from the repository's commits, compared side by side
  with today's. "Restore this version" saves it like any other change, so a
  restore can itself be undone. The same screen removes backups older than
  a number of days, always keeping each file's newest 50.
- **Settings:** store details, delivery, gift box, volume discount, gift
  with purchase, low stock, brand (with the logo and emblem uploads), search
  and sharing, social links, shopper sign-in (the Auth0 domain and Client
  ID; both empty hide sign-in on the shop), analytics and languages.
  Payments and tax are shown locked.

Every save is checked, written safely and followed by a rebuild of the site,
so the preview shows it at once. If the site would not build with a change,
nothing is kept: every file goes back exactly as it was and the admin says
why. The previous version of each file is kept in `flow/content/.backups/`.

Fields marked "Not on the site yet" are saved, but the shop does not read
them yet.

## What it will not do

- Change payments, tax, cash on delivery or the checkout: locked, a
  developer changes those in code.
- Publish on its own. Saving changes the files on this computer and the
  preview only. Committing and going live are separate clicks on the Publish
  screen, and a push needs the typed word PUBLISH. It never forces, pulls,
  merges or rebases, and its commits hold only the files it manages.
- Run on the internet. There is no login yet, so it only listens on
  127.0.0.1: other machines, even on your Wi-Fi, cannot reach it.

## Safety, in plain words

Only this computer can connect. Every request must come from the admin page
itself, carry a key the server makes fresh each time it starts, and name this
server as its host, so a web page open in another tab cannot use the admin
behind your back. Text cannot contain page code, links must point at pages of
this shop, and the admin never serves or edits the site's code.

## Who may open the admin

Shoppers sign in to the shop with the Auth0 application in
`flow/content/settings.json`. The admin has a **second, separate application**
of its own and its own list of people, so a shopper account is never an admin
account. On this machine the admin opens with no sign-in, as it always has;
it is asked for the moment the admin is served anywhere else, and
`BGS_ADMIN_REQUIRE_LOGIN=1` asks for it here too.

The settings live outside `flow/` (which is published) and outside git, in
`admin/local/admin-auth.json`, or in the environment, which is how a host
sets them:

```json
{
  "domain": "dev-xxxx.us.auth0.com",
  "client_id": "the admin application's Client ID",
  "base_url": "https://admin.example.com",
  "allowed": ["owner@example.com", "staff@example.com"]
}
```

`BGS_ADMIN_AUTH_DOMAIN`, `BGS_ADMIN_AUTH_CLIENT_ID`, `BGS_ADMIN_BASE_URL` and
`BGS_ADMIN_ALLOWED` (addresses separated by commas) say the same thing and
win over the file.

In Auth0, make a second application (Single Page Application) beside the
shop's, and give it the admin's own address:

- **Allowed Callback URLs:** `<base_url>/admin/callback`
- **Allowed Logout URLs:** `<base_url>/admin/`
- **Allowed Web Origins:** `<base_url>`

The admin keeps no client secret: it signs in with the Authorization Code
flow and PKCE, trades the code from the server over TLS, and reads who
signed in from the provider's own `/userinfo`. An address is let in only when
the provider says it is verified and the list holds it, whatever else the
account may be. The signed-in browser holds one cookie, signed with
`admin/local/session-key` (made on demand, `0600`), HttpOnly, SameSite=Lax
and Secure over https, good for twelve hours. It does not replace the
per-run token or the Origin checks: an API call still carries both, so a
signed-in person on another site still cannot drive the admin.

`/admin/signout` drops the cookie and ends the session at the provider.
Removing an address from `allowed` shuts that person out at their next
sign-in; deleting `admin/local/session-key` signs everyone out at once.

## Database

The admin can keep its content in PostgreSQL instead of the JSON files.
`admin/dbtool.py` makes the admin's tables in your database, loads
`flow/content` into them, checks that the two agree and switches this
checkout to the database. dbtool, and the admin on the database, need
psycopg, which the admin's own virtualenv has (`admin/requirements.txt` says
how it is made). Run each line from the repository root, with the admin
stopped:

```bash
# Once, recommended, as your own superuser role: the admin's own role, which may change content and nothing else.
/opt/homebrew/bin/psql -X -h /tmp -p 5432 -U ajoomama -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE bgs_corner_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10"

# A dry run: everything happens in one transaction, which is then rolled back.
admin/.venv/bin/python admin/dbtool.py migrate --dsn "host=/tmp port=5432 dbname=bgs_corner user=bgs_corner"

# The same, committed. It also switches this checkout to the database (admin/local/store.json).
admin/.venv/bin/python admin/dbtool.py migrate --dsn "host=/tmp port=5432 dbname=bgs_corner user=bgs_corner" --apply

# Read-only, safe at any time.
admin/.venv/bin/python admin/dbtool.py verify

# The admin, on the database.
admin/.venv/bin/python admin/server.py

# Back to the JSON files, which are current after every save ("use postgres" returns).
# Saves made on the files cannot go back to the database yet: before "use postgres",
# put each file you saved back (git checkout -- flow/content/<name>.json) and press Rebuild now.
admin/.venv/bin/python admin/dbtool.py use json
```

`migrate` applies the numbered files in `admin/bgsadmin/db/migrations/` the
database lacks, each with its row in `bgs.schema_migrations`, and binds the
database to this checkout: dbtool and the admin refuse any other. Into an
empty database it loads every content file one row at a time, listing every
row the database refuses and why. Then it compares what the database gives
back with the files: the same data for every file, and the same bytes for
every file already in canonical form (`home.json` is written by hand today,
so it shows as "formatting only"). It builds the site from the database's
export in a copy of `flow/` and compares every generated file. It commits
only with `--apply`, and only when nothing was refused or different. Run
again once the content is in, it has nothing to do.

`verify` prints the schema, the checkout the database belongs to, whether
every check and trigger is on, whether the admin's role has exactly its
rights, and for each content file its sha, the export's sha and its state:
in sync, changed in the file, changed in the database, changed in both, or
missing. Row counts and the newest revision follow.

On the database, every save writes the database first and then the files,
so `flow/content` always holds the database's export and git, History and
the Publish screen work as before. A file changed outside the admin (by hand
or by git) is not taken into the database yet: the home screen lists it, and
a save that would write it answers that it was changed outside the admin
until you put it back (`git checkout -- flow/content/<name>.json`). The admin
runs as `bgs_corner_app` once that role exists; until then it runs as the
database's owner and says so when it starts. If you create the role later,
run the `--apply` line again: it applies nothing new and switches the admin
to the role.

Both exit with 0 when all is well, 1 with the list of differences or
refusals, 2 when they refuse to run (a DSN with a password, a superuser,
another checkout's database, an admin running) and 3 when PostgreSQL is not
answering. A DSN names the socket folder, the port, the database and the
user, and never a password: the server trusts its own socket, and a
password belongs in `~/.pgpass`.

## Tests

Each test file starts its own admin on a temporary clone of the repository,
on its own port and with `--no-push`, so it never touches your content. Run
one file per command, from the repository root, like this:

```bash
ADMIN_RULES_PORT=4741 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_rules.py'
```

Use that `discover -p` form for every file. The files load `box.py` from
their own folder, so `python3 -m unittest admin/tests/test_rules.py` cannot
import them, and `test_bulk_ui.py` and `test_publish.py` do nothing when run
as scripts.

The port variable is optional: each file has its own default. Keep test
ports between 4700 and 4799; 4310 is your preview.

| File | What it covers | Port variable | Default |
|---|---|---|---|
| `test_admin.py` | The server end to end: the security gate, products, documents, saves and rollback | `ADMIN_TEST_PORT` | 4731 |
| `test_plumbing.py` | Raw-body uploads, non-JSON responses and background jobs, on a bare server; nothing secret in git; JSON mode loads no database driver; a test run that dies of the alarm or a kill leaves no server behind | `ADMIN_PLUMBING_PORT` and `ADMIN_PLUMBING_BOX_PORT` | 4732 and 4733 |
| `test_store.py` | The JSON store on a copy of the content, no server: the export, one rev function, the journal and recovery after a crash, the admin lock, busy, confirmed guarded changes | none | none |
| `test_rules.py` | The store rules reach the page text and `BGS_RULES`, bad rules are refused, COD and VAT stay locked | `ADMIN_RULES_PORT` | 4741 |
| `test_collections.py` | Collections: category text, homepage shelves, one save across three files | `ADMIN_COLLECTIONS_PORT` | 4742 |
| `test_pages.py` | Page text reaches the pages and `BGS_COPY`, and bad text is refused | `ADMIN_PAGES_PORT` and `ADMIN_PAGES2_PORT` | 4743 and 4744 |
| `test_translations.py` | The Arabic dictionary and its field type | `ADMIN_TRANSLATIONS_PORT` | 4751 |
| `test_quiz.py` | The scent quiz document and what a save does to `quiz.html` | `ADMIN_QUIZ_PORT` | 4752 |
| `test_media.py` | Uploads, attaching, the library and the trash; needs ffmpeg and ffprobe | `ADMIN_MEDIA_PORT` | 4761 |
| `test_bulk.py` | Bulk saves and the product CSV | `ADMIN_BULK_PORT` | 4771 |
| `test_bulk_screens.py` | The Inventory, Bulk editor and Import and export screens as rendered; needs Chrome | `ADMIN_BULK_UI_PORT` | 4772 |
| `test_bulk_ui.py` | The same three screens driven in headless Chrome; needs Chrome | `ADMIN_BULK_DRIVE_PORT` | 4773 |
| `test_history.py` | History, the sentences that describe a change, and restore | `ADMIN_HISTORY_PORT` | 4781 |
| `test_publish.py` | Review, commit and go live, against throwaway repositories with a temporary bare remote | `ADMIN_PUBLISH_PORT` | 4782 |
| `test_bag_path.py` | The storefront's way to checkout: the panel after Add to bag on a phone and a desktop, and the bag page's checkout bar; needs Chrome | `ADMIN_BAG_PATH_PORT` | 4791 |
| `test_signin.py` | Shopper sign-in against a stand-in for Auth0 on a phone and a desktop: the account page's panel, Sign in and Create account, refused callbacks, an expired profile, Sign out, the header and tab bar, the Settings fields, and the GitHub Pages, Netlify and bgscorner.com addresses against the lists in Auth0; needs Chrome | `ADMIN_SIGNIN_PORT` and `ADMIN_SIGNIN_OIDC_PORT` | 4792 and 4793 |
| `test_phone_layout.py` | The storefront on phones and other touch screens: the notch, type on the big landscape phones, Arabic word order, the masthead, the buy bar and the bag at 200% text; needs Chrome | `ADMIN_PHONE_LAYOUT_PORT` | 4792 |
| `test_adminauth.py` | Who may open the admin: the admin opens with no sign-in on this machine; with one asked for, the round trip to the stand-in provider, the list of people, a refused sign-in, a changed, stale or foreign cookie, that a signed-in browser still needs the admin's token, signing out, the settings the admin refuses and the admin refusing to start without them | `ADMIN_ADMINAUTH_PORT` (and the next) | 4746 |
| `test_dbschema.py` | The throwaway PostgreSQL clusters (private, no TCP, the owner's roles and database rights, nothing left after a failure, the alarm or a kill); the migrations through `dbtool migrate` and `verify`; the writes the database refuses by itself, as the owner and as the admin's role; dump and restore; exact round trips; what the database says about a save that died while committing. Needs PostgreSQL's programs, no admin server; everything past the clusters needs psycopg (`admin/.venv/bin/python`) | `ADMIN_PG_PORT` (and the next port) | 5453 |
| `test_pgstore.py` | The PostgreSQL store itself: reads and revs, a save's order, the database's refusals behind the admin's, busy, one admin per checkout and per database, the saves a crash cut short, files changed outside the admin, a database changed in psql, a missing file, the start refusals and start lines, dbtool use. Always PostgreSQL; needs psycopg (`admin/.venv/bin/python`) | `ADMIN_PGSTORE_PORT` (and the next port), `ADMIN_PG_PORT` | 4745 and 5453 |

The Chrome files and tests are skipped when Chrome is not installed. Helpers:
`box.py` (the temporary clone and its server), `cdp_pipe.py` (headless
Chrome over its DevTools pipe, standard library only), `fake_oidc.py` (a
stand-in for Auth0 on 127.0.0.1, for `test_signin.py`), `cleanup.py` (the
exit nets: however a run ends, the 110 s alarm and a kill included, the
servers and clusters it started stop and their folders go) and
`pgcluster.py` (throwaway PostgreSQL clusters, driven through psql).

`ADMIN_TEST_STORE` says which store the test servers run on: `json`, the
default, or `postgres`, which gives each test server a database of its own
on a throwaway cluster, made by `dbtool migrate --apply` on its clone. Run
PostgreSQL mode with the admin's virtualenv:

```bash
ADMIN_TEST_STORE=postgres ADMIN_TEST_PORT=4731 admin/.venv/bin/python -m unittest discover -s admin/tests -p 'test_admin.py'
```

test_admin, test_rules, test_collections, test_pages, test_translations,
test_quiz, test_media, test_bulk and test_history run on both stores.
test_dbschema and test_pgstore always use PostgreSQL and need psycopg. The
cluster tests read
`ADMIN_PG_PORT` (it only names the socket file: the clusters have no TCP),
`ADMIN_PG_ROOT` (where the cluster folders go, the system's temporary folder
unless set; macOS allows a socket path of 103 bytes, so keep it short) and
`ADMIN_PG_BIN` (`/opt/homebrew/bin`). No test uses the shared server or its
`bgs_corner` database.

## Developer tools

- `admin/devtools/compare_build.py [BASE]`: compares the generated files of
  this working tree with a base revision's, after dropping `?v=` tokens and
  decoding HTML entities, and lists any window global that was added or
  changed. Run `build.py` in `flow/` first.
- `admin/devtools/dom_diff.py --base REV --ports A,B`: renders the pages of
  both in headless Chrome after their scripts run and compares what a
  visitor gets.
- `admin/devtools/viewport_audit.py`: the storefront at 28 screen sizes
  (portrait and landscape phones, the fold closed and open, tablets,
  desktops, ultrawide) and 29 page states (every page, each category, a
  search, the filter drawer, five product pages and one just after Add to
  bag, the bag empty, with one line and with five, the quiz and its result,
  and index, product and bag in Arabic), in headless Chrome with phones and
  tablets emulated as touch screens. `list` shows the matrix. `run` serves
  a checkout and works through the jobs in batches that fit a two-minute
  limit; repeat the same command until it exits 0 (3 means jobs remain):

  ```bash
  perl -e 'alarm shift; exec @ARGV' 110 /usr/bin/python3 admin/devtools/viewport_audit.py run \
      --clone /path/to/checkout --port 4970 --out /tmp/va
  ```

  `--viewports` and `--pages` take sets and names (`phones`, `landscape`,
  `tablets`, `desktops`, `touch`; `pdp`, `cart`, `coll`, `ar`, or one state
  like `cart-1`), `--redo` runs a selection again. Each job saves its
  measurements and a first-screen screenshot; `report --out /tmp/va`
  rebuilds `report.txt` (issues by type and element: sideways scrolling,
  text under 12px, fields under 16px, tap targets under 44px, bars' share of
  the screen, covered actions, the bag's Checkout, pictures, clipped or
  overlapping text, lost spaces, wrapping labels, the tab bar, the language
  toggle, Arabic order and arrows, script errors), `matrix.txt` and
  `checkout.txt`. The file's docstring has every option.

More: `DESIGN.md` (decisions), `docs/PLAN.md` (architecture),
`docs/HARDCODED.md` (what is still typed into the code),
`docs/CONTENT-MODEL.md` (every content file and key).
