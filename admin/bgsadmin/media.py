"""Uploaded pictures, from the bytes a browser sends to the files the site
publishes (docs/PLAN.md security_model items 8 and 11, and
docs/CONTENT-MODEL.md, "Media pipeline").

Two steps. Staging keeps the upload under flow/content/.backups/staging,
never under flow/assets (everything there is published), checks it and
re-encodes it into a master with no metadata. Attaching cuts the master into
the house sizes for its target and hands the finished files to a store
transaction, which puts them in place, runs make_derivatives and the build,
and takes them away again if the build fails.

Every picture is decoded and encoded again, so nothing a camera or an editor
wrote into the file (GPS, a thumbnail, a script appended after the picture)
can reach the site, and every published name is made here, never taken from
the upload.
"""
import io
import json
import math
import os
import re
import secrets
import shutil
import struct
import time
import warnings

from PIL import Image, ImageCms, ImageOps

from .errors import ApiError

# A decompression bomb is a small file that unpacks into a huge picture. The
# pixel cap turns Pillow's warning into an error, and the size in the header
# is checked before a single pixel is decoded.
Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
MAX_SIDE = 12000

MB = 1024 * 1024
PHOTO = ("image/jpeg", "image/png", "image/webp")
# kind: (upload cap in bytes, accepted content types). Cut-outs, logos and the
# emblem stand on the page's own background, so they must be PNGs with alpha.
KINDS = {
    "product-image": (25 * MB, PHOTO),
    "banner": (30 * MB, PHOTO),
    "category-photo": (10 * MB, PHOTO),
    "cutout": (10 * MB, ("image/png",)),
    "logo": (10 * MB, ("image/png",)),
    "emblem": (10 * MB, ("image/png",)),
    "reel": (80 * MB, ("video/mp4",)),
}
LABELS = {"product-image": "product photo", "banner": "banner picture", "category-photo": "category photo",
          "cutout": "cut-out", "logo": "logo", "emblem": "emblem", "reel": "film"}
LARGEST = max(cap for cap, _ in KINDS.values())
HEIC = "HEIC and AVIF photos cannot be read here. Export the photo as a JPEG first (in Photos or Preview: File, Export)."
# The upload route takes these types only to say plainly why they are refused.
REFUSED = {
    "image/heic": HEIC,
    "image/heif": HEIC,
    "image/avif": HEIC,
    "image/svg+xml": "SVG files cannot be uploaded: they can carry script, and everything in the shop's assets is published.",
    "image/gif": "GIF files cannot be uploaded. Use a JPEG or a PNG; films go in as MP4.",
}
ROUTE_TYPES = sorted(set(PHOTO) | {"video/mp4"} | set(REFUSED))
PILLOW = {"image/jpeg": ("JPEG", "MPO"), "image/png": ("PNG",), "image/webp": ("WEBP",)}
EXPIRES = 24 * 3600
QUALITY = 72                   # the house JPEG quality (tools/import_website_set.py)
SID = re.compile(r"^[0-9a-f]{32}$")

FRAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-\d+\.jpg$")
FRAME_COPIES = ("-card", "-600", "-card-360", "-thumb")
LOGOS = {"dark": "logo-gold.png", "light": "logo-gold-light.png"}
EMBLEM = "logo-emblem.png"
FAVICON_OUTPUTS = ("favicon.ico", "assets/img/favicon-32.png", "assets/img/favicon-16.png",
                   "assets/img/apple-touch-icon.png")
CUTOUT_BOX, WIDE_BOX = (204, 240), (354, 154)
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


def bad(message, code="bad_image", status=422, details=None):
    return ApiError(status, code, message, details)


def check_upload(kind, ctype, length):
    """Type and size, before a byte of the body is read."""
    if kind not in KINDS:
        raise ApiError(400, "bad_request", "Say what the upload is for: kind is one of %s." % ", ".join(KINDS))
    cap, types = KINDS[kind]
    if ctype in REFUSED:
        raise bad(REFUSED[ctype], "unsupported_media_type", 415)
    if ctype not in types:
        need = "a PNG with a transparent background" if types == ("image/png",) else \
            "an MP4 film" if kind == "reel" else "a JPEG, PNG or WebP picture"
        raise bad("A %s must be %s." % (LABELS[kind], need), "unsupported_media_type", 415, {"accepted": list(types)})
    if length > cap:
        raise bad("A %s can be at most %d MB. This file is %.1f MB." % (LABELS[kind], cap // MB, length / MB),
                  "too_large", 413, {"limit": cap})


def sniff(head):
    """What the first bytes of a file say it is, whatever it was sent as."""
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        if head[8:12] in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif", b"avis"):
            return "image/heic"
        return "video/mp4"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head.lstrip(b"\xef\xbb\xbf \t\r\n")[:1] == b"<":
        return "image/svg+xml"
    return None


def check_magic(head, ctype):
    said = sniff(head)
    if said in REFUSED:
        raise bad(REFUSED[said], "unsupported_media_type", 415)
    if said != ctype:
        raise bad("The file is not the kind of file it says it is: it was sent as %s but its contents are %s."
                  % (ctype, said or "not a picture or film the admin knows"), "unsupported_media_type", 415)


# ---- reading an upload ------------------------------------------------------

def _png_end(b):
    i = 8
    while i + 12 <= len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        kind = b[i + 4:i + 8]
        i += 12 + n
        if kind == b"IEND":
            return i
    return None


def _jpeg_end(b):
    """Where the picture's end-of-image marker stops. After a start-of-scan
    the compressed data runs to the next marker that is not a stuffed FF00,
    a restart marker or fill."""
    i = 2
    while i + 2 <= len(b):
        if b[i] != 0xFF:
            return None
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0xD9:
            return i + 2
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if i + 4 > len(b):
            return None
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
        if m == 0xDA:
            while True:
                j = b.find(b"\xff", i)
                if j < 0 or j + 1 >= len(b):
                    return None
                nxt = b[j + 1]
                if nxt == 0 or 0xD0 <= nxt <= 0xD7:
                    i = j + 2
                elif nxt == 0xFF:
                    i = j + 1
                else:
                    i = j
                    break
    return None


def _webp_end(b):
    return 8 + struct.unpack("<I", b[4:8])[0] if len(b) >= 12 else None


def check_trailer(b, ctype, fmt):
    """A polyglot is a picture with something else stuck after it (a page, a
    script, an archive), made so that one file reads as both. The re-encode
    would drop the extra part anyway; refusing it says plainly what the file
    is. An MPO (a camera or iPhone JPEG carrying more pictures) keeps its extra
    pictures after the first one, so it is exempt; only its first picture is
    ever used."""
    if fmt == "MPO":
        return
    end = {"image/png": _png_end, "image/jpeg": _jpeg_end, "image/webp": _webp_end}[ctype](b)
    if end is None:
        raise bad("The picture is damaged or cut short. Export it again and retry.")
    rest = b[end:]
    if rest.strip(b"\x00"):
        raise bad("The file carries %d bytes of something else after the picture. Export the picture again "
                  "from a photo editor and upload that." % len(rest), "polyglot")


def open_image(path, ctype):
    """Open an upload after checking what it is and how big it says it is,
    and decode it. Returns the loaded image and its format."""
    b = path.read_bytes()
    check_magic(b[:64], ctype)
    try:
        im = Image.open(io.BytesIO(b))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise bad("The picture unpacks to more than %d million pixels, which is more than the admin opens."
                  % (Image.MAX_IMAGE_PIXELS // 1000000), "too_many_pixels")
    except (OSError, SyntaxError, ValueError):
        raise bad("The picture could not be read. Export it again as a JPEG or PNG and retry.")
    fmt = im.format
    if fmt not in PILLOW[ctype]:
        raise bad("The file is not the kind of file it says it is: sent as %s, it reads as %s." % (ctype, fmt),
                  "unsupported_media_type", 415)
    w, h = im.size
    if max(w, h) > MAX_SIDE:
        raise bad("The picture is %dx%d px; a side can be at most %d px." % (w, h, MAX_SIDE), "too_large_image")
    if w * h > Image.MAX_IMAGE_PIXELS:
        raise bad("The picture is %dx%d px, more than %d million pixels." % (w, h, Image.MAX_IMAGE_PIXELS // 1000000),
                  "too_many_pixels")
    if fmt != "MPO" and (getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) > 1):
        raise bad("Animated pictures cannot be uploaded. Upload a still picture, or the film as an MP4.", "animated")
    check_trailer(b, ctype, fmt)
    try:
        im.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise bad("The picture unpacks to more pixels than the admin opens.", "too_many_pixels")
    except (OSError, SyntaxError, ValueError):
        raise bad("The picture is damaged or cut short. Export it again and retry.")
    return im, fmt


def normalize(im):
    """Upright, in sRGB, RGB or RGBA (alpha only when the picture really has
    some), with no metadata left in it. Phone photos are Display P3: without
    the profile conversion their colours would come out dull."""
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode in ("I", "I;16", "I;16B", "I;16L"):
        # 16-bit greyscale: scaled down to 8 bits, not clipped to white
        im = im.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if im.mode in ("P", "PA") or (im.mode in ("L", "RGB") and "transparency" in im.info):
        im = im.convert("RGBA")
    alpha = None
    if im.mode in ("RGBA", "LA", "RGBa", "La"):
        alpha = im.getchannel("A")
        base = im.convert("L" if im.mode[0] == "L" else "RGB")
        if alpha.getextrema() == (255, 255):
            alpha = None
    elif im.mode in ("RGB", "L", "CMYK"):
        base = im
    else:
        base = im.convert("RGB")
    out = None
    if icc:
        try:
            out = ImageCms.profileToProfile(base, ImageCms.ImageCmsProfile(io.BytesIO(icc)), SRGB, outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError, TypeError):
            out = None           # an unreadable profile: take the numbers as sRGB
    if out is None:
        out = base.convert("RGB")
    if alpha is not None:
        out.putalpha(alpha)
    out.info = {}
    return out


def edge_clear(im):
    """The share of the border pixels that are (nearly) transparent."""
    if im.mode != "RGBA":
        return 0.0
    a = im.getchannel("A")
    w, h = a.size
    total = clear = 0
    for box in ((0, 0, w, 1), (0, h - 1, w, h), (0, 0, 1, h), (w - 1, 0, w, h)):
        hist = a.crop(box).histogram()
        total += sum(hist)
        clear += sum(hist[:16])
    return clear / total if total else 0.0


# ---- staging ----------------------------------------------------------------
# One upload is <id>.json (what it is), its master <id>.jpg, <id>.png or
# <id>.mp4, while it arrives <id>.upload, and while it is cut <id>.out/.

def staging_dir(cfg):
    d = cfg.backups / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_id():
    return secrets.token_hex(16)


def sweep(cfg, now=None):
    """Remove uploads older than a day. Run at startup and before each new
    upload, so abandoned ones never pile up."""
    d = cfg.backups / "staging"
    if not d.is_dir():
        return 0
    now = now or time.time()
    gone = 0
    for p in d.iterdir():
        try:
            old = now - os.lstat(p).st_mtime > EXPIRES
        except FileNotFoundError:
            continue
        if old:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p, ignore_errors=True)
            else:
                _unlink(p)
            gone += 1
    return gone


def _unlink(p):
    try:
        os.unlink(p)
    except FileNotFoundError:
        pass


def drop(cfg, sid):
    """Forget one upload: its record, its master and anything cut from it."""
    d = cfg.backups / "staging"
    for p in d.glob(sid + ".*"):
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            _unlink(p)


def write_meta(cfg, sid, meta):
    (staging_dir(cfg) / (sid + ".json")).write_text(json.dumps(meta), encoding="utf-8")


def staged(cfg, sid):
    """The record of one upload, with the path of its master, or a 404."""
    gone = ApiError(404, "not_found", "That upload is gone: it expired after a day or was already used. Upload the file again.")
    if not isinstance(sid, str) or not SID.match(sid):
        raise gone
    d = cfg.backups / "staging"
    try:
        meta = json.loads((d / (sid + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise gone
    master = d / ("%s.%s" % (sid, meta.get("ext")))
    if time.time() - meta.get("created", 0) > EXPIRES or not master.is_file():
        drop(cfg, sid)
        raise gone
    meta["master"] = master
    return meta


def out_dir(cfg, sid):
    """Where the finished files of one attach are cut, outside flow/assets."""
    d = staging_dir(cfg) / (sid + ".out")
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    return d


def stage_image(path, ctype, kind, dest_base):
    """Check an uploaded picture for its kind and keep a clean master beside
    it. Returns what the upload record keeps."""
    im, fmt = open_image(path, ctype)
    im = normalize(im)
    w, h = im.size
    if kind == "product-image" and min(w, h) < 1000:
        raise bad("A product photo needs at least 1000 px on its short side; this one is %dx%d px." % (w, h), "too_small")
    if kind == "banner" and (w < 2400 or h < 790):
        raise bad("A banner picture needs to be at least 2400 px wide and 790 px tall; this one is %dx%d px." % (w, h),
                  "too_small")
    if kind == "category-photo" and min(w, h) < 432:
        raise bad("A category photo needs at least 432 px on its short side; this one is %dx%d px." % (w, h), "too_small")
    if kind in ("cutout", "logo", "emblem"):
        if im.mode != "RGBA" or edge_clear(im) < 0.9:
            raise bad("This PNG has no transparent background: its edges are not see-through. Remove the background "
                      "(a painted checkerboard is not transparency) and upload it again.", "no_alpha")
        if kind == "cutout":
            cutout_fit(im)
        if kind == "logo" and w < 486:
            raise bad("A logo needs to be at least 486 px wide; this one is %d px." % w, "too_small")
        if kind == "emblem" and max(w, h) < 180:
            raise bad("The emblem needs at least 180 px on its long side; this one is %dx%d px." % (w, h), "too_small")
    if im.mode == "RGBA":
        ext = "png"
        im.save("%s.png" % dest_base, "PNG", compress_level=1)
    else:
        # the master is a working copy, cut again at attach time, so it is
        # kept close to lossless: quality 95 with full colour resolution
        ext = "jpg"
        im.save("%s.jpg" % dest_base, "JPEG", quality=95, subsampling=0)
    return {"ext": ext, "width": w, "height": h, "alpha": im.mode == "RGBA", "format": fmt}


def cutout_fit(im):
    """Where the object is and how it fits: a tall or square object stands in a
    204x240 box like the existing cut-outs; one clearly wider than tall (the
    gift boxes) is a wide cut-out, drawn across its circle, up to 354x154."""
    a = im.getchannel("A").point(lambda v: 255 if v >= 16 else 0)
    bbox = a.getbbox()
    if not bbox:
        raise bad("The picture is completely transparent.", "no_alpha")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    wide = w / h >= 1.3
    bw, bh = WIDE_BOX if wide else CUTOUT_BOX
    scale = min(bw / w, bh / h)
    if scale > 1:
        raise bad("The object in this cut-out is %dx%d px; it needs to fill a %dx%d px box without being enlarged."
                  % (w, h, bw, bh), "too_small")
    return bbox, wide, scale


# ---- cutting a master into the house sizes ----------------------------------

def _master(meta):
    im = Image.open(meta["master"])
    im.load()
    return im


def _jpeg(im, path):
    im.save(path, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return path


def _flat(im):
    """Alpha composited onto white, as the importers do for product frames."""
    if im.mode == "RGBA":
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.getchannel("A"))
        return flat
    return im.convert("RGB")


def _smaller(im, size):
    """Resize with the colour of see-through pixels kept out of the edges
    (premultiplied), so a cut-out gets no dark or white fringe."""
    if im.mode == "RGBA":
        return im.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
    return im.resize(size, Image.LANCZOS)


def crop_box(rect, size, aspect, need, what):
    """A crop sent as fractions of the picture, {x, y, w, h} from 0 to 1, as
    pixels. It is trimmed about its centre to the target's shape so nothing
    is ever stretched, and refused when it would have to be enlarged."""
    if rect is None:
        rect = {"x": 0, "y": 0, "w": 1, "h": 1}
    try:
        x, y, w, h = (float(rect[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        raise bad("Send the %s crop as x, y, w and h, fractions of the picture from 0 to 1." % what, "bad_crop")
    ok = all(math.isfinite(v) for v in (x, y, w, h)) and w > 0 and h > 0 and x >= 0 and y >= 0 \
        and x + w <= 1.0001 and y + h <= 1.0001
    if not ok:
        raise bad("The %s crop must lie inside the picture." % what, "bad_crop")
    W, H = size
    left, top, bw, bh = x * W, y * H, min(w, 1 - x) * W, min(h, 1 - y) * H
    if bw / bh > aspect:
        left += (bw - bh * aspect) / 2
        bw = bh * aspect
    else:
        top += (bh - bw / aspect) / 2
        bh = bw / aspect
    if bw < need - 1:
        raise bad("The %s crop is %d px wide; it needs at least %d px of the picture. Make the crop larger."
                  % (what, bw, need), "too_small")
    return (left, top, left + bw, top + bh)


def render_frame(meta, out):
    """tools/import_website_set.py resize(): flatten, centre-crop square, then
    1000 px and the 520 px card copy, quality 72, progressive."""
    im = _flat(_master(meta))
    w, h = im.size
    s = min(w, h)
    sq = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return {"": _jpeg(sq.resize((1000, 1000), Image.LANCZOS), out / "frame.jpg"),
            "-card": _jpeg(sq.resize((520, 520), Image.LANCZOS), out / "card.jpg")}


def render_banner(meta, crop_desktop, crop_phone, out):
    """Two separate crops of one picture: the 2400x790 desktop band and the
    1110x600 phone crop, which is usually centred on the product."""
    im = _flat(_master(meta))
    d = crop_box(crop_desktop, im.size, 2400 / 790, 2400, "desktop")
    p = crop_box(crop_phone, im.size, 1110 / 600, 1110, "phone")
    return {"desktop": _jpeg(im.resize((2400, 790), Image.LANCZOS, box=d), out / "desktop.jpg"),
            "phone": _jpeg(im.resize((1110, 600), Image.LANCZOS, box=p), out / "phone.jpg")}


def render_category(meta, crop, out):
    """A 432 px square; make_derivatives cuts the 216 px copy the circle shows."""
    im = _flat(_master(meta))
    if crop is None:
        w, h = im.size
        s = min(w, h)
        crop = {"x": (w - s) / 2 / w, "y": (h - s) / 2 / h, "w": s / w, "h": s / h}
    box = crop_box(crop, im.size, 1.0, 432, "square")
    return _jpeg(im.resize((432, 432), Image.LANCZOS, box=box), out / "category.jpg")


def render_cutout(meta, out):
    """Trimmed to the object and fitted like the existing cut-outs: standing
    on the bottom edge of a 204x240 canvas, or tight for a wide one. Then 256
    colours, as they are (7 to 21 KB)."""
    im = _master(meta).convert("RGBA")
    bbox, wide, scale = cutout_fit(im)
    obj = im.crop(bbox)
    size = (max(1, round(obj.width * scale)), max(1, round(obj.height * scale)))
    obj = _smaller(obj, size)
    if wide:
        canvas = obj
    else:
        canvas = Image.new("RGBA", CUTOUT_BOX, (0, 0, 0, 0))
        canvas.alpha_composite(obj, ((CUTOUT_BOX[0] - obj.width) // 2, CUTOUT_BOX[1] - obj.height))
    path = out / "cutout.png"
    canvas.quantize(256, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)
    return path, wide


def render_logo(meta, out):
    """The full-size lockup, trimmed to what is drawn. make_derivatives makes
    the 486 px copy the pages use; anything over 3200 px wide is brought down
    to that (today's lockups are 3149 px)."""
    im = _master(meta).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
    if im.width > 3200:
        im = _smaller(im, (3200, max(1, round(im.height * 3200 / im.width))))
    path = out / "logo.png"
    im.save(path, optimize=True)
    return path


def render_emblem(meta, out):
    """A square transparent PNG, 256 px like today's, centred on its square;
    tools/make_favicon.py makes the icons from it."""
    im = _master(meta).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
    s = max(im.size)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.alpha_composite(im, ((s - im.width) // 2, (s - im.height) // 2))
    if s > 256:
        sq = _smaller(sq, (256, 256))
    path = out / "emblem.png"
    sq.save(path, optimize=True)
    return path


# ---- names and copies -------------------------------------------------------

def rel(cfg, path):
    """A path under flow/ as the content and derivatives.json write it."""
    s = str(path)
    if not os.path.isabs(s):
        return s
    return os.path.relpath(s, str(cfg.flow)).replace(os.sep, "/")


def is_frame(name):
    """A product photo original, by the rule make_derivatives.py uses."""
    return bool(FRAME.match(name)) and not name.startswith("banner-") \
        and not name.endswith(tuple(s + ".jpg" for s in FRAME_COPIES))


def sized_copies(cfg, path):
    """The copies tools/make_derivatives.py writes for an original."""
    r = rel(cfg, path)
    folder, _, name = r.rpartition("/")
    img, cat = cfg.assets / "img", cfg.assets / "cat"
    if folder == "assets/img":
        m = re.fullmatch(r"(banner-\d+)(-phone)?\.jpg", name)
        if m:
            return [img / ("%s-phone-750.jpg" % m.group(1) if m.group(2) else "%s-1320.jpg" % m.group(1))]
        if is_frame(name):
            return [img / (name[:-4] + s + ".jpg") for s in ("-600", "-card-360", "-thumb")]
        if name in LOGOS.values():
            return [img / (name[:-4] + "-486.png")]
    if folder == "assets/cat" and name.endswith(".jpg") and not name.endswith("-216.jpg"):
        return [cat / (name[:-4] + "-216.jpg")]
    return []


def orphan_copies(cfg):
    """The sized copies make_derivatives sweeps because their original is gone
    (a re-import with fewer frames, or a file removed outside the admin). A
    media save runs make_derivatives, which deletes these; the transaction
    snapshots them so a failed build puts them back and the sweep is not
    reported as a file the build should not have changed."""
    out = []
    for folder, suffixes in ((cfg.assets / "img", ("-600", "-card-360", "-thumb")), (cfg.assets / "cat", ("-216",))):
        if not folder.is_dir():
            continue
        for suf in suffixes:
            for d in folder.glob("*" + suf + ".jpg"):
                if not (folder / (d.name[: -len(suf + ".jpg")] + ".jpg")).exists():
                    out.append(d)
    return out


def companions(cfg, path):
    """Every file made from an original: its sized copies, a frame's -card
    (written with it, not by make_derivatives), a film's poster and the
    emblem's icons. They are listed, trashed and restored with it."""
    r = rel(cfg, path)
    name = r.rpartition("/")[2]
    out = sized_copies(cfg, path)
    if r.startswith("assets/img/") and is_frame(name):
        out.insert(0, cfg.assets / "img" / (name[:-4] + "-card.jpg"))
    if r.startswith("assets/video/") and name.endswith(".mp4"):
        out.append(cfg.assets / "video" / (name[:-4] + ".jpg"))
    if r == "assets/img/" + EMBLEM:
        out += [cfg.flow / f for f in FAVICON_OUTPUTS]
    return out


def trash_names(cfg):
    """Paths waiting in the trash: a new file never takes one of their names,
    so restoring it later cannot collide."""
    out = set()
    for m in (cfg.backups / "trash").glob("*/manifest.json"):
        try:
            out.update(json.loads(m.read_text(encoding="utf-8")).get("files", []))
        except (OSError, ValueError):
            continue
    return out


def _taken(cfg, r, trashed):
    return r in trashed or os.path.lexists(str(cfg.flow / r))


def _names(cfg, folder, trashed):
    return os.listdir(str(cfg.flow / folder)) + [t.rpartition("/")[2] for t in trashed if t.startswith(folder + "/")]


def next_frame(cfg, pid):
    """<id>-<n>.jpg with n one above the highest on disk, referenced or not,
    so a published file nobody points at is never overwritten. Never 600:
    <id>-<n>-600.jpg is also the name of a copy."""
    trashed = trash_names(cfg)
    rx = re.compile(r"^%s-(\d+)\.jpg$" % re.escape(pid))
    n = max([int(m.group(1)) for m in map(rx.match, _names(cfg, "assets/img", trashed)) if m] + [0]) + 1
    while n == 600 or any(_taken(cfg, "assets/img/%s-%d%s.jpg" % (pid, n, s), trashed) for s in ("",) + FRAME_COPIES):
        n += 1
    return "%s-%d.jpg" % (pid, n)


def next_banner(cfg):
    trashed = trash_names(cfg)
    rx = re.compile(r"^banner-(\d+)(?:-phone)?(?:-\d+)?\.jpg$")
    return max([int(m.group(1)) for m in map(rx.match, _names(cfg, "assets/img", trashed)) if m] + [0]) + 1


def slug(text, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40].strip("-")
    return s or fallback


def free_name(cfg, folder, base, exts):
    """base, then base-2, base-3 and so on, until no file of that stem exists
    in folder under any of exts. A stem ending -216 would be taken for a
    category photo's copy, so it is never used."""
    trashed = trash_names(cfg)
    k, name = 1, base
    while name.endswith("-216") or any(_taken(cfg, "%s/%s%s" % (folder, name, e), trashed) for e in exts):
        k += 1
        name = "%s-%d" % (base, k)
    return name
