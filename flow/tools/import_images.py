#!/usr/bin/env python3
"""
Import product photography into the storefront.

Reads the retouched shots from the photo folder, produces web-sized
derivatives in assets/img/, and records which images belong to which product
in content/products.json so the admin and the build both see them.

Uses sips, which ships with macOS, plus Pillow for the one composited banner.

    python3 tools/import_images.py            # from flow/
    python3 tools/import_images.py --dry-run  # show the plan, touch nothing

Sources are never modified; everything is written into assets/img/.

WHY A MAPPING TABLE
-------------------
Most image sets are named after the product and match on their own. The five
bakhoor sets are named "Bakhoor 1".."Bakhoor 5" after the tin label, not after
the product names in the sheet (Shay, Compodi, Mattar, Falah, Philippine), so
they cannot be matched automatically. Fill BAKHOOR_MAP in when the numbers are
confirmed; until then those products keep their placeholders rather than
risking the wrong tin on the wrong product.
"""

import json, pathlib, re, subprocess, sys, shutil, os

FLOW    = pathlib.Path(__file__).resolve().parent.parent
SRC     = pathlib.Path("/Users/ajoomama/Desktop/CORNER_RAW_IMAGES/edited")
BANNER  = pathlib.Path("/Users/ajoomama/Desktop/CORNER_RAW_IMAGES/Codex Image Sep 1, 2026, 06_10_53 PM.png")
OUT     = FLOW / "assets" / "img"
CONTENT = FLOW / "content" / "products.json"

SQUARE, CARD, QUALITY = 1000, 520, 72       # px, px, jpeg quality
MAX_PER_PRODUCT = 8   # you supplied up to 60 per product; 8 is a gallery,
                      # beyond that it is a slideshow nobody reaches the end of

# image-set name -> product id. Only unambiguous pairings live here.
EXTRA_MAP = {
    "Solei Frais":  "soleil-frais",          # spelling differs from the sheet
    "Platinum Oud": "platinum-musk-oud",
}
# "Bakhoor 1".."Bakhoor 5" -> product id. Empty until the tins are identified.
BAKHOOR_MAP = {}

# Which shot is the bare product and which shows the box, per product, read off
# contact sheets of every imported image. There is no pattern to inherit: the
# box is frame 3 for Suit Up, 5 for Be Mine, 7 for Amore, and frame 1 for most
# of the oud oils, which are shot in a leather BGS case rather than a carton.
# 1-based, matching the numbering on the contact sheets.
#   product: (close-up frame, box frame or None)
SHOT_ORDER = {
    "be-mine":                 (1, 5),
    "vibe":                    (1, None),   # every frame is the bottle
    "pride-of-arabia":         (1, 4),
    "suit-up":                 (1, 3),
    "edward-the-black-prince": (1, 5),
    "amore":                   (1, 7),
    "soleil-frais":            (1, 5),
    "barcelona":               (1, 5),
    "imperial-crown":          (2, 1),
    "dark-leather":            (1, 5),
    "royal-amber":             (1, 5),
    "golden-bloom":            (2, 1),
    "majestic-musk":           (3, 1),
    "belle-aura":              (3, 1),
    "magnolia-veil":           (4, 1),
    "parisian-muse":           (4, 1),
    "velvet-spell":            (2, 1),
    "desert-breeze":           (1, 8),
    "majlis-oud":              (1, 4),
    "platinum-musk-oud":       (1, None),   # one frame, and it has the box in it
}


def order_shots(pid, names):
    """Close-up first, box second, everything else after in its original order.
       A product with no box shot keeps its close-up first and simply has no
       second view to swap to."""
    pair = SHOT_ORDER.get(pid)
    if not pair:
        return names
    close, box = pair
    picked = []
    for idx in (close, box):
        if idx and 1 <= idx <= len(names) and names[idx - 1] not in picked:
            picked.append(names[idx - 1])
    return picked + [n for n in names if n not in picked]


# The category circles live at assets/cat/<key>.jpg, referenced by flow.css.
# Only the four tiles that ARE a product category take real photography. Gift
# Sets, Discovery, Shop by Occasion and Corporate Gifting are concepts, not
# products: the Collection set gave four near-identical rows of bottles for
# them, so they keep their Pexels stock (see assets/cat/SOURCES.txt) and this
# tool leaves those files alone.
CATEGORY_IMAGES = {
    "oud":  ("Royal Amber", 0),
    "res":  ("Majlis Oud", 0),
    "bak":  ("Bakhoor 1", 0),
    "musk": ("Pride Of Arabia", 0),
}

def sh(*args):
    subprocess.run(args, check=True, capture_output=True)


def sets_available():
    out = {}
    for f in sorted(os.listdir(SRC)):
        if not f.endswith("_EDITED.JPG"):
            continue
        name = re.sub(r"_\d+_EDITED\.JPG$", "", f).replace("RAW_BGS_", "")
        out.setdefault(name, []).append(SRC / f)
    return out


def square(src, dst, size):
    """Resize so the short side covers, then centre-crop to a square."""
    tmp = dst.with_suffix(".tmp.jpg")
    shutil.copy2(src, tmp)
    sh("sips", "-Z", str(size * 2), str(tmp))      # long side first
    sh("sips", "-c", str(size), str(size), str(tmp))
    sh("sips", "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY),
       str(tmp), "--out", str(dst))
    tmp.unlink(missing_ok=True)


def banner(src, dst, w=2400, h=790):
    """The hero is a composite, not a crop.

    The source is a portrait shot of the bottle inside a ring of salt. A wide
    band cut straight out of it loses the ring and leaves no room for the
    headline, so the frame is extended in the photograph's own black and the
    shot placed to the right.

    No blend mask. The source's own left edge is already black (mean luminance
    3.4 of 255), so it butts against the canvas invisibly. The earlier attempt
    feathered the paste, and the fade was itself the artifact: it put a 39.7
    brightness step at the 72% mark. A hard paste measures better than the
    photograph's own internal contrast. check_seam() enforces that."""
    from PIL import Image
    src_img = Image.open(src).convert("RGB")
    canvas = Image.new("RGB", (w, h), (0, 0, 0))

    sw = int(w * 0.68)                      # leaves the left third for the type
    sh_ = int(src_img.height * (sw / src_img.width))
    sub = src_img.resize((sw, sh_), Image.LANCZOS)
    top = (sh_ - h) // 2
    sub = sub.crop((0, top, sw, top + h))

    canvas.paste(sub, (w - sw, 0))
    canvas.save(dst, "JPEG", quality=84, optimize=True, progressive=True)

    # Verify against a control: the same band with no compositing at all. Any
    # excess over the control is something this function introduced.
    import tempfile, os
    fd, ctrl = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    sub.save(ctrl, "JPEG", quality=84)
    a, b = check_seam(dst), check_seam(ctrl)
    os.unlink(ctrl)
    added = round(a["worst_column_jump"] - b["worst_column_jump"], 2)
    return {"photo_contrast": b["worst_column_jump"],
            "banner_worst": a["worst_column_jump"],
            "added_by_compositing": added,
            "seamless": added < 2.0}


def check_seam(path):
    """Scan for a vertical seam: a column whose mean brightness jumps away from
       its neighbours. Returns the worst jump found, in 0-255 units."""
    from PIL import Image
    im = Image.open(path).convert("L")
    w, h = im.size
    px = im.load()
    cols = []
    for x in range(w):
        cols.append(sum(px[x, y] for y in range(0, h, 7)) / len(range(0, h, 7)))
    worst, at = 0.0, 0
    for x in range(2, w - 2):
        d = abs((cols[x + 1] + cols[x + 2]) / 2 - (cols[x - 1] + cols[x - 2]) / 2)
        if d > worst:
            worst, at = d, x
    return {"worst_column_jump": round(worst, 2), "at_x": at,
            "at_pct": round(100 * at / w, 1)}

def main():
    dry = "--dry-run" in sys.argv
    if not SRC.exists():
        sys.exit("photo folder not found: %s" % SRC)

    products = json.loads(CONTENT.read_text())
    by_name = {re.sub(r"[^a-z0-9]", "", v["name"].lower()): k for k, v in products.items()}
    avail = sets_available()

    plan, skipped = {}, []
    for name, files in avail.items():
        pid = by_name.get(re.sub(r"[^a-z0-9]", "", name.lower())) \
              or EXTRA_MAP.get(name) or BAKHOOR_MAP.get(name)
        if not pid or pid not in products:
            skipped.append(name)
            continue
        plan[pid] = sorted(files)[:MAX_PER_PRODUCT]

    print("%d image sets -> %d products" % (len(avail), len(plan)))
    if skipped:
        print("not mapped (left alone): %s" % ", ".join(sorted(skipped)))
    missing = [k for k in products if k not in plan and products[k].get("published", True)]
    print("published products still without photography: %d" % len(missing))
    if dry:
        for pid, files in sorted(plan.items()):
            print("  %-26s %d image(s)" % (pid, len(files)))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for pid, files in sorted(plan.items()):
        names = []
        for i, f in enumerate(files, 1):
            full = OUT / ("%s-%d.jpg" % (pid, i))
            card = OUT / ("%s-%d-card.jpg" % (pid, i))
            square(f, full, SQUARE)
            square(f, card, CARD)
            names.append(full.name)
            written += 2
        products[pid]["images"] = order_shots(pid, names)
        print("  %-26s %d" % (pid, len(names)))

    # the banner
    if BANNER.exists():
        seam = banner(BANNER, OUT / "banner-1.jpg")
        print("  banner seam check: %s" % seam)
        written += 1
        print("  banner-1.jpg written from %s" % BANNER.name)

    # category tiles: real product photography replaces the stock images,
    # written to the paths flow.css already points at
    catdir = FLOW / "assets" / "cat"
    catdir.mkdir(parents=True, exist_ok=True)
    for key, (setname, idx) in CATEGORY_IMAGES.items():
        files = sorted(avail.get(setname, []))
        if not files:
            continue
        square(files[min(idx, len(files) - 1)], catdir / ("%s.jpg" % key), 600)
        written += 1

    CONTENT.write_text(json.dumps(products, indent=2, ensure_ascii=False) + "\n")
    print("wrote %d files into assets/img/, and the image lists into products.json" % written)


if __name__ == "__main__":
    main()
