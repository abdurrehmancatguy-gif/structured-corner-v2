"""The admin's PostgreSQL side: the numbered migrations and their runner
(migrate.py), connections and their checks (connect.py), the content tables
(content.py) and how the database's refusals become the API's answers
(errors.py).

Only PostgreSQL mode imports this package, because it needs psycopg: the
JSON store, the API modules and the app never import it, so JSON mode runs
on the standard library (test_plumbing checks that). The entry point for the
owner is admin/dbtool.py.
"""
