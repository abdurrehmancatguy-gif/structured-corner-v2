"""Recolour the logo art to one flat colour.

The owner asked for the logo in one solid colour, #A8791E, with no gradient,
shine or glare, the word included. Every visible pixel of each file below is
set to that colour and its alpha is kept, so the lockup keeps its shape and
its soft edges. The shop shows them through content/settings.json brand:
the header logo and the footer logo (their -486 copies) and the icons made
from the emblem.

    python3 tools/flat_logo.py          # from flow/
    python3 tools/make_derivatives.py   # the -486 copies the pages show
    python3 tools/make_favicon.py       # favicon.ico, the 32 and 16 px icons, the home screen icon

It reads 3.88:1 on the white masthead and 3.79:1 on the #34260B footer. It
replaces the metal ramps tools/make_gold_logo.py draws, which would bring the
gradient back if that were run again, so run this after it.
"""
import pathlib
from PIL import Image

IMG = pathlib.Path(__file__).resolve().parent.parent / "assets" / "img"
COLOUR = (0xA8, 0x79, 0x1E)
FILES = ("logo-gold.png", "logo-gold-light.png", "logo-emblem.png")

for name in FILES:
    p = IMG / name
    im = Image.open(p).convert("RGBA")
    flat = Image.new("RGBA", im.size, COLOUR + (0,))
    flat.putalpha(im.getchannel("A"))
    flat.save(p, optimize=True)
    print("recoloured", name, "%dx%d" % im.size)
