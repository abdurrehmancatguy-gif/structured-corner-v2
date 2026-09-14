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
  and sharing, social links, analytics and languages. Payments and tax are
  shown locked.

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
| `test_plumbing.py` | Raw-body uploads, non-JSON responses and background jobs, on a bare server | `ADMIN_PLUMBING_PORT` | 4732 |
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

The three Chrome files are skipped when Chrome is not installed. Helpers:
`box.py` (the temporary clone and its server) and `cdp_pipe.py` (headless
Chrome over its DevTools pipe, standard library only).

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
