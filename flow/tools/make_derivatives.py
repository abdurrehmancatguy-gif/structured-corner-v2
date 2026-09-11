"""Write the smaller image files the pages ask for, next to their sources.

    python3 tools/make_derivatives.py          # from flow/

Product photos are stored at 1000 px (<id>-<n>.jpg) with a 520 px card copy,
both written by the importers. Pages need three more sizes so that a phone is
never sent a desktop file:
  <id>-<n>-600.jpg        product page main image (shown at 245 to 470 px)
  <id>-<n>-card-360.jpg   product cards on phones (shown at about 166 px)
  <id>-<n>-thumb.jpg      gallery thumbnails and bag lines (51 to 108 px)
Banners get a 750 px phone copy and a 1320 px desktop copy, category photos a
216 px square (twice the largest circle), and the logos a 486 px copy (three
times the phone logo, over twice the desktop one). A derivative is rewritten
only when its source is newer, so reruns are cheap and importers need no change.
If you change QUALITY or a size, bump DERIVATIVES in build.py as well: product
photo URLs are versioned by their original, so rewritten copies need a new salt.
If you change QUALITY or a size, bump DERIVATIVES in build.py as well: product
photo URLs are versioned by their original, so rewritten copies need a new salt.
If you change QUALITY or a size, bump DERIVATIVES in build.py as well: product
photo URLs are versioned by their original, so rewritten copies need a new salt.
"""
import pathlib
import re
from PIL import Image

FLOW = pathlib.Path(__file__).resolve().parent.parent
IMG, CAT = FLOW / "assets" / "img", FLOW / "assets" / "cat"
QUALITY = 78
# "vibe-1-600.jpg" also looks like frame 600 of "vibe-1", so a copy must never be
# taken for an original; without this a second run made copies of copies.
# Banner copies ("banner-1-1320.jpg") look like product frames the same way, so
# everything named banner- is handled by the banner branch alone.
COPIES = ("-600.jpg", "-card-360.jpg", "-thumb.jpg", "-card.jpg")
made = kept = 0


def stale(src, dst):
    return not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime


def jpeg(src, dst, width=None, square=None):
    global made, kept
    if not stale(src, dst):
        kept += 1
        return
    im = Image.open(src).convert("RGB")
    if square:
        s = min(im.size)
        l, t = (im.width - s) // 2, (im.height - s) // 2
        im = im.crop((l, t, l + s, t + s)).resize((square, square), Image.LANCZOS)
    elif width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    made += 1


def png(src, dst, width):
    global made, kept
    if not stale(src, dst):
        kept += 1
        return
    im = Image.open(src).convert("RGBA")
    im = im.convert("RGBa").resize((width, round(im.height * width / im.width)), Image.LANCZOS).convert("RGBA")
    im.quantize(256, method=Image.Quantize.FASTOCTREE).save(dst, optimize=True)
    made += 1


for src in sorted(IMG.glob("*.jpg")):
    m = re.fullmatch(r"(banner-\d+)(-phone)?\.jpg", src.name)
    if m:
        jpeg(src, IMG / ("%s-phone-750.jpg" % m.group(1) if m.group(2) else "%s-1320.jpg" % m.group(1)),
             750 if m.group(2) else 1320)
    elif (re.fullmatch(r"[a-z0-9-]+-\d+\.jpg", src.name) and not src.name.endswith(COPIES)
          and not src.name.startswith("banner-")):
        stem = src.name[:-4]
        jpeg(src, IMG / (stem + "-600.jpg"), 600)
        jpeg(src, IMG / (stem + "-card-360.jpg"), 360)
        jpeg(src, IMG / (stem + "-thumb.jpg"), 160)
for src in sorted(CAT.glob("*.jpg")):
    if not src.stem.endswith("-216"):
        jpeg(src, CAT / (src.stem + "-216.jpg"), square=216)
for name in ("logo-gold", "logo-gold-light"):
    png(IMG / (name + ".png"), IMG / (name + "-486.png"), 486)

# Copies whose original is gone (a re-import with fewer frames) go too, or they
# would sit in assets/ referenced by nothing.
removed = 0
for folder, suffixes, ext in ((IMG, ("-600", "-card-360", "-thumb"), ".jpg"), (CAT, ("-216",), ".jpg")):
    for suf in suffixes:
        for d in folder.glob("*" + suf + ext):
            if not (folder / (d.name[: -len(suf + ext)] + ext)).exists():
                d.unlink(); removed += 1
print("derivatives: %d written, %d already current, %d orphans removed" % (made, kept, removed))
