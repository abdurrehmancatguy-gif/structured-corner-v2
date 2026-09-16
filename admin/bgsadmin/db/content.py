"""The content tables as the PostgreSQL store and dbtool use them:
everything read in one statement, the export (the exact bytes each
flow/content file is written with), a save's changes written with who and
why, the file bases, and the audit row every change commits with.

Bodies are written compact and read back as text, parsed by Python's json:
psycopg's json loaders are never used, so the key order and the spelling of
every value are the file's. Products are exported in file order (pos), which
is not the shop's order: a reorder rewrites "order" and moves no product in
the file.
"""
import json
import uuid

import psycopg

from ..jsonutil import canonical
from ..store.base import content_names

READ = ("SELECT s.version, "
        "(SELECT coalesce(json_agg(json_build_array(p.id, p.pos, p.body) ORDER BY p.pos), '[]'::json) "
        "FROM bgs.products AS p)::text, "
        "(SELECT coalesce(json_object_agg(d.key, d.body), '{}'::json) FROM bgs.documents AS d)::text, "
        "(SELECT coalesce(json_object_agg(f.name, json_build_array(f.file_sha, f.export_sha)), '{}'::json) "
        "FROM bgs.content_files AS f)::text "
        "FROM bgs.content_state AS s")

# What the database's reference checks found missing, after a refusal.
DANGLING = ("SELECT r.resource, r.owner_id, r.ptr, r.product_id FROM bgs.product_refs AS r "
            "WHERE NOT EXISTS (SELECT 1 FROM bgs.products AS p WHERE p.id = r.product_id) "
            "ORDER BY r.resource, r.owner_id, r.ptr")


def compact(obj):
    """How a body is stored: the same data as the file, without the spaces."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class State:
    """The content as one statement read it."""

    def __init__(self, version, products, positions, docs, bases):
        self.version = version        # bgs.content_state: moves with every write, from anywhere
        self.products = products      # {id: data}, in file order
        self.positions = positions    # {id: pos}
        self.docs = docs              # {name: data}
        self.bases = bases            # {name: (file_sha, export_sha)} from bgs.content_files
        self._exports = None

    def data(self, name):
        return self.products if name == "products" else self.docs[name]

    @property
    def exports(self):
        """{name: bytes}: each content file as the database writes it, in
        content_names() order."""
        if self._exports is None:
            out = {}
            for n in content_names():
                if n == "products":
                    out[n] = canonical(self.products)
                elif n in self.docs:
                    out[n] = canonical(self.docs[n])
            self._exports = out
        return self._exports


def read(cur):
    """The whole content in one statement, so one snapshot."""
    version, prods, docs, bases = cur.execute(READ).fetchone()
    products, positions = {}, {}
    for pid, pos, body in json.loads(prods):
        products[pid] = body
        positions[pid] = pos
    return State(version, products, positions, json.loads(docs),
                 {k: tuple(v) for k, v in json.loads(bases).items()})


def begin(cur, txn, actor, reason, confirmed=()):
    """Who and why for every change this transaction makes (the triggers
    refuse a change without them), and the guarded fields the owner
    confirmed, as "<id>/<field>" (store.base.CONFIRMED)."""
    cur.execute("SELECT set_config('bgs.txn', %s, true), set_config('bgs.actor', %s, true), "
                "set_config('bgs.reason', %s, true), set_config('bgs.confirmed', %s, true)",
                (str(txn), actor, (reason or "a save")[:200], ",".join(confirmed)))


def lock_version(cur):
    """The content version, its row locked until this transaction ends: a
    change from psql waits for this one, or this one gives up after
    lock_timeout (55P03)."""
    return cur.execute("SELECT bgs.lock_content_state()").fetchone()[0]


def _run(cur, where, sql, params):
    """One write; a refusal is tagged with (resource, product id) it was
    writing, so a bulk save's answer can say which product."""
    try:
        cur.execute(sql, params)
    except psycopg.Error as e:
        try:
            e.bgs_where = where
        except AttributeError:
            pass
        raise


def write_changes(cur, state, products=None, docs=None):
    """Write what differs from state: products (the whole dict, in its new
    file order) row by row, and whole documents. The unique pos and order
    are checked at commit, so moving products around needs no juggling.
    Returns the number of rows written."""
    n = 0
    if products is not None:
        for pid in state.products:
            if pid not in products:
                _run(cur, ("products", pid), "DELETE FROM bgs.products WHERE id = %s", (pid,))
                n += 1
        for pos, (pid, data) in enumerate(products.items(), 1):
            body, where = compact(data), ("products", pid)
            if pid not in state.products:
                _run(cur, where, "INSERT INTO bgs.products (id, pos, body) VALUES (%s, %s, %s::json)", (pid, pos, body))
                n += 1
                continue
            same, moved = body == compact(state.products[pid]), state.positions[pid] != pos
            if not same and moved:
                _run(cur, where, "UPDATE bgs.products SET pos = %s, body = %s::json WHERE id = %s", (pos, body, pid))
            elif not same:
                _run(cur, where, "UPDATE bgs.products SET body = %s::json WHERE id = %s", (body, pid))
            elif moved:
                _run(cur, where, "UPDATE bgs.products SET pos = %s WHERE id = %s", (pos, pid))
            else:
                continue
            n += 1
    for name, data in (docs or {}).items():
        body = compact(data)
        if body != compact(state.docs[name]):
            _run(cur, (name, None), "UPDATE bgs.documents SET body = %s::json WHERE key = %s", (body, name))
            n += 1
    return n


def set_bases(cur, bases):
    """Record, per file, the sha256 of its bytes and of the database's export
    when the two last agreed."""
    for name, (f, e) in bases.items():
        cur.execute("INSERT INTO bgs.content_files AS c (name, file_sha, export_sha) VALUES (%s, %s, %s) "
                    "ON CONFLICT (name) DO UPDATE SET file_sha = EXCLUDED.file_sha, export_sha = EXCLUDED.export_sha, "
                    "updated_at = now() WHERE (c.file_sha, c.export_sha) IS DISTINCT FROM "
                    "(EXCLUDED.file_sha, EXCLUDED.export_sha)", (name, f, e))


def audit(cur, txn, actor, action, resources, ok=True, build_ms=None, problems=()):
    """The transaction's bgs.audit_log row. A change commits only with an ok
    row for its bgs.txn (a deferred check), which is also how recover()
    learns, after a crash during COMMIT, whether the save was kept."""
    cur.execute("INSERT INTO bgs.audit_log (txn, actor, action, resources, ok, build_ms, problems) "
                "VALUES (%s, %s, %s, %s::text[], %s, %s, %s::jsonb)",
                (str(txn), actor, (action or "a save")[:200], list(resources), bool(ok), build_ms,
                 json.dumps([str(p) for p in problems], ensure_ascii=False)))


def dangling(cur):
    """[(resource, owner id, pointer, product id)] naming a product that
    does not exist."""
    return [tuple(r) for r in cur.execute(DANGLING).fetchall()]


def refusal(name, pid, e):
    d = e.diag
    return {"name": name, "id": pid, "sqlstate": e.sqlstate, "constraint": d.constraint_name,
            "message": d.message_primary or str(e).strip().splitlines()[0], "detail": d.message_detail}


def load(cur, files, actor, reason="migrate: take flow/content"):
    """Put the parsed content (files: {name: data}) into empty tables, each
    row in a savepoint of its own so every refusal is listed rather than the
    first. The deferred checks (a reference to a product that does not
    exist, a repeated position or order) run once every row is in. Returns
    (txn, refusals)."""
    txn = uuid.uuid4()
    begin(cur, txn, actor, reason)
    out = []
    for name in content_names():
        rows = list(files[name].items()) if name == "products" else [(None, files[name])]
        for pos, (pid, data) in enumerate(rows, 1):
            cur.execute("SAVEPOINT bgs_row")
            try:
                if name == "products":
                    cur.execute("INSERT INTO bgs.products (id, pos, body) VALUES (%s, %s, %s::json)",
                                (pid, pos, compact(data)))
                else:
                    cur.execute("INSERT INTO bgs.documents (key, body) VALUES (%s, %s::json)", (name, compact(data)))
                cur.execute("RELEASE SAVEPOINT bgs_row")
            except psycopg.Error as e:
                cur.execute("ROLLBACK TO SAVEPOINT bgs_row")
                out.append(refusal(name, pid, e))
    audit(cur, txn, actor, "migrate", content_names())
    cur.execute("SAVEPOINT bgs_row")
    try:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("RELEASE SAVEPOINT bgs_row")
    except psycopg.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT bgs_row")
        missing = dangling(cur)
        if missing:
            for res, owner, ptr, target in missing:
                out.append({"name": res, "id": None if owner == "_" else owner, "sqlstate": "23503",
                            "constraint": "product_refs_target", "detail": None,
                            "message": "%s names the product %s, which does not exist" % (ptr, target)})
        else:
            out.append(refusal("", None, e))
    return txn, out
