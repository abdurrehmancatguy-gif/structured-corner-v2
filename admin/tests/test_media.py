"""Uploads end to end: staging, attaching, the library and the trash, against
a temporary clone. Pictures are drawn with Pillow here and the film is made
with ffmpeg's test pattern, so the tests carry no media files of their own.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_media.py'
"""
import http.client
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import zlib

from PIL import Image, ImageDraw

from box import Box

PORT = int(os.environ.get("ADMIN_MEDIA_PORT", "4761"))
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def jpeg(w, h, exif=None, colour=(190, 120, 50)):
    im = Image.new("RGB", (w, h), colour)
    ImageDraw.Draw(im).ellipse((w // 5, h // 5, w * 4 // 5, h * 4 // 5), fill=(30, 60, 190))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def cutout(w=600, h=800):
    """An object on a transparent ground, clear of every edge (the rule is 90%
    of the border see-through)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((w // 4, h // 8, w * 3 // 4, h - 40), fill=(170, 130, 60, 255))
    return png(im)


def png_header(w, h):
    """A PNG that says it is w x h but carries almost no data: what a
    decompression bomb or an oversized picture looks like before decoding."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 1000)) + chunk(b"IEND", b""))


def exif_with_gps():
    ex = Image.Exif()
    ex[0x010F] = "PhoneMakerTest"
    gps = ex.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (25.0, 12.0, 30.0)
    return ex.tobytes()


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.flow = cls.b.repo / "flow"

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def stage(self, kind, data, ctype):
        return self.b.api("POST", "media/staging?kind=" + kind, data, ctype=ctype)

    def attach(self, sid, rev, target):
        return self.b.api("POST", "media/attach", {"staging_id": sid, "expect_rev": rev, "target": target})

    def headers_only(self, path, ctype, length):
        """Declare a body without sending it: the server must refuse it on
        its headers alone."""
        c = http.client.HTTPConnection("127.0.0.1", self.b.port, timeout=30)
        c.putrequest("POST", "/admin/api/v1/" + path, skip_host=True, skip_accept_encoding=True)
        for k, v in (("Host", "localhost:%d" % self.b.port), ("X-Admin-Token", self.b.token),
                     ("Origin", "http://localhost:%d" % self.b.port), ("Content-Type", ctype),
                     ("Content-Length", str(length))):
            c.putheader(k, v)
        c.endheaders()
        r = c.getresponse()
        out = r.status, json.loads(r.read() or b"{}")
        c.close()
        return out

    def img_files(self):
        return set(os.listdir(str(self.flow / "assets" / "img")))

    # ---- product frames ------------------------------------------------------

    def test_frame_upload_and_attach(self):
        b = self.b
        st, res = self.stage("product-image", jpeg(1400, 1100, exif_with_gps()), "image/jpeg")
        self.assertEqual(st, 201, res)
        self.assertEqual((res["width"], res["height"]), (1400, 1100))
        sid = res["staging_id"]
        st, prod = b.api("GET", "products/vibe")
        before = list(prod["data"]["images"])
        st, res = self.attach(sid, prod["rev"], {"kind": "product-image", "product": "vibe", "position": 1})
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        name = res["data"]["images"][1]
        self.assertRegex(name, r"^vibe-\d+\.jpg$")
        self.assertNotIn(name, before)
        self.assertEqual(b.content("products")["vibe"]["images"], before[:1] + [name] + before[1:])
        stem = name[:-4]
        for suf in ("", "-card", "-600", "-card-360", "-thumb"):
            self.assertTrue((self.flow / "assets" / "img" / (stem + suf + ".jpg")).is_file(), suf)
        raw = (self.flow / "assets" / "img" / name).read_bytes()
        with Image.open(io.BytesIO(raw)) as im:
            self.assertEqual(im.size, (1000, 1000))
            self.assertNotIn("exif", im.info)
        self.assertNotIn(b"PhoneMakerTest", raw)
        with Image.open(self.flow / "assets" / "img" / (stem + "-card.jpg")) as im:
            self.assertEqual(im.size, (520, 520))
        made = json.loads((self.flow / "tools" / "derivatives.json").read_text())
        self.assertIn("assets/img/%s-600.jpg" % stem, made)
        self.assertIn(name, (self.flow / "assets" / "catalogue.js").read_text())
        # the upload is used up
        st, res = self.attach(sid, b.api("GET", "products/vibe")[1]["rev"], {"kind": "product-image", "product": "vibe"})
        self.assertEqual(st, 404)

    def test_product_photos_are_editable_but_checked(self):
        b = self.b
        st, prod = b.api("GET", "products/be-mine")
        imgs = prod["data"]["images"]
        st, res = b.api("PUT", "products/be-mine", {"data": dict(prod["data"], images=imgs[::-1])}, rev=prod["rev"])
        self.assertEqual(st, 200, res)
        self.assertEqual(b.content("products")["be-mine"]["images"], imgs[::-1])
        for bad in (["be-mine-99.jpg"], ["../x.jpg"], ["banner-1.jpg"], ["vibe-1-600.jpg"], [imgs[0], imgs[0]]):
            st, res = b.api("PUT", "products/be-mine", {"data": dict(res["data"], images=bad)}, rev=res["rev"])
            self.assertEqual(st, 422, bad)
            st, res = b.api("GET", "products/be-mine")

    # ---- refusals ------------------------------------------------------------

    def test_refusals(self):
        b = self.b
        photo = png(Image.new("RGB", (1200, 1200), (200, 200, 200)))
        cases = [
            ("wrong content type", "product-image", b"hello", "text/plain", 415, None),
            ("png sent as jpeg", "product-image", photo, "image/jpeg", 415, None),
            ("svg", "product-image", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
             "image/svg+xml", 415, "SVG"),
            ("svg sent as png", "product-image", b'<?xml version="1.0"?><svg></svg>', "image/png", 415, "SVG"),
            ("heic", "product-image", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "image/heic", 415, "HEIC"),
            ("heic sent as jpeg", "product-image", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "image/jpeg", 415, "HEIC"),
            ("bomb", "product-image", png_header(9000, 9000), "image/png", 422, None),
            ("side over 12000 px", "banner", png_header(12001, 900), "image/png", 422, None),
            ("polyglot", "product-image", photo + b"<html><script>alert(1)</script></html>", "image/png", 422, None),
            ("too small a frame", "product-image", jpeg(800, 800), "image/jpeg", 422, None),
            ("cut-out without alpha", "cutout", photo, "image/png", 422, None),
            ("cut-out as jpeg", "cutout", jpeg(600, 800), "image/jpeg", 415, None),
            ("unknown kind", "poster", photo, "image/png", 400, None),
        ]
        anim = io.BytesIO()
        frames = [Image.new("RGB", (1100, 1100), c) for c in ((255, 0, 0), (0, 0, 255))]
        frames[0].save(anim, "PNG", save_all=True, append_images=frames[1:])
        cases.append(("animated png", "product-image", anim.getvalue(), "image/png", 422, None))
        codes = {}
        for label, kind, data, ctype, want, word in cases:
            st, res = self.stage(kind, data, ctype)
            self.assertEqual(st, want, "%s: %s" % (label, res))
            codes[label] = res["error"]["code"]
            if word:
                self.assertIn(word, res["error"]["message"], label)
        self.assertEqual(codes["bomb"], "too_many_pixels")
        self.assertEqual(codes["side over 12000 px"], "too_large_image")
        self.assertEqual(codes["polyglot"], "polyglot")
        self.assertEqual(codes["cut-out without alpha"], "no_alpha")
        self.assertEqual(codes["animated png"], "animated")
        # the per-kind cap is checked on the headers, before the body is read
        st, res = self.headers_only("media/staging?kind=category-photo", "image/jpeg", 10 * 1024 * 1024 + 1)
        self.assertEqual((st, res["error"]["code"]), (413, "too_large"))
        st, res = self.headers_only("media/staging?kind=reel", "video/mp4", 80 * 1024 * 1024 + 1)
        self.assertEqual(st, 413)
        # nothing refused is left in staging
        left = [p.name for p in (self.flow / "content" / ".backups" / "staging").iterdir()]
        self.assertFalse([n for n in left if n.endswith((".upload", ".png", ".jpg"))
                          and not (self.flow / "content" / ".backups" / "staging" / (n.split(".")[0] + ".json")).exists()], left)

    def test_attach_checks_kind_and_rev(self):
        b = self.b
        st, res = self.stage("product-image", jpeg(1200, 1200), "image/jpeg")
        sid = res["staging_id"]
        st, prod = b.api("GET", "products/amore")
        st, res = self.attach(sid, prod["rev"], {"kind": "banner", "slide": 0})
        self.assertEqual(st, 422)
        st, res = self.attach(sid, "0" * 16, {"kind": "product-image", "product": "amore"})
        self.assertEqual(st, 412)
        st, res = self.attach(sid, None, {"kind": "product-image", "product": "amore"})
        self.assertEqual(st, 428)
        st, res = self.attach("f" * 32, prod["rev"], {"kind": "product-image", "product": "amore"})
        self.assertEqual(st, 404)
        st, res = self.attach("../../x", prod["rev"], {"kind": "product-image", "product": "amore"})
        self.assertEqual(st, 404)

    # ---- trash and restore ---------------------------------------------------

    def test_trash_refuses_a_referenced_file_and_restore_brings_one_back(self):
        b = self.b
        st, res = b.api("POST", "media/trash", {"path": "assets/img/vibe-1.jpg"})
        self.assertEqual(st, 409, res)
        self.assertEqual(res["error"]["code"], "referenced")
        self.assertTrue(res["error"]["details"]["refs"])
        self.assertTrue((self.flow / "assets" / "img" / "vibe-1.jpg").is_file())
        st, res = b.api("POST", "media/trash", {"path": "assets/img/vibe-1-600.jpg"})
        self.assertEqual(st, 422)
        st, res = b.api("POST", "media/trash", {"path": "content/products.json"})
        self.assertEqual(st, 404)
        st, res = b.api("POST", "media/trash", {"path": "assets/../content/products.json"})
        self.assertEqual(st, 404)
        # an unused category photo: its 216 copy goes with it
        cat = self.flow / "assets" / "cat"
        st, lib = b.api("GET", "media?unused=1&kind=category-photo")
        self.assertEqual(st, 200)
        self.assertTrue(lib["items"], "the clone has no unused category photo to trash")
        path = lib["items"][0]["path"]
        name = path.rpartition("/")[2][:-4]
        keep = {p: (cat / p).read_bytes() for p in (name + ".jpg", name + "-216.jpg")}
        st, res = b.api("POST", "media/trash", {"path": path})
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        self.assertEqual(sorted(res["files"]), sorted("assets/cat/" + p for p in keep))
        for p in keep:
            self.assertFalse((cat / p).exists(), p)
        made = json.loads((self.flow / "tools" / "derivatives.json").read_text())
        self.assertNotIn("assets/cat/%s-216.jpg" % name, made)
        st, tl = b.api("GET", "media/trash")
        self.assertIn(res["trash_id"], [t["trash_id"] for t in tl["items"]])
        st, res2 = b.api("POST", "media/restore", {"trash_id": res["trash_id"]})
        self.assertEqual(st, 200, res2)
        for p, data in keep.items():
            self.assertEqual((cat / p).read_bytes(), data, p)
        made = json.loads((self.flow / "tools" / "derivatives.json").read_text())
        self.assertIn("assets/cat/%s-216.jpg" % name, made)
        st, tl = b.api("GET", "media/trash")
        self.assertNotIn(res["trash_id"], [t["trash_id"] for t in tl["items"]])
        self.assertEqual(b.api("POST", "media/restore", {"trash_id": res["trash_id"]})[0], 404)
        self.assertEqual(b.api("POST", "media/restore", {"trash_id": "../../etc"})[0], 404)

    def test_failed_build_removes_the_created_files(self):
        b = self.b
        still = self.flow / "assets" / "video" / "vibe.jpg"
        aside = self.flow / "vibe-still.aside"
        products = (self.flow / "content" / "products.json").read_bytes()
        made = (self.flow / "tools" / "derivatives.json").read_bytes()
        st, res = self.stage("product-image", jpeg(1200, 1200), "image/jpeg")
        sid = res["staging_id"]
        st, prod = b.api("GET", "products/amore")
        files = self.img_files()
        # a file the homepage needs goes missing, so the build fails
        shutil.move(str(still), str(aside))
        try:
            st, res = self.attach(sid, prod["rev"], {"kind": "product-image", "product": "amore"})
        finally:
            shutil.move(str(aside), str(still))
        self.assertEqual(st, 422, res)
        self.assertEqual(res["error"]["code"], "build_failed")
        self.assertTrue(res["error"]["details"]["restored"])
        self.assertEqual(self.img_files(), files)
        self.assertEqual((self.flow / "content" / "products.json").read_bytes(), products)
        self.assertEqual((self.flow / "tools" / "derivatives.json").read_bytes(), made)
        # with the file back the same upload goes in
        st, res = self.attach(sid, prod["rev"], {"kind": "product-image", "product": "amore"})
        self.assertEqual(st, 200, res)

    def test_a_save_sweeps_an_orphan_copy_instead_of_failing(self):
        # A sized copy without its original (a file removed outside the admin)
        # is swept by make_derivatives on the next media save. That sweep used
        # to be reported as a file the build should not have changed, failing
        # the save with a confusing message and not putting the copy back.
        b = self.b
        img = self.flow / "assets" / "img"
        orphan = img / "zz-9-600.jpg"
        shutil.copy(str(img / "amore-1-600.jpg"), str(orphan))
        st, media = b.api("GET", "media")
        self.assertEqual(st, 200, media)
        self.assertIn("assets/img/zz-9-600.jpg", [i["path"] for i in media["items"] if i["kind"] == "orphan"])
        products = (self.flow / "content" / "products.json").read_bytes()
        st, res = self.stage("product-image", jpeg(1200, 1200), "image/jpeg")
        sid = res["staging_id"]
        st, prod = b.api("GET", "products/vibe")
        st, res = self.attach(sid, prod["rev"], {"kind": "product-image", "product": "vibe"})
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        # the orphan is gone (swept, as make_derivatives does) and the product saved
        self.assertFalse(orphan.exists(), "the orphan copy should have been swept")
        self.assertNotEqual((self.flow / "content" / "products.json").read_bytes(), products)

    # ---- the other kinds -----------------------------------------------------

    def test_a_scent_family_photo(self):
        b = self.b
        # too small for the 900x675 tile
        st, res = self.stage("family-photo", jpeg(880, 700), "image/jpeg")
        self.assertEqual(st, 422, res)
        st, res = self.stage("family-photo", jpeg(1600, 1000), "image/jpeg")
        self.assertEqual(st, 201, res)
        sid = res["staging_id"]
        st, pages = b.api("GET", "documents/pages")
        st, res = self.attach(sid, pages["rev"], {"kind": "family-photo", "family": "no-such-family"})
        self.assertEqual(st, 422, res)
        st, res = self.attach(sid, pages["rev"], {"kind": "family-photo", "family": "reserve"})
        self.assertEqual(st, 200, res)
        orig, copy = res["paths"]
        self.assertEqual(b.content("pages")["index"]["families"]["reserve"]["image"], orig)
        with Image.open(self.flow / orig) as im:
            self.assertEqual(im.size, (900, 675))
        with Image.open(self.flow / copy) as im:
            self.assertEqual(im.size, (450, 338))
        home = (self.flow / "index.html").read_text()
        self.assertIn(copy + "?v=", home)
        self.assertIn(orig + "?v=", home)
        # the photo it replaced is still published, and now unused
        st, lib = b.api("GET", "media?unused=1&kind=family-photo")
        self.assertEqual(st, 200, lib)
        self.assertIn("assets/fam/reserve.jpg", [it["path"] for it in lib["items"]])

    def test_banner_category_cutout_logo_and_emblem(self):
        b = self.b
        img, cat = self.flow / "assets" / "img", self.flow / "assets" / "cat"
        # banner: two crops of one picture
        st, res = self.stage("banner", jpeg(3000, 1600), "image/jpeg")
        self.assertEqual(st, 201, res)
        st, home = b.api("GET", "documents/home")
        st, res = self.attach(res["staging_id"], home["rev"], {
            "kind": "banner", "slide": 1, "crop_desktop": {"x": 0, "y": 0.2, "w": 1, "h": 0.5},
            "crop_phone": {"x": 0.3, "y": 0.2, "w": 0.4, "h": 0.5}})
        self.assertEqual(st, 200, res)
        desk, phone = res["paths"]
        self.assertEqual(b.content("home")["hero_slides"][1]["image"], desk)
        with Image.open(self.flow / desk) as im:
            self.assertEqual(im.size, (2400, 790))
        with Image.open(self.flow / phone) as im:
            self.assertEqual(im.size, (1110, 600))
        for c in (desk[:-4] + "-1320.jpg", phone[:-4] + "-750.jpg"):
            self.assertTrue((self.flow / c).is_file(), c)
        # a phone crop narrower than 1110 px of the picture is refused
        st, res = self.stage("banner", jpeg(2400, 800), "image/jpeg")
        st, home = b.api("GET", "documents/home")
        st, res = self.attach(res["staging_id"], home["rev"], {
            "kind": "banner", "slide": 0, "crop_phone": {"x": 0, "y": 0, "w": 0.3, "h": 1}})
        self.assertEqual(st, 422, res)
        # category photo: a 432 square, the circle shows its 216 copy
        st, res = self.stage("category-photo", jpeg(900, 600), "image/jpeg")
        st, nav = b.api("GET", "documents/navigation")
        st, res = self.attach(res["staging_id"], nav["rev"], {"kind": "category-photo", "index": 4})
        self.assertEqual(st, 200, res)
        entry = b.content("navigation")["categories"][4]
        self.assertEqual(entry["image"], res["paths"][1])
        self.assertNotIn("cutout", entry)
        with Image.open(self.flow / res["paths"][0]) as im:
            self.assertEqual(im.size, (432, 432))
        self.assertTrue((self.flow / res["paths"][1]).is_file())
        # cut-out: trimmed onto the 204x240 canvas, 256 colours
        st, res = self.stage("cutout", cutout(), "image/png")
        self.assertEqual(st, 201, res)
        st, nav = b.api("GET", "documents/navigation")
        st, res = self.attach(res["staging_id"], nav["rev"], {"kind": "cutout", "index": 1})
        self.assertEqual(st, 200, res)
        entry = b.content("navigation")["categories"][1]
        self.assertEqual((entry["image"], entry["cutout"]), (res["paths"][0], True))
        with Image.open(self.flow / entry["image"]) as im:
            self.assertEqual((im.size, im.mode), ((204, 240), "P"))
        # logo: the old file goes to the trash, make_derivatives makes the 486 copy
        logo = img / "logo-gold.png"
        old = logo.read_bytes()
        mark = Image.new("RGBA", (1600, 300), (0, 0, 0, 0))
        ImageDraw.Draw(mark).rectangle((40, 40, 1560, 260), fill=(168, 121, 30, 255))
        st, res = self.stage("logo", png(mark), "image/png")
        self.assertEqual(st, 201, res)
        st, settings = b.api("GET", "documents/settings")
        st, res = self.attach(res["staging_id"], settings["rev"], {"kind": "logo", "variant": "dark"})
        self.assertEqual(st, 200, res)
        self.assertNotEqual(logo.read_bytes(), old)
        with Image.open(img / "logo-gold-486.png") as im:
            self.assertEqual(im.width, 486)
        trashed = self.flow / "content" / ".backups" / "trash" / res["trashed"] / "assets" / "img" / "logo-gold.png"
        self.assertEqual(trashed.read_bytes(), old)
        # restoring the old logo puts the new one in the trash in its place
        st, res2 = b.api("POST", "media/restore", {"trash_id": res["trashed"]})
        self.assertEqual(st, 200, res2)
        self.assertEqual(logo.read_bytes(), old)
        self.assertTrue(res2["trashed"])
        # emblem: make_favicon rebuilds the icons
        icon = (img / "favicon-32.png").read_bytes()
        em = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        ImageDraw.Draw(em).ellipse((40, 40, 360, 360), fill=(30, 90, 160, 255))
        st, res = self.stage("emblem", png(em), "image/png")
        self.assertEqual(st, 201, res)
        st, settings = b.api("GET", "documents/settings")
        st, res = self.attach(res["staging_id"], settings["rev"], {"kind": "emblem"})
        self.assertEqual(st, 200, res)
        self.assertNotEqual((img / "favicon-32.png").read_bytes(), icon)
        with Image.open(img / "logo-emblem.png") as im:
            self.assertEqual(im.size, (256, 256))

    def test_library_groups_copies_under_originals(self):
        st, lib = self.b.api("GET", "media")
        self.assertEqual(st, 200)
        items = {it["path"]: it for it in lib["items"]}
        frame = items["assets/img/vibe-1.jpg"]
        self.assertEqual(frame["kind"], "product-image")
        self.assertTrue(frame["used_by"])
        self.assertEqual(sorted(frame["copies"]["ok"]), sorted("assets/img/vibe-1%s.jpg" % s
                                                              for s in ("-card", "-600", "-card-360", "-thumb")))
        self.assertNotIn("assets/img/vibe-1-600.jpg", items)
        self.assertNotIn("assets/img/logo-gold-486.png", items)
        self.assertIn("assets/img/logo-gold-486.png", items["assets/img/logo-gold.png"]["copies"]["ok"])
        self.assertEqual(items["assets/video/vibe.mp4"]["copies"]["ok"], ["assets/video/vibe.jpg"])
        self.assertTrue(all(it["published"] for it in lib["items"]))
        st, lib = self.b.api("GET", "media?kind=banner")
        self.assertTrue(lib["items"] and all(it["kind"] == "banner" for it in lib["items"]))
        st, lib = self.b.api("GET", "media?unused=1")
        self.assertTrue(all(not it["used_by"] for it in lib["items"]))

    # ---- films ---------------------------------------------------------------

    def test_upload_fields_move_but_only_onto_real_files(self):
        """The banner, film, circle, logo and icon fields are no longer read
        only: a save may reorder or repoint them, but only onto a file the
        site publishes and that is there."""
        b = self.b
        st, home = b.api("GET", "documents/home")
        self.assertEqual(st, 200, home)
        data = home["data"]
        slides, films = data["hero_slides"], data["reels"]["items"]
        moved = dict(data, hero_slides=[slides[1], slides[0]] + slides[2:],
                     reels=dict(data["reels"], items=[films[1], films[0]] + films[2:]))
        st, res = b.api("PUT", "documents/home", {"data": moved}, rev=home["rev"])
        self.assertEqual(st, 200, res)
        for bad, code in (("assets/img/nope.jpg", "missing_file"), ("content/home.json", "format"),
                          ("assets/img/../../content/home.json", "format"), (films[0]["video"], "format")):
            s = [dict(x) for x in res["data"]["hero_slides"]]
            s[0]["image"] = bad
            st, out = b.api("PUT", "documents/home", {"data": dict(res["data"], hero_slides=s)}, rev=res["rev"])
            self.assertEqual(st, 422, (bad, out))
            self.assertEqual([d["code"] for d in out["error"]["details"]], [code], bad)
        s = [dict(x) for x in res["data"]["hero_slides"]]
        s[0]["image"] = s[1]["image"]
        st, res = b.api("PUT", "documents/home", {"data": dict(res["data"], hero_slides=s)}, rev=res["rev"])
        self.assertEqual(st, 200, res)
        st, res = b.api("PUT", "documents/home", {"data": data}, rev=res["rev"])
        self.assertEqual(st, 200, res)
        st, sets = b.api("GET", "documents/settings")
        brand = dict(sets["data"]["brand"], logo="assets/img/nope.png")
        st, out = b.api("PUT", "documents/settings", {"data": dict(sets["data"], brand=brand)}, rev=sets["rev"])
        self.assertEqual(st, 422, out)
        self.assertEqual([d["code"] for d in out["error"]["details"]], ["missing_file"])

    def test_film_upload_transcode_and_attach(self):
        b = self.b
        tmp = tempfile.mkdtemp(prefix="bgsmedia-")
        try:
            def film(size):
                out = os.path.join(tmp, "f-%s.mp4" % size)
                subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=%s:rate=30" % size,
                                "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-metadata", "title=SecretTitle", out],
                               check=True, timeout=60)
                with open(out, "rb") as f:
                    return f.read()
            st, res = self.stage("reel", film("960x540"), "video/mp4")
            self.assertEqual((st, res["error"]["code"]), (422, "not_portrait"))
            st, res = self.stage("reel", film("540x960"), "video/mp4")
            self.assertEqual(st, 201, res)
            self.assertAlmostEqual(res["duration"], 2, delta=0.2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        st, home = b.api("GET", "documents/home")
        n = len(home["data"]["reels"]["items"])
        st, job = self.attach(res["staging_id"], home["rev"], {"kind": "reel", "product": "vibe", "index": n})
        self.assertEqual(st, 202, job)
        for _ in range(180):
            st, view = b.api("GET", "jobs/" + job["job"])
            if view["state"] in ("done", "failed"):
                break
            time.sleep(0.25)
        self.assertEqual(view["state"], "done", view)
        item = b.content("home")["reels"]["items"][n]
        self.assertEqual(item["product"], "vibe")
        self.assertEqual([item["video"], item["still"]], view["result"]["paths"])
        mp4 = self.flow / item["video"]
        probe = json.loads(subprocess.run(["/opt/homebrew/bin/ffprobe", "-v", "error", "-show_streams", "-show_format",
                                           "-of", "json", str(mp4)], capture_output=True, timeout=30).stdout)
        vids = [s for s in probe["streams"] if s["codec_type"] == "video"]
        self.assertEqual([(s["width"], s["height"], s["codec_name"]) for s in vids], [(540, 960, "h264")])
        self.assertFalse([s for s in probe["streams"] if s["codec_type"] == "audio"])
        self.assertNotIn(b"SecretTitle", mp4.read_bytes())
        with Image.open(self.flow / item["still"]) as im:
            self.assertEqual(im.size, (480, 854))


if __name__ == "__main__":
    unittest.main()
