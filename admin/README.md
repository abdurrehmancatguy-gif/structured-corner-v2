# BGS Corner admin

A back office for the storefront in `flow/`, run on your own computer.

## Open it

```bash
python3 admin/server.py
```

Then go to http://localhost:4310/admin/ (the store itself is at
http://localhost:4310/). The preview configuration's `python3 flow/server.py
4310` starts the same server.

## What it does now

- **Products:** list, search, filter, reorder within a category, add (as a
  draft), duplicate, delete, and edit every field: title, story, prices and
  sizes, stock, status, category, scent notes, ingredients, barcode, and the
  fields kept for later (Arabic, SEO, related products and the rest).
- **Homepage:** banner slides (text, buttons, links, alt text), the product
  films, section headings.
- **Navigation:** the category bar and homepage circles, the phone tab bar,
  the footer.
- **Site text** and **Settings** (store details, delivery and gift box rules,
  brand text, social links).
- **Translations:** the Arabic the language switch in the top strip puts in
  place of the shop's labels, as one English and Arabic table with search, a
  Missing filter, coverage, add and remove, and a mark on entries whose
  English the built site no longer shows. It also counts each product's
  Arabic name and story, which the shop does not show yet.

Every save is checked, written safely and followed by a rebuild of the site,
so the preview shows it at once. If the site would not build with a change,
nothing is kept: every file goes back exactly as it was and the admin says
why. The previous version of each file is kept in `flow/content/.backups/`.

Fields marked "Not on the site yet" are saved but the shop does not read them
yet; the next stage wires them in.

## What it will not do

- Change payments, tax, cash on delivery or the checkout: locked, a
  developer changes those in code.
- Publish. Saving changes the files on this computer and the preview only.
  Going live is still a commit and a push, which the Publish screen will do
  with your confirmation in a later stage.
- Run on the internet. There is no login yet, so it only listens on
  127.0.0.1: other machines, even on your Wi-Fi, cannot reach it.

## Safety, in plain words

Only this computer can connect. Every request must come from the admin page
itself, carry a key the server makes fresh each time it starts, and name this
server as its host, so a web page open in another tab cannot use the admin
behind your back. Text cannot contain page code, links must point at pages of
this shop, and the admin never serves or edits the site's code.

## Tests

```bash
/usr/bin/python3 -m unittest discover -s admin/tests
```

They run against a temporary copy of the repository, on port 4731, and never
touch your content.

More: `DESIGN.md` (decisions), `docs/PLAN.md` (architecture).
