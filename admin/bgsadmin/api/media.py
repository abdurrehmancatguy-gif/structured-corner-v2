"""Media: upload, attach to the content, the library and the trash.

Uploading and attaching are two steps (docs/PLAN.md, API contract, Media):
the heavy checks and the re-encode run on the upload, outside any save; the
attach cuts the master into the house sizes and saves the files with the
content change in one store transaction, so a failed build takes away every
file it made and puts back every file it replaced.
"""
import copy
import shutil
import time

from .. import jobs, media, medialib, security, video
from .. import schema as schema_mod
from .. import validate
from ..errors import ApiError
from ..routes import Route
from ..service import saved
from ..store.jsonstore import rev_of
from .meta import schemas

MAX_REELS = 12
FIXED = tuple("assets/img/" + n for n in list(media.LOGOS.values()) + [media.EMBLEM])


def _body(req):
    return req.body if isinstance(req.body, dict) else {}


def _expect(expect, current):
    if not expect:
        raise ApiError(428, "rev_required", "Reload and try again: the request did not say which version it was editing.")
    if expect != current:
        raise ApiError(412, "stale_rev", "This changed since you opened it.", {"current_rev": current})


def _index(v, n, what):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < n:
        raise ApiError(422, "validation", "Pick one of the %s (0 to %d)." % (what, n - 1), {"index": v})
    return v


def _ctx(cfg, pending=()):
    return {"icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg),
            "img_dir": cfg.assets / "img", "pending_images": set(pending)}


# ---- upload -----------------------------------------------------------------

def stage(req):
    app, cfg = req.app, req.app.cfg
    kind = req.query.get("kind")
    media.check_upload(kind, req.content_type, req.body_length or 0)
    if kind == "reel":
        video.tool(app, "ffprobe")
        video.tool(app, "ffmpeg")
    d = media.staging_dir(cfg)
    media.sweep(cfg)
    sid = media.new_id()
    upload = d / (sid + ".upload")
    try:
        req.save_body(str(upload))
        if kind == "reel":
            meta = video.stage(app, upload, str(d / sid))
        else:
            meta = media.stage_image(upload, req.content_type, kind, str(d / sid))
        meta.update(kind=kind, content_type=req.content_type, created=time.time())
        media.write_meta(cfg, sid, meta)
    except BaseException:
        media.drop(cfg, sid)
        raise
    finally:
        if upload.exists():
            upload.unlink()
    out = {"staging_id": sid, "kind": kind, "width": meta["width"], "height": meta["height"],
           "expires_in": media.EXPIRES}
    if "duration" in meta:
        out["duration"] = meta["duration"]
    return 201, out


# ---- attach -----------------------------------------------------------------

def _attach(req, sid, reason, render, apply):
    """Cut the files (before the store lock is taken: a big picture takes a
    moment), then apply(txn, files, undo) inside one transaction. undo
    collects clean-ups for a failed save, such as a trash entry made for the
    file being replaced. The upload is forgotten once it is saved; after a
    failure it stays, so the owner can try again."""
    cfg = req.app.cfg
    out = media.out_dir(cfg, sid)
    undo = []
    try:
        files = render(out)
        with req.app.store.transaction(reason) as txn:
            apply(txn, files, undo)
    except BaseException:
        for fn in undo:
            fn()
        raise
    finally:
        shutil.rmtree(str(out), ignore_errors=True)
    media.drop(cfg, sid)
    return txn


def _trash_current(cfg, r, kind, undo):
    """A logo or the emblem keeps one fixed name, so the file in use goes to
    the trash (restorable from Files) before the new one takes its place."""
    files = [f for f in [r] + [media.rel(cfg, c) for c in media.companions(cfg, r)]
             if f not in media.FAVICON_OUTPUTS and (cfg.flow / f).is_file()]
    if not files:
        return None
    tid, tdir = medialib.new_trash(cfg, r, kind, files)
    undo.append(lambda: shutil.rmtree(str(tdir), ignore_errors=True))
    return tid


def attach_frame(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    pid = t.get("product")
    cur, rev = store.product(pid)
    _expect(expect, rev)
    count = len(cur.get("images") or [])
    pos = t.get("position", count)
    if isinstance(pos, bool) or not isinstance(pos, int) or not 0 <= pos <= count:
        raise ApiError(422, "validation", "The position must be from 0 to %d." % count, {"position": pos})
    state = {}

    def apply(txn, files, undo):
        products = txn.load("products")
        if pid not in products:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        _expect(expect, rev_of(products[pid]))
        name = media.next_frame(cfg, pid)
        new = copy.deepcopy(products[pid])
        new["images"] = list(new.get("images") or [])
        new["images"].insert(min(pos, len(new["images"])), name)
        errors, warnings = validate.product(pid, new, products, schemas()["products"]["fields"], _ctx(cfg, [name]))
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        products[pid] = new
        txn.put("products", products)
        card = name[:-4] + "-card.jpg"
        txn.add_file(cfg.assets / "img" / name, files[""])
        txn.add_file(cfg.assets / "img" / card, files["-card"])
        state.update(id=pid, rev=rev_of(new), data=new, warnings=warnings,
                     paths=["assets/img/" + name, "assets/img/" + card])

    txn = _attach(req, sid, "photo for %s" % pid, lambda out: media.render_frame(meta, out), apply)
    return saved(req.app, txn, **state)


def attach_banner(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    home, rev = store.doc("home")
    _expect(expect, rev)
    slide = _index(t.get("slide"), len(home.get("hero_slides") or []), "banner slides")
    state = {}

    def apply(txn, files, undo):
        doc = txn.load("home")
        _expect(expect, store.doc("home")[1])
        n = media.next_banner(cfg)
        desk, phone = "banner-%d.jpg" % n, "banner-%d-phone.jpg" % n
        doc["hero_slides"][slide]["image"] = "assets/img/" + desk
        txn.put("home", doc)
        txn.add_file(cfg.assets / "img" / desk, files["desktop"])
        txn.add_file(cfg.assets / "img" / phone, files["phone"])
        state["paths"] = ["assets/img/" + desk, "assets/img/" + phone]

    render = lambda out: media.render_banner(meta, t.get("crop_desktop"), t.get("crop_phone"), out)  # noqa: E731
    txn = _attach(req, sid, "banner for slide %d" % (slide + 1), render, apply)
    return saved(req.app, txn, name="home", rev=store.doc("home")[1], **state)


def _category(store, expect, t):
    nav, rev = store.doc("navigation")
    _expect(expect, rev)
    return _index(t.get("index"), len(nav.get("categories") or []), "categories")


def _cat_base(c):
    """The file's stem: the category key from its link, else its label."""
    href = c.get("href") or ""
    key = href.split("cat=", 1)[1].split("&")[0] if "cat=" in href else c.get("label")
    return media.slug(key, "category")


def attach_category(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    i = _category(store, expect, t)
    state = {}

    def apply(txn, path, undo):
        nav = txn.load("navigation")
        _expect(expect, store.doc("navigation")[1])
        c = nav["categories"][i]
        name = media.free_name(cfg, "assets/cat", _cat_base(c), (".jpg", "-216.jpg", ".png"))
        # the circle shows the 216 px copy make_derivatives cuts from it
        c["image"] = "assets/cat/%s-216.jpg" % name
        c.pop("cutout", None)
        txn.put("navigation", nav)
        txn.add_file(cfg.assets / "cat" / (name + ".jpg"), path)
        state["paths"] = ["assets/cat/%s.jpg" % name, "assets/cat/%s-216.jpg" % name]

    txn = _attach(req, sid, "photo for category %d" % (i + 1), lambda out: media.render_category(meta, t.get("crop"), out), apply)
    return saved(req.app, txn, name="navigation", rev=store.doc("navigation")[1], **state)


def attach_cutout(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    i = _category(store, expect, t)
    state = {}

    def apply(txn, res, undo):
        path, wide = res
        nav = txn.load("navigation")
        _expect(expect, store.doc("navigation")[1])
        c = nav["categories"][i]
        name = media.free_name(cfg, "assets/cat", _cat_base(c), (".jpg", "-216.jpg", ".png"))
        c["image"] = "assets/cat/%s.png" % name
        c["cutout"] = "wide" if wide else True
        txn.put("navigation", nav)
        txn.add_file(cfg.assets / "cat" / (name + ".png"), path)
        state.update(paths=["assets/cat/%s.png" % name], cutout=c["cutout"])

    txn = _attach(req, sid, "cut-out for category %d" % (i + 1), lambda out: media.render_cutout(meta, out), apply)
    return saved(req.app, txn, name="navigation", rev=store.doc("navigation")[1], **state)


def attach_logo(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    variant = t.get("variant")
    if variant not in media.LOGOS:
        raise ApiError(422, "validation", "Say which logo: dark (the header) or light (the footer).")
    _expect(expect, store.doc("settings")[1])
    r = "assets/img/" + media.LOGOS[variant]
    state = {}

    def apply(txn, path, undo):
        _expect(expect, store.doc("settings")[1])
        state["trashed"] = _trash_current(cfg, r, "logo", undo)
        txn.add_file(cfg.flow / r, path)
        state["paths"] = [r, media.rel(cfg, media.sized_copies(cfg, r)[0])]

    txn = _attach(req, sid, "%s logo" % variant, lambda out: media.render_logo(meta, out), apply)
    return saved(req.app, txn, name="settings", rev=store.doc("settings")[1], **state)


def attach_emblem(req, sid, meta, t, expect):
    store, cfg = req.app.store, req.app.cfg
    _expect(expect, store.doc("settings")[1])
    r = "assets/img/" + media.EMBLEM
    state = {}

    def apply(txn, path, undo):
        _expect(expect, store.doc("settings")[1])
        state["trashed"] = _trash_current(cfg, r, "emblem", undo)
        txn.add_file(cfg.flow / r, path)
        for f in media.FAVICON_OUTPUTS:
            txn.snapshot(cfg.flow / f)
        txn.run_tool("favicon")
        state["paths"] = [r] + list(media.FAVICON_OUTPUTS)

    txn = _attach(req, sid, "emblem and site icons", lambda out: media.render_emblem(meta, out), apply)
    return saved(req.app, txn, name="settings", rev=store.doc("settings")[1], **state)


def _reel_job(app, sid, meta, index, pid, before, log):
    """The film transcodes on a job thread; then one transaction places the
    film and its poster and points the homepage entry at them."""
    cfg, store = app.cfg, app.store
    out = media.out_dir(cfg, sid)
    state = {}
    try:
        film, still = video.transcode(app, meta["master"], out, log)
        log("Saving the film to the homepage.")
        for attempt in range(40):
            try:
                with store.transaction("film for %s" % pid) as txn:
                    home = txn.load("home")
                    if home.get("reels") != before:
                        raise ApiError(412, "stale_rev", "The homepage films changed while this one was being prepared. "
                                       "Attach it again.", {"current_rev": store.doc("home")[1]})
                    slug = media.free_name(cfg, "assets/video", pid, (".mp4", ".jpg"))
                    item = {"product": pid, "video": "assets/video/%s.mp4" % slug, "still": "assets/video/%s.jpg" % slug}
                    items = home.setdefault("reels", {}).setdefault("items", [])
                    if index < len(items):
                        items[index] = item
                    else:
                        items.append(item)
                    txn.put("home", home)
                    txn.add_file(cfg.flow / item["video"], film)
                    txn.add_file(cfg.flow / item["still"], still)
                    state["paths"] = [item["video"], item["still"]]
                break
            except ApiError as e:
                # another save holds the store for a moment: wait for it
                if e.code != "busy" or attempt == 39:
                    raise
                time.sleep(0.5)
    finally:
        shutil.rmtree(str(out), ignore_errors=True)
    media.drop(cfg, sid)
    build = txn.result["build"] if txn.result else None
    app.note_build(build)
    return dict(state, name="home", rev=store.doc("home")[1], build=build)


def attach_reel(req, sid, meta, t, expect):
    app, store = req.app, req.app.store
    video.tool(app, "ffmpeg")
    home, rev = store.doc("home")
    _expect(expect, rev)
    items = (home.get("reels") or {}).get("items") or []
    index = t.get("index", len(items))
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= len(items):
        raise ApiError(422, "validation", "The film's place must be from 0 to %d." % len(items), {"index": index})
    if index == len(items) and len(items) >= MAX_REELS:
        raise ApiError(422, "validation", "The row holds at most %d films. Replace one instead." % MAX_REELS)
    pid = t.get("product")
    if not isinstance(pid, str) or pid not in store.products()[0]:
        raise ApiError(422, "validation", "Pick the product the film links to.", {"product": pid})
    if jobs.running("reel"):
        raise ApiError(423, "busy", "Another film is still being prepared. Try again when it is done.", {"operation": "film"})
    before = copy.deepcopy(home.get("reels"))
    job = jobs.start("reel", lambda log: _reel_job(app, sid, meta, index, pid, before, log))
    return 202, {"job": job.id, "state": job.state}


def attach_family(req, sid, meta, t, expect):
    """A scent family tile's photograph: a new file in assets/fam named after
    the family, and pages.json index.families.<slug>.image pointing at it.
    The photo it replaces stays in Files until it is moved to the trash."""
    store, cfg = req.app.store, req.app.cfg
    pages, rev = store.doc("pages")
    _expect(expect, rev)
    fams = (pages.get("index") or {}).get("families") or {}
    slug = t.get("family")
    if not isinstance(slug, str) or slug not in fams:
        raise ApiError(422, "validation", "Pick one of the scent families: %s." % ", ".join(fams), {"family": slug})
    state = {}

    def apply(txn, path, undo):
        doc = txn.load("pages")
        _expect(expect, store.doc("pages")[1])
        name = media.free_name(cfg, "assets/fam", media.slug(slug, "family"), (".jpg", "-450.jpg"))
        fam = doc["index"]["families"][slug]
        if not isinstance(fam, dict):
            fam = doc["index"]["families"][slug] = {"label": fam}
        fam["image"] = "assets/fam/%s.jpg" % name
        txn.put("pages", doc)
        txn.add_file(cfg.assets / "fam" / (name + ".jpg"), path)
        state["paths"] = ["assets/fam/%s.jpg" % name, "assets/fam/%s-450.jpg" % name]

    txn = _attach(req, sid, "photo for the %s tile" % slug,
                  lambda out: media.render_family(meta, t.get("crop"), out), apply)
    return saved(req.app, txn, name="pages", rev=store.doc("pages")[1], **state)


ATTACH = {"product-image": attach_frame, "banner": attach_banner, "category-photo": attach_category,
          "family-photo": attach_family, "cutout": attach_cutout, "logo": attach_logo, "emblem": attach_emblem,
          "reel": attach_reel}


def attach(req):
    body = _body(req)
    target = body.get("target")
    if not isinstance(target, dict) or target.get("kind") not in ATTACH:
        raise ApiError(400, "bad_request", "Say where the upload goes: target.kind is one of %s." % ", ".join(ATTACH))
    sid = body.get("staging_id")
    meta = media.staged(req.app.cfg, sid)
    if meta["kind"] != target["kind"]:
        raise ApiError(422, "validation", "This upload was checked as a %s, so it cannot be used as a %s. Upload it again for that."
                       % (media.LABELS.get(meta["kind"], meta["kind"]), media.LABELS[target["kind"]]))
    return ATTACH[target["kind"]](req, sid, meta, target, body.get("expect_rev"))


# ---- library and trash ------------------------------------------------------

def list_media(req):
    store = req.app.store
    products, _ = store.products()
    docs = {n: store.doc(n)[0] for n in schema_mod.document_names()}
    unused = (req.query.get("unused") or "") in ("1", "true", "yes")
    items = medialib.library(req.app.cfg, docs, products, req.app.probes.get("ffprobe"),
                             req.query.get("kind") or None, unused)
    return {"items": items}


def trash(req):
    app, cfg, store = req.app, req.app.cfg, req.app.store
    r = _body(req).get("path")
    if not isinstance(r, str) or security.safe_join(cfg.flow, r) is None or r not in medialib.published_files(cfg):
        raise ApiError(404, "not_found", "There is no published picture or film at that path.")
    o = medialib.original_of(r)
    if o != r and (cfg.flow / o).is_file():
        raise ApiError(422, "validation", "That is a copy made from %s. Trash the original and its copies go with it." % o,
                       {"original": o})
    kind = medialib.kind_of(r) if o == r else "orphan"
    state, made = {}, []
    try:
        with store.transaction("trash %s" % r) as txn:
            docs = {n: txn.load(n) for n in schema_mod.document_names()}
            used = medialib.references(docs, txn.load("products")).get(r)
            if used:
                raise ApiError(409, "referenced", "This file is in use. Take it out of these places first.", {"refs": used})
            files = [r] + ([media.rel(cfg, c) for c in media.companions(cfg, r) if c.is_file()] if o == r else [])
            tid, tdir = medialib.new_trash(cfg, r, kind, files)
            made.append(tdir)
            for f in files:
                txn.remove_file(cfg.flow / f)
            state.update(trash_id=tid, files=files)
    except BaseException:
        for d in made:
            shutil.rmtree(str(d), ignore_errors=True)
        raise
    return saved(app, txn, **state)


def list_trash(req):
    return {"items": medialib.trash_list(req.app.cfg)}


def restore(req):
    app, cfg, store = req.app, req.app.cfg, req.app.store
    man, tdir = medialib.trash_entry(cfg, _body(req).get("trash_id"))
    r, files = man.get("path"), man["files"]
    if not all((tdir / f).is_file() for f in files):
        raise ApiError(404, "not_found", "That trash entry is missing some of its files and cannot be restored.")
    state, undo = {}, []
    try:
        with store.transaction("restore %s" % r) as txn:
            taken = [f for f in files if (cfg.flow / f).exists()]
            if taken and r not in FIXED:
                raise ApiError(409, "exists", "A file with the same name is on the site now (%s). Trash that one first."
                               % ", ".join(taken), {"paths": taken})
            if taken:
                state["trashed"] = _trash_current(cfg, r, man.get("kind"), undo)
            for f in files:
                txn.add_file(cfg.flow / f, tdir / f)
            if r == "assets/img/" + media.EMBLEM:
                for f in media.FAVICON_OUTPUTS:
                    txn.snapshot(cfg.flow / f)
                txn.run_tool("favicon")
            state["restored"] = files
    except BaseException:
        for fn in undo:
            fn()
        raise
    shutil.rmtree(str(tdir), ignore_errors=True)
    return saved(app, txn, **state)


ROUTES = [
    Route("GET", r"media", list_media),
    Route("POST", r"media/staging", stage, body="raw", limit=media.LARGEST, types=media.ROUTE_TYPES),
    Route("POST", r"media/attach", attach, body="json"),
    Route("GET", r"media/trash", list_trash),
    Route("POST", r"media/trash", trash, body="json"),
    Route("POST", r"media/restore", restore, body="json"),
]
