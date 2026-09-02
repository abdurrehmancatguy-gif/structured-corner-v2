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
MAX_PER_PRODUCT = 4                          # the PDP gallery shows four

# image-set name -> product id. Only unambiguous pairings live here.
EXTRA_MAP = {
    "Solei Frais":  "soleil-frais",          # spelling differs from the sheet
    "Platinum Oud": "platinum-musk-oud",
}
# "Bakhoor 1".."Bakhoor 5" -> product id. Empty until the tins are identified.
BAKHOOR_MAP = {}

# The category circles live at assets/cat/<key>.jpg, referenced by flow.css.
# key -> (image set, which shot). The four gift/occasion tiles all draw on the
# Collection set, so they take different frames rather than repeating one.
CATEGORY_IMAGES = {
    "oud":    ("Royal Amber", 0),
    "res":    ("Majlis Oud", 0),
    "bak":    ("Bakhoor 1", 0),
    "musk":   ("Pride Of Arabia", 0),
    "floral": ("Collection", 2),
    "fresh":  ("Collection", 8),
    "amber":  ("Collection", 14),
    "sweet":  ("Collection", 20),
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
    shot is placed to the right, feathered so there is no seam. That gives the
    hero a dark left half to set type on, which is how the reference reads."""
    from PIL import Image
    src_img = Image.open(src).convert("RGB")
    canvas = Image.new("RGB", (w, h), (0, 0, 0))

    sw = int(w * 0.70)
    sh_ = int(src_img.height * (sw / src_img.width))
    sub = src_img.resize((sw, sh_), Image.LANCZOS)
    top = (sh_ - h) // 2
    sub = sub.crop((0, top, sw, top + h))

    mask = Image.new("L", (sw, h), 255)
    grad = Image.linear_gradient("L").rotate(270, expand=True).resize((int(sw * 0.60), h))
    mask.paste(grad, (0, 0))
    canvas.paste(sub, (w - sw, 0), mask)
    canvas.save(dst, "JPEG", quality=82, optimize=True, progressive=True)


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
        products[pid]["images"] = names
        print("  %-26s %d" % (pid, len(names)))

    # the banner
    if BANNER.exists():
        banner(BANNER, OUT / "banner-1.jpg")
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
