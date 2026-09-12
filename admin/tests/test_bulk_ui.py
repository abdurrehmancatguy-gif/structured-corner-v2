"""The Inventory, Bulk editor and Import and export screens driven in headless
Chrome, each test on a fresh temporary clone: typing, the grid's keys,
pastes, saves, a 412 with Reload row, and the import's check, confirmation
and apply. Keys go through Chrome's input pipeline; clicks run as script.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_bulk_ui.py'
"""
import csv
import io
import json
import os
import time
import unittest

from box import Box
import cdp_pipe

PORT = int(os.environ.get("ADMIN_BULK_DRIVE_PORT", "4773"))
J = json.dumps


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class Driven(unittest.TestCase):
    def setUp(self):
        self.b = Box(PORT)
        self.c = cdp_pipe.Chrome()

    def tearDown(self):
        self.c.close()
        self.b.close()

    # ---- helpers -----------------------------------------------------------
    def open(self, address, ready):
        self.c.go("http://localhost:%d/admin/%s" % (PORT, address))
        self.c.wait(ready, 25)

    def js(self, expr):
        return self.c.js(expr)

    def click(self, sel, text=None):
        done = self.js("(() => { const els = [...document.querySelectorAll(%s)].filter(e => !%s || e.textContent.trim().startsWith(%s));"
                       " if (!els.length) return false; els[0].click(); return true; })()" % (J(sel), J(text), J(text)))
        self.assertTrue(done, "nothing to click: %s %s" % (sel, text or ""))

    def setval(self, sel, value, ev="input"):
        self.js("(() => { const e = document.querySelector(%s); e.value = %s; e.dispatchEvent(new Event(%s, {bubbles: true})); })()"
                % (J(sel), J(value), J(ev)))

    def texts(self, sel):
        return self.js("[...document.querySelectorAll(%s)].map(e => e.textContent)" % J(sel))

    def has(self, sel, words):
        return any(words in t for t in self.texts(sel))

    def wait_text(self, sel, words, timeout=30):
        self.c.wait("[...document.querySelectorAll(%s)].some(e => e.textContent.includes(%s))" % (J(sel), J(words)),
                    timeout, what="%s saying %r" % (sel, words))

    def product(self, pid):
        return self.b.content("products")[pid]

    def bump(self, pid, **fields):
        """Saves a change to one product, as a save from elsewhere would."""
        st, cur = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200)
        st, res = self.b.api("POST", "products/bulk", {"changes": [{"id": pid, "rev": cur["rev"], "data": dict(cur["data"], **fields)}]})
        self.assertEqual(st, 200, res)

    def no_page_errors(self):
        self.assertEqual(self.c.errors(), [], "the page threw or logged an error")

    # ---- inventory ---------------------------------------------------------
    def test_inventory_edits_saves_and_reloads_a_stale_row(self):
        self.open("#/inventory", "document.querySelectorAll('.inv-stock').length > 0")
        rows = lambda: self.js("document.querySelectorAll('.inv-stock').length")
        tracked = [k for k, d in self.b.content("products").items() if d.get("stock") is not None]
        self.assertEqual(rows(), len(tracked))
        self.js("document.getElementById('inv-low').click()")
        self.assertEqual(rows(), sum(1 for k in tracked if self.product(k)["stock"] <= 5))
        self.js("document.getElementById('inv-low').click()")

        def typein(pid, s):
            self.js("(() => { const e = document.getElementById(%s); e.focus(); e.select(); })()" % J("inv-" + pid))
            self.c.type(s)

        typein("be-mine", "12")
        self.assertTrue(self.js("document.getElementById('inv-be-mine').closest('tr').classList.contains('changed')"))
        self.assertTrue(self.has(".savebar", "1 unsaved change"))
        typein("vibe", "x")
        self.assertTrue(self.has("#inv-vibe-msg", "Enter a whole number."))
        self.c.key("s", ["ctrl"])
        self.wait_text(".banner", "to fix first")
        self.assertEqual(self.product("be-mine")["stock"], 8)
        self.js("document.getElementById('inv-vibe').focus()")
        self.c.key("Escape")
        self.assertEqual(self.js("document.getElementById('inv-vibe').value"), "10")
        self.js("document.getElementById('inv-be-mine').focus()")
        self.c.key("Enter")
        self.assertEqual(self.js("document.activeElement.id"), "inv-vibe")

        # One save elsewhere to the same stock, one to another field.
        self.bump("pride-of-arabia", stock=9)
        self.bump("amore", price=86)
        typein("pride-of-arabia", "7")
        typein("amore", "14")
        self.click(".savebar button", "Save")
        self.wait_text(".banner", "changed since this screen opened")
        self.assertEqual(self.product("be-mine")["stock"], 8, "a 412 saves nothing")
        self.assertEqual(len(self.texts(".inv-stale")), 2)
        self.click("button[aria-label='Reload Pride of Arabia']")
        self.wait_text(".toast", "Your number was dropped")
        self.assertEqual(self.js("document.getElementById('inv-pride-of-arabia').value"), "9")
        self.click("button[aria-label='Reload Amore']")
        self.wait_text(".toast", "Your number is kept")
        self.assertEqual(self.js("document.getElementById('inv-amore').value"), "14")
        self.assertFalse(self.has(".banner", "changed since this screen opened"), "the 412 banner goes with the last stale row")
        self.click(".savebar button", "Save")
        self.wait_text(".toast", "Saved the stock of 2 products")
        p = self.b.content("products")
        self.assertEqual((p["be-mine"]["stock"], p["amore"]["stock"], p["amore"]["price"], p["pride-of-arabia"]["stock"]), (12, 14, 86, 9))
        self.assertTrue(self.js("document.querySelector('.savebar').hidden"))

        # Leaving with a change asks first.
        typein("vibe", "11")
        self.js("location.hash = '#/bulk'")
        self.c.wait("!!document.querySelector('dialog[open]')", 10, "the leave dialog")
        self.assertTrue(self.has("dialog[open]", "Leave without saving?"))
        self.click("dialog[open] button", "Stay")
        self.assertEqual(self.js("location.hash"), "#/inventory")
        self.no_page_errors()

    # ---- bulk editor -------------------------------------------------------
    def test_bulk_editor_keys_paste_undo_and_a_stale_row(self):
        self.open("#/bulk", "document.querySelectorAll('[role=gridcell]').length > 0")
        c = self.c
        cell = lambda r, k: "document.querySelector('[data-r=\"%d\"][data-c=\"%d\"]')" % (r, k)
        val = lambda r, k: self.js("(() => { const e = %s.querySelector('.g-val, .badge'); return e ? e.textContent : '' })()" % cell(r, k))
        cls = lambda r, k: self.js("%s.className" % cell(r, k))
        at = lambda: self.js("(() => { const a = document.activeElement; return a.dataset && a.dataset.r !== undefined"
                             " ? [Number(a.dataset.r), Number(a.dataset.c)] : a.tagName })()")
        btn = lambda: self.js("document.querySelector('.head-actions .btn.primary').textContent")
        heads = lambda: self.js("document.querySelectorAll('[role=rowheader]').length")
        status = lambda: self.js("document.querySelector('.bulk-status').textContent")
        row_of = lambda pid: self.js("[...document.querySelectorAll('[role=rowheader]')].findIndex(e => e.textContent.includes(%s))" % J(pid))
        col_of = lambda label: self.js("[...document.querySelectorAll('[role=columnheader]')].findIndex(e => e.textContent === %s)" % J(label))

        def paste(text):
            self.js("(() => { const dt = new DataTransfer(); dt.setData('text/plain', %s); document.activeElement.dispatchEvent("
                    "new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); })()" % J(text))

        products = self.b.content("products")
        self.assertEqual(heads(), len(products))
        self.assertEqual([row_of(x) for x in ("be-mine", "vibe", "pride-of-arabia", "suit-up")], [0, 1, 2, 3],
                         "this test expects the shop's first four products in this order")
        P, S1, S2, ST = (col_of(x) for x in ("Price (AED)", "Size 1 (AED)", "Size 2 (AED)", "Stock"))
        self.assertEqual(self.js("getComputedStyle(document.querySelector('.g-h')).position"), "sticky")
        self.assertEqual(self.js("getComputedStyle(%s).position" % cell(0, 0)), "sticky")

        # Arrows, Enter to edit and commit, F2 and Esc to cancel, typing to
        # start an edit, Tab, Esc to put a cell back, undo and redo.
        self.js("%s.focus()" % cell(0, 0))
        for _ in range(P):
            c.key("ArrowRight")
        self.assertEqual(at(), [0, P])
        c.key("Enter")
        self.assertEqual((at(), self.js("document.activeElement.value")), ("INPUT", "85"))
        c.type("90")
        c.key("Enter")
        self.assertEqual((at(), btn()), ([1, P], "Save 1 change"))
        self.assertIn("changed", cls(0, P))
        c.key("F2")
        c.type("1")
        c.key("Escape")
        self.assertEqual((at(), val(1, P)), ([1, P], "85"))
        c.type("95")
        c.key("Tab")
        self.assertEqual((at(), val(1, P), btn()), ([1, P + 1], "95", "Save 2 changes"))
        c.key("ArrowLeft")
        c.key("Escape")
        self.assertEqual((val(1, P), btn()), ("85", "Save 1 change"))
        c.key("z", ["ctrl"])
        self.assertEqual(val(1, P), "95")
        c.key("z", ["ctrl"])
        c.key("z", ["ctrl"])
        self.assertEqual((val(0, P), btn()), ("85", "Save changes"))
        c.key("z", ["ctrl", "shift"])
        self.assertEqual((val(0, P), btn()), ("90", "Save 1 change"))

        # Pastes: an attar's price and sizes (45 is its saved Size 1, so not a
        # change), a column with a bad value, a row over cells not used.
        ic = row_of("imperial-crown")
        self.js("%s.focus()" % cell(ic, P))
        paste("45\t45\t80\n")
        self.assertEqual([val(ic, P), val(ic, S1), val(ic, S2)], ["45", "45", "80"])
        self.assertTrue(status().startswith("Pasted 3 cells."), status())
        self.js("%s.focus()" % cell(2, ST))
        paste("7\nabc\n")
        self.assertEqual(val(2, ST), "7")
        self.assertIn("invalid", cls(3, ST))
        self.assertTrue(self.has("#g-err-suit-up-stock", "Enter a whole number."))
        self.js("%s.focus()" % cell(0, S1))
        paste("5\t6\t7")
        self.assertEqual(val(0, ST), "7")
        self.assertIn("2 cells skipped", status())
        self.click(".head-actions .btn.primary")
        self.wait_text(".banner", "to fix first")
        self.assertEqual(at(), [3, ST], "a refused save points at the bad cell")
        c.key("Escape")
        self.assertNotIn("invalid", cls(3, ST))
        self.js("%s.focus()" % cell(ic, P))
        c.type("50")
        c.key("Enter")
        self.assertTrue(self.has("#g-err-imperial-crown-price", "one of the sizes"))
        c.key("ArrowUp")
        c.key("z", ["ctrl"])
        self.assertEqual(val(ic, P), "45")
        self.assertFalse(self.has("#g-err-imperial-crown-price", "sizes"))

        # Filters hide rows and keep their changes.
        self.setval(".card select[aria-label=Category]", "attars", "change")
        self.assertEqual(heads(), sum(1 for d in products.values() if d["category"] == "attars"))
        self.setval(".card input[type=search]", "musk")
        self.assertEqual(heads(), sum(1 for k, d in products.items() if d["category"] == "attars" and "musk" in k))
        self.setval(".card input[type=search]", "")
        self.setval(".card select[aria-label=Category]", "", "change")
        self.assertEqual((heads(), btn()), (len(products), "Save 5 changes"))

        # Vibe changes elsewhere: a 412, Reload, then the save.
        self.bump("vibe", price=87)
        self.js("%s.focus()" % cell(1, P))
        c.type("88")
        c.key("Enter")
        self.click(".head-actions .btn.primary")
        self.wait_text(".bulk-stale .banner", "changed since this screen opened")
        self.assertEqual(self.product("be-mine")["price"], 85, "a 412 saves nothing")
        self.assertTrue(self.js("%s.closest('tr').classList.contains('stale')" % cell(1, 0)))
        self.assertTrue(self.has("th .g-stale", "Reload row"))
        self.click(".bulk-stale button", "Reload Vibe")
        self.wait_text(".toast", "was dropped")
        self.assertEqual(val(1, P), "87")
        self.assertFalse(self.js("!!document.querySelector('.bulk-stale .banner')"))
        self.click(".head-actions .btn.primary")
        self.wait_text(".toast", "Saved 5 changes to 3 products")
        p = self.b.content("products")
        self.assertEqual((p["be-mine"]["price"], p["be-mine"]["stock"], p["pride-of-arabia"]["stock"], p["vibe"]["price"]), (90, 7, 7, 87))
        self.assertEqual((p["imperial-crown"]["price"], [s["price"] for s in p["imperial-crown"]["sizes"]]), (45, [45, 80]))
        self.assertEqual(btn(), "Save changes")
        self.no_page_errors()

    # ---- import and export -------------------------------------------------
    def download(self, label):
        """Clicks an export button and returns the file's bytes and rows. Each
        file is removed once read, so the next, with the same name, is new."""
        self.click(".imp-actions button", label)
        end = time.monotonic() + 20
        while time.monotonic() < end:
            names = os.listdir(self.c.downloads)
            done = [n for n in names if n.endswith(".csv")]
            if done and not any(n.endswith(".crdownload") for n in names):
                path = os.path.join(self.c.downloads, done[0])
                with open(path, "rb") as fh:
                    raw = fh.read()
                os.remove(path)
                return raw, list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
            time.sleep(0.2)
        self.fail("no file from " + label)

    def choose(self, rows, name, changes=None):
        """Picks a CSV file built from rows, with {(handle, column): value} changed."""
        col = {k: i for i, k in enumerate(rows[0])}
        out = [list(r) for r in rows]
        for r in out[1:]:
            for (pid, k), v in (changes or {}).items():
                if r[0] == pid:
                    r[col[k]] = v
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\r\n").writerows(out)
        self.js("(() => { const i = document.getElementById('imp-file'); const dt = new DataTransfer();"
                " dt.items.add(new File([%s], %s, {type: 'text/csv'})); i.files = dt.files;"
                " i.dispatchEvent(new Event('change', {bubbles: true})); })()" % (J(chr(0xFEFF) + buf.getvalue()), J(name)))
        self.wait_text(".imp-checked", name)
        return self.js("document.querySelector('.imp-checked').textContent")

    def test_import_checks_confirms_applies_and_rechecks(self):
        self.open("#/import", "document.body.textContent.includes('products in all')")
        n = len(self.b.content("products"))
        raw, rows = self.download("Export all products")
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw)
        self.assertEqual((len(rows), rows[0][0]), (n + 1, "Handle"))
        self.setval("select[aria-label=Category]", "bakhoor", "change")
        _, some = self.download("Export these")
        self.assertTrue(len(some) > 1 and all(self.product(r[0])["category"] == "bakhoor" for r in some[1:]))
        self.setval("select[aria-label=Category]", "", "change")

        # A price and a Never discounted change: reviewed, confirmed on their
        # own, applied.
        said = self.choose(rows, "edited.csv", {("be-mine", "Price"): "88", ("vibe", "Never discounted"): "TRUE"})
        self.assertIn("0 to create, 2 to change, %d unchanged, 0 errors" % (n - 2), said)
        self.assertEqual(self.js("document.querySelector('[aria-current=step]').textContent"), "Apply or cancel")
        self.click(".imp-filters button", "To change")
        self.assertEqual(self.js("document.querySelectorAll('.imp-table > tbody > tr').length"), 2)
        diffs = self.texts(".imp-changes tbody tr")
        self.assertTrue(any(d.startswith("Price") and "85" in d and "88" in d for d in diffs), diffs)
        self.assertIn("Never discountedoffon", diffs)
        self.assertTrue(self.has(".imp-table", "Asks first"))
        self.click(".imp-apply button.primary")
        self.c.wait("!!document.querySelector('dialog[open]')", 10, "the confirm dialog")
        self.assertTrue(self.has("dialog[open] h2", "Confirm Never discounted for 1 product"))
        self.assertTrue(self.has("dialog[open]", "Vibe: Never discounted from off to on"))
        self.click("dialog[open] button", "Back to the check")
        self.assertEqual((self.product("be-mine")["price"], self.product("vibe")["never_discount"]), (85, False))
        self.click(".imp-apply button.primary")
        self.c.wait("!!document.querySelector('dialog[open]')", 10, "the confirm dialog")
        self.click("dialog[open] button", "Confirm")
        self.wait_text(".banner", "Imported: 2 products changed.")
        self.assertEqual((self.product("be-mine")["price"], self.product("vibe")["never_discount"]), (88, True))

        # A file with an error cannot be applied.
        said = self.choose(rows, "bad.csv", {("amore", "Price"): "abc"})
        self.assertIn("1 error", said)
        self.assertTrue(self.has(".imp-filters [aria-pressed=true]", "Errors"))
        self.assertTrue(self.has(".imp-errors", "Price"))
        self.assertFalse(self.js("!!document.querySelector('.imp-apply button.primary')"))
        self.click(".imp-apply button", "Choose another file")

        # Cancel, after the guard on leaving.
        _, now = self.download("Export all products")
        self.choose(now, "cancel.csv", {("amore", "Price"): "86"})
        self.js("location.hash = '#/bulk'")
        self.c.wait("!!document.querySelector('dialog[open]')", 10, "the leave dialog")
        self.click("dialog[open] button", "Stay")
        self.click(".imp-apply button", "Cancel")
        self.assertTrue(self.js("!!document.getElementById('imp-file')"))
        self.assertEqual(self.product("amore")["price"], 85)

        # Products change between the check and the apply: the second check
        # shows that the file would put back the stock saved in between.
        self.choose(now, "late.csv", {("amore", "Price"): "86"})
        self.bump("suit-up", stock=5)
        self.click(".imp-apply button.primary")
        self.wait_text(".banner", "Products changed since the file was checked.")
        self.assertEqual(self.product("amore")["price"], 85)
        self.click(".banner button", "Check the file again")
        self.wait_text(".imp-checked", "2 to change")
        self.assertTrue(any(d.startswith("Stock") and "5" in d and "4" in d for d in self.texts(".imp-changes tbody tr")))
        self.click(".imp-apply button.primary")
        self.wait_text(".banner", "Imported: 2 products changed.")
        self.assertEqual((self.product("amore")["price"], self.product("suit-up")["stock"]), (86, 4))
        self.no_page_errors()

    # ---- phone width -------------------------------------------------------
    def test_no_screen_scrolls_sideways_on_a_phone(self):
        self.open("#/inventory", "document.querySelectorAll('.inv-stock').length > 0")
        for width in (390, 1280):
            self.c.size(width, 844)
            for address, ready in (("#/inventory", ".inv-stock"), ("#/bulk", "[role=gridcell]"), ("#/import", "#imp-file"),
                                   ("#/content/quiz", ".qz-grid"), ("#/content/translations", ".tr-table"),
                                   ("#/collections/attars", ".t-name")):
                self.js("location.hash = %s" % J(address))
                self.c.wait("location.hash === %s && !!document.querySelector(%s)" % (J(address), J(ready)), 20)
                self.js("new Promise(r => setTimeout(r, 200))")
                page, view = self.js("[document.documentElement.scrollWidth, window.innerWidth]")
                self.assertLessEqual(page, view, "%s at %d wide scrolls sideways" % (address, width))
                if address == "#/bulk" and width == 390:
                    self.assertTrue(self.js("(() => { const e = document.querySelector('.bulk-wrap'); return e.scrollWidth > e.clientWidth; })()"),
                                    "the grid scrolls inside its own box")
        self.no_page_errors()
