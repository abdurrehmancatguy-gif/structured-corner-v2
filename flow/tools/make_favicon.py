#!/usr/bin/env python3
"""
Build the favicon set from the gold BGS emblem.

Source is assets/img/logo-emblem.png (transparent, square). Outputs:

  favicon.ico                  16/32/48 in one file, at the SITE ROOT so the
                               browser's implicit /favicon.ico probe finds it
  assets/img/favicon-32.png    modern browsers
  assets/img/favicon-16.png    small tab / bookmark bar
  assets/img/apple-touch-icon.png
                               180x180 on the brand ink, inset — iOS composites
                               transparency onto black and rounds the corners,
                               so this one cannot be transparent or edge-to-edge

Re-run after replacing the emblem; the paths are declared in
content/settings.json under brand.icons, which is what build.py renders.
"""
import pathlib
from PIL import Image, ImageFilter

FLOW = pathlib.Path(__file__).resolve().parent.parent
SRC = FLOW / "assets" / "img" / "logo-emblem.png"
IMG = FLOW / "assets" / "img"
INK = (23, 19, 16, 255)          # --ink #171310, the footer ground
APPLE_INSET = 0.82               # emblem occupies 82% of the iOS tile


def main():
    if not SRC.exists():
        raise SystemExit("missing source emblem: %s" % SRC)
    em = Image.open(SRC).convert("RGBA")
    if em.width != em.height:                      # square it, centred
        s = max(em.size)
        sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        sq.alpha_composite(em, ((s - em.width) // 2, (s - em.height) // 2))
        em = sq

    def small(n):
        """Downscale for tab-sized icons. The emblem is thin interlocking
        strokes over a gold gradient, which turns to mush at 16px on a plain
        resize, so step down and unsharp-mask to hold the strokes apart."""
        im = em.resize((n * 2, n * 2), Image.LANCZOS).resize((n, n), Image.LANCZOS)
        rgb = im.convert("RGB").filter(
            ImageFilter.UnsharpMask(radius=0.6, percent=140, threshold=2))
        out = rgb.convert("RGBA")
        out.putalpha(im.split()[3])
        return out

    # multi-size .ico at the site root, each size its own sharpened rendition
    ico = FLOW / "favicon.ico"
    i48, i32, i16 = small(48), small(32), small(16)
    try:
        i48.save(ico, format="ICO", sizes=[(48, 48), (32, 32), (16, 16)],
                 append_images=[i32, i16])
    except (TypeError, ValueError):                # older Pillow: no append_images
        i48.save(ico, format="ICO", sizes=[(48, 48), (32, 32), (16, 16)])
    print("wrote", ico.relative_to(FLOW))

    # transparent PNGs
    for n, im in ((32, i32), (16, i16)):
        p = IMG / ("favicon-%d.png" % n)
        im.save(p)
        print("wrote", p.relative_to(FLOW))

    # iOS tile: solid brand ground, inset
    tile, inner = 180, int(180 * APPLE_INSET)
    ios = Image.new("RGBA", (tile, tile), INK)
    ios.alpha_composite(em.resize((inner, inner), Image.LANCZOS),
                        ((tile - inner) // 2, (tile - inner) // 2))
    p = IMG / "apple-touch-icon.png"
    ios.convert("RGB").save(p)
    print("wrote", p.relative_to(FLOW))


if __name__ == "__main__":
    main()
