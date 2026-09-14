"""The media library: every published picture and film under flow/assets,
where the content uses it, whether its sized copies are current, and the
trash that removed files wait in.

Content is the only record of use: build.py and shop.js take every picture
and film path from it (DESIGN.md), apart from the two sources the
storefront's own tools read, which are listed in TOOL_SOURCES.
"""
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil

from PIL import Image

from . import media, schema, validate, video
from .errors import ApiError
from .service import field_for, flatten

FOLDERS = ("assets/img", "assets/cat", "assets/fam", "assets/video")
EXTS = (".jpg", ".png", ".mp4")
TOOL_SOURCES = {
    "assets/img/logo.png": "The gold logo tool (tools/make_gold_logo.py) draws the logos from it",
    "assets/img/" + media.EMBLEM: "The favicon tool (tools/make_favicon.py) makes the site icons from it",
}
TRASH_ID = re.compile(r"^\d{8}-\d{6}-\d{6}-[0-9a-f]{4}$")
_INFO = {}           # path -> (size, mtime_ns, info)
_MD5 = {}            # path -> (size, mtime_ns, md5)


def original_of(r):
    """The original a published path belongs to; a copy maps to its source."""
    r = r.split("?", 1)[0]
    folder, _, name = r.rpartition("/")
    if r == "favicon.ico" or r in media.FAVICON_OUTPUTS:
        return "assets/img/" + media.EMBLEM
    if folder == "assets/img":
        m = re.fullmatch(r"(banner-\d+)-1320\.jpg|(banner-\d+-phone)-750\.jpg", name)
        if m:
            return "assets/img/%s.jpg" % (m.group(1) or m.group(2))
        for logo in media.LOGOS.values():
            if name == logo[:-4] + "-486.png":
                return "assets/img/" + logo
        for s in ("-card-360", "-card", "-600", "-thumb"):
            if name.endswith(s + ".jpg") and media.is_frame(name[:-len(s + ".jpg")] + ".jpg"):
                return "assets/img/" + name[:-len(s + ".jpg")] + ".jpg"
    if folder == "assets/cat" and name.endswith("-216.jpg"):
        return "assets/cat/" + name[:-8] + ".jpg"
    if folder == "assets/fam" and name.endswith("-450.jpg"):
        return "assets/fam/" + name[:-8] + ".jpg"
    if folder == "assets/video" and name.endswith(".jpg"):
        return "assets/video/" + name[:-4] + ".mp4"
    return r


def kind_of(r):
    folder, _, name = r.rpartition("/")
    if folder == "assets/img":
        if name in media.LOGOS.values():
            return "logo"
        if name == media.EMBLEM:
            return "emblem"
        if re.fullmatch(r"banner-\d+(?:-phone)?\.jpg", name):
            return "banner"
        return "product-image" if media.is_frame(name) else "other"
    if folder == "assets/cat":
        return "cutout" if name.endswith(".png") else "category-photo"
    if folder == "assets/fam":
        return "family-photo"
    return "reel" if name.endswith(".mp4") else "other"


def _where(label, fields, ptr, data):
    """'Homepage: Find your scent., Picture' from a JSON pointer, using the
    schema's labels and, for list entries, the entry's own label."""
    f, parents = field_for(fields, ptr)
    if f is None:
        return "%s (%s)" % (label, ptr)
    idx = [int(s) for s in ptr.split("/") if s.isdigit()]
    bits = []
    for i, p in enumerate(parents):
        n = idx[i] if i < len(idx) else None
        name = None
        if i == 0 and n is not None and p.get("itemLabel"):
            item = validate.get(data, "%s/%d" % (p["path"], n))
            v = item.get(p["itemLabel"]) if isinstance(item, dict) else None
            name = " ".join(v.split()) if isinstance(v, str) and v.strip() else None
        bits.append(name or ("%s %d" % (p["label"], n + 1) if n is not None else p["label"]))
    bits.append(f["label"])
    return "%s: %s" % (label, ", ".join(bits))


def references(docs, products):
    """{original path: [{where, link}]} for every picture and film the content
    points at, sized copies counted as their original."""
    out = {}

    def add(path, where, link):
        o = original_of(path)
        entry = {"where": where, "link": link}
        if entry not in out.setdefault(o, []):
            out[o].append(entry)

    for pid, d in products.items():
        for i, n in enumerate(d.get("images") or []):
            if isinstance(n, str) and n:
                add("assets/img/" + n, "%s, photo %d" % (d.get("name") or pid, i + 1), "#/products/%s" % pid)
    res = schema.load()
    for name, data in docs.items():
        spec = res.get(name) or {}
        label = (spec.get("resource") or {}).get("label", name)
        fields = spec.get("fields", [])
        for ptr, v in flatten(data).items():
            if not isinstance(v, str):
                continue
            s = v.split("?", 1)[0]
            if not (s.startswith("assets/") or s == "favicon.ico"):
                continue
            where = _where(label, fields, ptr, data)
            add(s, where, "#/content/%s" % name)
            # build.py takes a slide's phone crop from its desktop picture's name
            m = re.fullmatch(r"assets/img/(banner-\d+)\.jpg", s)
            if m:
                add("assets/img/%s-phone.jpg" % m.group(1), where + " (phone crop)", "#/content/%s" % name)
    for p, why in TOOL_SOURCES.items():
        add(p, why, None)
    return out


def _stat_key(p):
    st = os.stat(p)
    return st.st_size, st.st_mtime_ns


def md5(p):
    key = _stat_key(p)
    c = _MD5.get(str(p))
    if not c or c[:2] != key:
        c = key + (hashlib.md5(p.read_bytes()).hexdigest(),)
        _MD5[str(p)] = c
    return c[2]


def info(p, ffprobe=None):
    """Bytes, width and height (and a film's length), cached by size and time."""
    key = _stat_key(p)
    c = _INFO.get(str(p))
    if c and c[:2] == key:
        return dict(c[2])
    out = {"bytes": key[0], "width": None, "height": None}
    if p.suffix == ".mp4":
        if ffprobe:
            out["width"], out["height"], out["duration"] = video.dimensions(ffprobe, p)
    else:
        try:
            with Image.open(p) as im:
                out["width"], out["height"] = im.size
        except Exception:        # a file Pillow cannot read still gets listed, without its size
            pass
    _INFO[str(p)] = key + (out,)
    return dict(out)


def published_files(cfg):
    """Every picture and film under the three media folders, as paths under flow/."""
    out = []
    for folder in FOLDERS:
        d = cfg.flow / folder
        if not d.is_dir():
            continue
        for name in sorted(os.listdir(str(d))):
            p = d / name
            if not name.startswith(".") and name.endswith(EXTS) and p.is_file() and not p.is_symlink():
                out.append("%s/%s" % (folder, name))
    return out


def copy_status(cfg, r, made):
    """ok, missing or stale for each file made from original r. The copies
    make_derivatives writes are stale when derivatives.json does not record
    them as made from the original's current bytes; the others (a frame's
    -card, a film's poster, the icons) can only be present or missing."""
    out = {"ok": [], "missing": [], "stale": []}
    derived = {media.rel(cfg, c) for c in media.sized_copies(cfg, r)}
    src = None
    for c in media.companions(cfg, r):
        cr = media.rel(cfg, c)
        if not c.is_file():
            out["missing"].append(cr)
        elif cr in derived:
            src = src or md5(cfg.flow / r)
            rec = made.get(cr) or [None, None]
            out["ok" if rec[0] == r and rec[1] == src else "stale"].append(cr)
        else:
            out["ok"].append(cr)
    return out


def library(cfg, docs, products, ffprobe=None, kind=None, unused=False):
    """The Files list: originals only, each with its copies grouped under it.
    A copy whose original is gone is listed on its own as an orphan, so it
    can be cleared away."""
    try:
        made = json.loads((cfg.flow / "tools" / "derivatives.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        made = {}
    files = published_files(cfg)
    present = set(files)
    refs = references(docs, products)
    items = []
    for r in files:
        o = original_of(r)
        if o != r and o in present:
            continue
        k = kind_of(r) if o == r else "orphan"
        used = refs.get(r, [])
        if (kind and k != kind) or (unused and used):
            continue
        item = {"path": r, "kind": k}
        item.update(info(cfg.flow / r, ffprobe))
        item.update(used_by=used, published=True,
                    copies=copy_status(cfg, r, made) if k != "orphan" else {"ok": [], "missing": [], "stale": []})
        items.append(item)
    return items


# ---- trash ------------------------------------------------------------------
# .backups/trash/<id>/manifest.json lists what was taken away; the files wait
# beside it at their own paths (assets/img/...), ready to be put back.

def new_trash(cfg, path, kind, files):
    """Copy files (paths under flow/) into a new trash entry. The caller
    removes the originals inside a store transaction and deletes the entry
    again if that transaction fails."""
    tid = "%s-%s" % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"), secrets.token_hex(2))
    tdir = cfg.backups / "trash" / tid
    tdir.mkdir(parents=True)
    for r in files:
        dst = tdir / r
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(cfg.flow / r), str(dst))
    man = {"trash_id": tid, "at": datetime.datetime.now().isoformat(timespec="seconds"),
           "path": path, "kind": kind, "files": files}
    (tdir / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return tid, tdir


def trash_entry(cfg, tid):
    if not isinstance(tid, str) or not TRASH_ID.match(tid):
        raise ApiError(404, "not_found", "Nothing in the trash has that id.")
    tdir = cfg.backups / "trash" / tid
    try:
        man = json.loads((tdir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ApiError(404, "not_found", "Nothing in the trash has that id.")
    files = man.get("files") or []
    # the manifest is ours, but it sits on disk: every name is checked again
    # before anything is copied back under flow/
    if not all(isinstance(f, str) and re.fullmatch(r"assets/(?:img|cat|video)/[a-z0-9][a-z0-9._-]*\.(?:jpg|png|mp4)", f)
               or f in media.FAVICON_OUTPUTS for f in files) or not files:
        raise ApiError(404, "not_found", "That trash entry is damaged and cannot be restored.")
    return man, tdir


def trash_list(cfg):
    out = []
    for m in sorted((cfg.backups / "trash").glob("*/manifest.json"), reverse=True):
        try:
            man = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        size = sum((m.parent / f).stat().st_size for f in man.get("files", []) if (m.parent / f).is_file())
        out.append({"trash_id": man.get("trash_id"), "at": man.get("at"), "path": man.get("path"),
                    "kind": man.get("kind"), "files": man.get("files", []), "bytes": size,
                    "blocked": [f for f in man.get("files", []) if (cfg.flow / f).exists()]})
    return out
