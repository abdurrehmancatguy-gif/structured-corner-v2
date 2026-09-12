"""The storage interface every store implements.

build.py keeps reading flow/content/*.json, now and after PostgreSQL: those
files are the build input and, in git, the record of what went live. A store
is the editing side of that; the PostgreSQL one will write the same files on
export. Validation, locked fields and referential checks live above the store
(validate.py, the API modules), so both stores get identical rules.

    doc(name)                    -> (data, rev)       settings, copy, home, navigation
    products()                   -> (dict, collection_rev)
    product(id)                  -> (data, rev)       404 ApiError when missing
    external_changes()           -> [name, ...]       changed on disk since the admin last saw them
    transaction(reason)          -> context manager yielding a Txn; one writer at a time (423 busy)

    Txn.load(name)               -> a private, mutable copy of a document or of the products dict
    Txn.put(name, data)          -> stage a whole document
    Txn.result                   -> {"changed": [...], "build": {...}} after commit

A transaction stages everything in memory; nothing touches disk until the
block ends without an exception. Then the store writes atomically, rebuilds
the site and commits, or puts every file back byte for byte and raises a 422
build_failed with the build's problems.
"""


class ContentStore:
    def doc(self, name):
        raise NotImplementedError

    def products(self):
        raise NotImplementedError

    def product(self, pid):
        raise NotImplementedError

    def external_changes(self):
        raise NotImplementedError

    def transaction(self, reason):
        raise NotImplementedError
