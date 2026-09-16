-- 001_foundation.sql
--
-- The admin's tables in the owner's database, and the rules the database
-- itself holds the content to. Each product and each document is kept as the
-- exact JSON text its file holds: a json column keeps key order and number
-- spelling, so the export is the file byte for byte. A jsonb copy and a few
-- generated columns are what the checks read. A change made in psql passes
-- the same checks and must say who and why, in the same transaction:
--   SELECT set_config('bgs.txn', '<uuid>', true), set_config('bgs.actor', '<who>', true),
--          set_config('bgs.reason', '<why>', true);
-- and it commits only with its bgs.audit_log row.
--
-- Applied by admin/bgsadmin/db/migrate.py as the database owner (bgs_corner),
-- in one transaction with its schema_migrations row.

CREATE SCHEMA bgs;

CREATE TABLE bgs.schema_migrations (
  version    integer PRIMARY KEY CONSTRAINT schema_migrations_version CHECK (version > 0),
  name       text NOT NULL CONSTRAINT schema_migrations_name CHECK (name ~ '^[0-9]{3}_[a-z0-9_]+[.]sql$'),
  sha256     text NOT NULL CONSTRAINT schema_migrations_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  applied_at timestamptz NOT NULL DEFAULT now(),
  applied_by text NOT NULL
);

-- The one checkout this database belongs to. The admin and dbtool refuse any
-- other, so a test clone can never export from or into the owner's database.
CREATE TABLE bgs.store_meta (
  one       boolean PRIMARY KEY DEFAULT true CONSTRAINT store_meta_one_row CHECK (one),
  app       text NOT NULL CONSTRAINT store_meta_app CHECK (app = 'bgs-corner-admin'),
  repo_path text NOT NULL CONSTRAINT store_meta_repo_path CHECK (repo_path ~ '^/' AND length(repo_path) <= 1024),
  bound_at  timestamptz NOT NULL DEFAULT now(),
  bound_by  text NOT NULL
);

-- products (one row per product) and the documents, each one file in flow/content.
CREATE TABLE bgs.resources (
  name     text PRIMARY KEY CONSTRAINT resources_name_format CHECK (name ~ '^[a-z]{1,30}$'),
  kind     text NOT NULL CONSTRAINT resources_kind CHECK (kind IN ('collection', 'document')),
  position integer NOT NULL UNIQUE CONSTRAINT resources_position CHECK (position > 0)
);
INSERT INTO bgs.resources (name, kind, position) VALUES
  ('products', 'collection', 1), ('settings', 'document', 2), ('copy', 'document', 3), ('home', 'document', 4),
  ('navigation', 'document', 5), ('pages', 'document', 6), ('quiz', 'document', 7), ('translations', 'document', 8);

-- Where the product-ref and product-refs fields are (* for each item of a list).
CREATE TABLE bgs.ref_fields (
  resource text NOT NULL REFERENCES bgs.resources (name),
  ptr      text NOT NULL CONSTRAINT ref_fields_ptr CHECK (ptr ~ '^(/([a-z0-9_]+|[*]))+$'),
  PRIMARY KEY (resource, ptr)
);
INSERT INTO bgs.ref_fields (resource, ptr) VALUES
  ('products', '/related/*'), ('home', '/reels/items/*/product'), ('quiz', '/profiles/*/product'),
  ('pages', '/index/discovery_band/product');

-- Payments, VAT, cash on delivery and the other locked settings, with the one
-- value each may hold. Only a migration changes a row here, together with
-- settings in the same transaction; the admin's own role may only read it.
CREATE TABLE bgs.locked_values (
  resource text NOT NULL REFERENCES bgs.resources (name),
  ptr      text NOT NULL CONSTRAINT locked_values_ptr CHECK (ptr ~ '^(/[a-z0-9_]+)+$'),
  value    jsonb NOT NULL,
  reason   text NOT NULL,
  PRIMARY KEY (resource, ptr)
);
INSERT INTO bgs.locked_values (resource, ptr, value, reason) VALUES
  ('settings', '/store/currency', '"AED"', 'The shop sells in one currency.'),
  ('settings', '/store/vat_rate_percent', '5', 'Checkout and payments are changed in code.'),
  ('settings', '/store/vat_inclusive', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/store/cod_max_order', '300', 'Checkout and payments are changed in code.'),
  ('settings', '/store/cod_fee', '8', 'Checkout and payments are changed in code.'),
  ('settings', '/payments/card', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/payments/apple_pay', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/payments/tabby', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/payments/tamara', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/payments/cod', 'true', 'Checkout and payments are changed in code.'),
  ('settings', '/analytics/ga4_id', '""', 'Tracking scripts arrive with login.'),
  ('settings', '/analytics/meta_pixel_id', '""', 'Tracking scripts arrive with login.'),
  ('settings', '/analytics/tiktok_pixel_id', '""', 'Tracking scripts arrive with login.'),
  ('settings', '/languages/english', 'true', 'The shop is written in English.');

-- ---- helpers the checks use -------------------------------------------------
-- Every function a CHECK or a generated column calls names its schema, so a
-- pg_restore (which runs with an empty search_path) rebuilds the tables.

-- A JSON number as Python's int would read it; null for anything else (true is not 1).
CREATE FUNCTION bgs.json_int(v jsonb) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT CASE WHEN jsonb_typeof(v) IS DISTINCT FROM 'number' THEN NULL
                  WHEN scale(v::numeric) <> 0 THEN NULL
                  WHEN v::numeric NOT BETWEEN -2147483648 AND 2147483647 THEN NULL
                  ELSE v::numeric::integer END $$;

-- Python's truthiness for a JSON value: null, false, 0, "", [] and {} are false.
CREATE FUNCTION bgs.truthy(v jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT CASE WHEN v IS NULL THEN false
                  WHEN jsonb_typeof(v) = 'number' THEN v::numeric <> 0
                  ELSE v NOT IN ('null'::jsonb, 'false'::jsonb, '""'::jsonb, '[]'::jsonb, '{}'::jsonb) END $$;

-- The stored text, read before jsonb sees it: no key twice in one object
-- (jsonb would keep the last one silently), no deeper than the API accepts
-- (jsonutil.MAX_DEPTH), and every number a plain integer literal (no field
-- holds a fraction; 5.0 and 5e0 are floats to Python).
CREATE FUNCTION bgs.json_sane(j json, depth integer DEFAULT 0) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog
AS $$
DECLARE
  t text := json_typeof(j);
  v json;
  n integer;
  u integer;
BEGIN
  IF depth > 20 THEN
    RETURN false;
  END IF;
  IF t = 'object' THEN
    SELECT count(*), count(DISTINCT k) INTO n, u FROM json_object_keys(j) AS k;
    IF n <> u THEN
      RETURN false;
    END IF;
    FOR v IN SELECT value FROM json_each(j) LOOP
      IF NOT bgs.json_sane(v, depth + 1) THEN
        RETURN false;
      END IF;
    END LOOP;
  ELSIF t = 'array' THEN
    FOR v IN SELECT value FROM json_array_elements(j) LOOP
      IF NOT bgs.json_sane(v, depth + 1) THEN
        RETURN false;
      END IF;
    END LOOP;
  ELSIF t = 'number' THEN
    RETURN btrim(j::text, ' ' || chr(9) || chr(10) || chr(13)) ~ '^-?(0|[1-9][0-9]*)$';
  END IF;
  RETURN true;
END $$;

-- The text rule every key and string obeys, whatever field holds it: no < or >
-- (the pages would read them as code), no control character but a line break,
-- neither long dash, and no '%%'. Which fields may hold a line break, and markup
-- written as entities, are the field rules' job (migration 002).
CREATE FUNCTION bgs.text_clean(j jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog
AS $$
DECLARE
  bad constant text := '[<>' || chr(1) || '-' || chr(9) || chr(11) || '-' || chr(31) || chr(127)
                       || chr(8212) || chr(8213) || ']';
  k text;
  v jsonb;
BEGIN
  CASE jsonb_typeof(j)
    WHEN 'string' THEN
      RETURN NOT ((j #>> '{}') ~ bad OR strpos(j #>> '{}', '%%') > 0);
    WHEN 'object' THEN
      FOR k, v IN SELECT e.key, e.value FROM jsonb_each(j) AS e LOOP
        IF k ~ bad OR strpos(k, '%%') > 0 OR NOT bgs.text_clean(v) THEN
          RETURN false;
        END IF;
      END LOOP;
    WHEN 'array' THEN
      FOR v IN SELECT e FROM jsonb_array_elements(j) AS e LOOP
        IF NOT bgs.text_clean(v) THEN
          RETURN false;
        END IF;
      END LOOP;
    ELSE
      NULL;
  END CASE;
  RETURN true;
END $$;

-- validate.product_id_problem: lower-case words joined by single hyphens, at
-- most 64 characters, not a word the browser's objects or the admin use.
CREATE FUNCTION bgs.product_id_ok(id text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT id ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(id) <= 64
         AND replace(id, '-', '') NOT IN ('admin', 'constructor', 'hasownproperty', 'isprototypeof', 'new',
             'propertyisenumerable', 'proto', 'prototype', 'tolocalestring', 'tostring', 'valueof') $$;

-- An attar's sizes as validate.product checks them: one to four objects, each
-- with a text label and a whole price from 1 to 100000, no label twice, and
-- the product's own price one of them (the size the card shows first).
CREATE FUNCTION bgs.attar_sizes_ok(d jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT CASE
  WHEN jsonb_typeof(d -> 'sizes') IS DISTINCT FROM 'array' THEN false
  WHEN jsonb_array_length(d -> 'sizes') NOT BETWEEN 1 AND 4 THEN false
  ELSE (SELECT coalesce(bool_and(coalesce(jsonb_typeof(s) = 'object' AND jsonb_typeof(s -> 'label') = 'string'
                                          AND bgs.json_int(s -> 'price') BETWEEN 1 AND 100000, false)), false)
               AND count(DISTINCT s -> 'label') = count(*)
               AND coalesce(bool_or(s -> 'price' = d -> 'price'), false)
          FROM jsonb_array_elements(d -> 'sizes') AS s) END $$;

-- Every scalar of a document with its JSON pointer.
CREATE FUNCTION bgs.leaves(d jsonb) RETURNS TABLE (ptr text, value jsonb)
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
  WITH RECURSIVE t (ptr, v) AS (
    SELECT ''::text, d
    UNION ALL
    SELECT t.ptr || '/' || c.k, c.v
      FROM t CROSS JOIN LATERAL (
        SELECT replace(replace(e.key, '~', '~0'), '/', '~1') AS k, e.value AS v
          FROM jsonb_each(CASE WHEN jsonb_typeof(t.v) = 'object' THEN t.v ELSE '{}'::jsonb END) AS e
        UNION ALL
        SELECT (a.i - 1)::text, a.value
          FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.v) = 'array' THEN t.v ELSE '[]'::jsonb END)
               WITH ORDINALITY AS a (value, i)) AS c)
  SELECT t.ptr, t.v FROM t WHERE jsonb_typeof(t.v) NOT IN ('object', 'array') $$;

-- Who and why, from the transaction's settings. Every content change must say them.
CREATE FUNCTION bgs.actor() RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog
AS $$
DECLARE
  who text := nullif(current_setting('bgs.actor', true), '');
BEGIN
  IF who IS NULL OR nullif(current_setting('bgs.txn', true), '') IS NULL
     OR nullif(current_setting('bgs.reason', true), '') IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'bgs: a content change must say who and why',
      HINT = 'In the same transaction: SELECT set_config(''bgs.txn'', ''<uuid>'', true), '
             'set_config(''bgs.actor'', ''<who>'', true), set_config(''bgs.reason'', ''<why>'', true).';
  END IF;
  IF who !~ '^[A-Za-z0-9._@|:+-]{1,128}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'bgs: bgs.actor is not a user name';
  END IF;
  RETURN who;
END $$;

-- ---- content ------------------------------------------------------------------

-- pos is the product's place in products.json. It is not the shop's order: a
-- reorder rewrites "order" and leaves every product where it is in the file.
CREATE TABLE bgs.products (
  id             text PRIMARY KEY CONSTRAINT products_id_format CHECK (bgs.product_id_ok(id)),
  pos            integer NOT NULL CONSTRAINT products_pos_positive CHECK (pos > 0),
  body           json NOT NULL
                   CONSTRAINT products_body_object CHECK (json_typeof(body) = 'object')
                   CONSTRAINT products_body_sane CHECK (bgs.json_sane(body))
                   CONSTRAINT products_body_size CHECK (octet_length(body::text) <= 65536),
  data           jsonb GENERATED ALWAYS AS (body::jsonb) STORED,
  name           text GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(body::jsonb -> 'name') = 'string'
                                                THEN body::jsonb ->> 'name' END) STORED,
  category       text GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(body::jsonb -> 'category') = 'string'
                                                THEN body::jsonb ->> 'category' END) STORED,
  published      boolean GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(body::jsonb -> 'published') = 'boolean'
                                                   THEN (body::jsonb -> 'published')::boolean END) STORED,
  price          integer GENERATED ALWAYS AS (bgs.json_int(body::jsonb -> 'price')) STORED,
  stock          integer GENERATED ALWAYS AS (bgs.json_int(body::jsonb -> 'stock')) STORED,
  never_discount boolean GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(body::jsonb -> 'never_discount') = 'boolean'
                                                   THEN (body::jsonb -> 'never_discount')::boolean END) STORED,
  sort_order     integer GENERATED ALWAYS AS (bgs.json_int(body::jsonb -> 'order')) STORED,
  version        bigint NOT NULL DEFAULT 1,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  updated_by     text NOT NULL,
  CONSTRAINT products_text_clean CHECK (bgs.text_clean(data)),
  CONSTRAINT products_name_present CHECK (coalesce(btrim(name) <> '' AND length(name) <= 60, false)),
  CONSTRAINT products_category_known CHECK (coalesce(category IN ('attars', 'edp', 'bakhoor', 'gift-sets'), false)),
  CONSTRAINT products_published_boolean CHECK (published IS NOT NULL),
  CONSTRAINT products_never_discount_boolean CHECK (never_discount IS NOT NULL),
  CONSTRAINT products_price_whole_1_to_100000 CHECK (coalesce(price BETWEEN 1 AND 100000, false)),
  CONSTRAINT products_stock_empty_or_0_to_100000 CHECK (coalesce(data -> 'stock' IS NULL OR data -> 'stock' = 'null'::jsonb
                                                                 OR stock BETWEEN 0 AND 100000, false)),
  CONSTRAINT products_order_whole_0_to_100000 CHECK (coalesce(sort_order BETWEEN 0 AND 100000, false)),
  CONSTRAINT products_attar_sizes CHECK (category IS DISTINCT FROM 'attars' OR coalesce(bgs.attar_sizes_ok(data), false)),
  CONSTRAINT products_edp_size_and_gender CHECK (category IS DISTINCT FROM 'edp'
                                                 OR (bgs.truthy(data -> 'size') AND bgs.truthy(data -> 'gender'))),
  CONSTRAINT products_bakhoor_size CHECK (category IS DISTINCT FROM 'bakhoor' OR bgs.truthy(data -> 'size')),
  CONSTRAINT products_gift_set_contents CHECK (category IS DISTINCT FROM 'gift-sets' OR bgs.truthy(data -> 'contents')),
  CONSTRAINT products_not_related_to_itself CHECK (NOT coalesce(data -> 'related' @> to_jsonb(id), false)),
  CONSTRAINT products_pos_unique UNIQUE (pos) DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT products_order_unique UNIQUE (sort_order) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX products_by_category ON bgs.products (category, sort_order);

CREATE TABLE bgs.documents (
  key        text PRIMARY KEY REFERENCES bgs.resources (name)
               CONSTRAINT documents_not_products CHECK (key <> 'products'),
  body       json NOT NULL
               CONSTRAINT documents_body_object CHECK (json_typeof(body) = 'object')
               CONSTRAINT documents_body_sane CHECK (bgs.json_sane(body))
               CONSTRAINT documents_body_size CHECK (octet_length(body::text) <= 1048576),
  data       jsonb GENERATED ALWAYS AS (body::jsonb) STORED,
  version    bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text NOT NULL,
  CONSTRAINT documents_text_clean CHECK (bgs.text_clean(data))
);

-- One number that moves with every statement that writes content, from the
-- admin or from psql: the admin's read cache and its save check compare it.
CREATE TABLE bgs.content_state (
  one     boolean PRIMARY KEY DEFAULT true CONSTRAINT content_state_one_row CHECK (one),
  version bigint NOT NULL DEFAULT 1 CONSTRAINT content_state_version CHECK (version > 0)
);
INSERT INTO bgs.content_state DEFAULT VALUES;

-- A save's check that nothing changed since it read the content: the version,
-- with its row locked until the save ends, so a change from psql waits for the
-- save (or the save gives up after lock_timeout). Definer rights: SELECT ...
-- FOR UPDATE needs UPDATE on the table, which the admin's own role must not
-- have, since it may only read content_state.
CREATE FUNCTION bgs.lock_content_state() RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$ SELECT s.version FROM bgs.content_state AS s FOR UPDATE $$;
REVOKE ALL ON FUNCTION bgs.lock_content_state() FROM PUBLIC;

-- For each file, the sha256 of its bytes and of the database's export when
-- the two last agreed: how the admin tells an edit made to the file (taken
-- in) from one made in the database (exported) from both (flagged).
CREATE TABLE bgs.content_files (
  name       text PRIMARY KEY REFERENCES bgs.resources (name),
  file_sha   text NOT NULL CONSTRAINT content_files_file_sha CHECK (file_sha ~ '^[0-9a-f]{64}$'),
  export_sha text NOT NULL CONSTRAINT content_files_export_sha CHECK (export_sha ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Every place a product is named: the product-ref fields and any link with
-- ?p=. Kept by triggers; the foreign key refuses a name with no product and
-- the removal of a product something still names. It is checked at commit,
-- so one save may add a product and name it in either order (the admin runs
-- SET CONSTRAINTS ALL IMMEDIATE before it writes a file).
CREATE TABLE bgs.product_refs (
  resource   text NOT NULL REFERENCES bgs.resources (name),
  owner_id   text NOT NULL,
  ptr        text NOT NULL,
  via        text NOT NULL CONSTRAINT product_refs_via CHECK (via IN ('field', 'link')),
  product_id text NOT NULL,
  PRIMARY KEY (resource, owner_id, ptr, product_id),
  CONSTRAINT product_refs_target FOREIGN KEY (product_id) REFERENCES bgs.products (id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX product_refs_by_target ON bgs.product_refs (product_id);

-- ---- history and audit ------------------------------------------------------------

CREATE TABLE bgs.revisions (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  txn       uuid NOT NULL,
  at        timestamptz NOT NULL DEFAULT now(),
  actor     text NOT NULL,
  reason    text NOT NULL CONSTRAINT revisions_reason_length CHECK (length(reason) BETWEEN 1 AND 200),
  resource  text NOT NULL REFERENCES bgs.resources (name),
  entity_id text NOT NULL,
  op        text NOT NULL CONSTRAINT revisions_op CHECK (op IN ('insert', 'update', 'delete')),
  version   bigint NOT NULL,
  pos       integer,
  body      json,
  CONSTRAINT revisions_body_unless_deleted CHECK ((op = 'delete') = (body IS NULL)),
  CONSTRAINT revisions_entity CHECK (CASE WHEN resource = 'products' THEN bgs.product_id_ok(entity_id)
                                          ELSE entity_id = '_' END)
);
CREATE INDEX revisions_by_entity ON bgs.revisions (resource, entity_id, id DESC);
CREATE INDEX revisions_by_txn ON bgs.revisions (txn);

-- One row per transaction that changed content (and per refused save, ok
-- false). A save commits only with its row, which is also how the admin
-- learns, after a crash during COMMIT, whether the save was kept.
CREATE TABLE bgs.audit_log (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  txn       uuid NOT NULL UNIQUE,
  at        timestamptz NOT NULL DEFAULT now(),
  actor     text NOT NULL CONSTRAINT audit_log_actor CHECK (actor ~ '^[A-Za-z0-9._@|:+-]{1,128}$'),
  action    text NOT NULL CONSTRAINT audit_log_action_length CHECK (length(action) BETWEEN 1 AND 200),
  resources text[] NOT NULL DEFAULT '{}',
  ok        boolean NOT NULL,
  build_ms  integer CONSTRAINT audit_log_build_ms CHECK (build_ms >= 0),
  problems  jsonb NOT NULL DEFAULT '[]'::jsonb CONSTRAINT audit_log_problems_list CHECK (jsonb_typeof(problems) = 'array'),
  CONSTRAINT audit_log_success_has_no_problems CHECK (NOT ok OR problems = '[]'::jsonb)
);

-- ---- triggers -----------------------------------------------------------------------

CREATE FUNCTION bgs.products_before() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.id <> OLD.id THEN
      RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'products_id_fixed',
        MESSAGE = 'bgs: a product id never changes';
    END IF;
    IF NEW.body::text = OLD.body::text AND NEW.pos = OLD.pos THEN
      NEW.version := OLD.version;
      NEW.created_at := OLD.created_at;
      NEW.updated_at := OLD.updated_at;
      NEW.updated_by := OLD.updated_by;
      RETURN NEW;
    END IF;
    NEW.version := OLD.version + 1;
    NEW.created_at := OLD.created_at;
  ELSE
    NEW.version := 1;
    NEW.created_at := now();
    IF NEW.pos IS NULL THEN
      NEW.pos := (SELECT coalesce(max(p.pos), 0) + 1 FROM bgs.products AS p);
    END IF;
  END IF;
  NEW.updated_by := bgs.actor();
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE FUNCTION bgs.locked_problems(res text, d jsonb) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog
AS $$ SELECT jsonb_agg(jsonb_build_object('path', l.ptr, 'code', 'locked_field') ORDER BY l.ptr)
        FROM bgs.locked_values AS l
       WHERE l.resource = res
         AND (d #> string_to_array(substr(l.ptr, 2), '/')) IS DISTINCT FROM l.value $$;

CREATE FUNCTION bgs.documents_before() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
  probs jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'documents_kept',
      MESSAGE = 'bgs: a document is never deleted; save it with new content instead';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF NEW.key <> OLD.key THEN
      RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'documents_key_fixed',
        MESSAGE = 'bgs: a document key never changes';
    END IF;
    IF NEW.body::text = OLD.body::text THEN
      NEW.version := OLD.version;
      NEW.created_at := OLD.created_at;
      NEW.updated_at := OLD.updated_at;
      NEW.updated_by := OLD.updated_by;
      RETURN NEW;
    END IF;
    NEW.version := OLD.version + 1;
    NEW.created_at := OLD.created_at;
  ELSE
    NEW.version := 1;
    NEW.created_at := now();
  END IF;
  probs := bgs.locked_problems(NEW.key, NEW.body::jsonb);
  IF probs IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'documents_locked_values',
      MESSAGE = format('bgs: %s holds a locked value that is not the one allowed', NEW.key), DETAIL = probs::text;
  END IF;
  NEW.updated_by := bgs.actor();
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- never_discount is guarded in the admin (428 until the owner confirms it). The
-- database asks the same: a change to it needs bgs.confirmed to name that
-- product, as '<id>/never_discount' in a comma-separated list, set in the same
-- transaction, so a script or a bulk update cannot flip it by the way.
CREATE FUNCTION bgs.guard_never_discount() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
  IF (OLD.body::jsonb -> 'never_discount') IS DISTINCT FROM (NEW.body::jsonb -> 'never_discount')
     AND NOT ((NEW.id || '/never_discount') = ANY (string_to_array(coalesce(current_setting('bgs.confirmed', true), ''), ','))) THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'products_never_discount_guarded',
      MESSAGE = format('bgs: never_discount of %s changes only when the change is confirmed', NEW.id),
      DETAIL = '[{"path":"/never_discount","code":"guarded_field"}]',
      HINT = 'SELECT set_config(''bgs.confirmed'', ''<id>/never_discount'', true) in the same transaction.';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION bgs.no_truncate() RETURNS trigger
LANGUAGE plpgsql
AS $$ BEGIN RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'bgs: ' || TG_TABLE_NAME || ' is never truncated'; END $$;

-- Definer rights: the admin's own role may only read content_state.
CREATE FUNCTION bgs.bump_content_state() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$ BEGIN UPDATE bgs.content_state SET version = version + 1; RETURN NULL; END $$;

CREATE FUNCTION bgs.extract_refs(res text, d jsonb)
RETURNS TABLE (ptr text, via text, product_id text)
LANGUAGE sql STABLE SET search_path = pg_catalog
AS $$
  SELECT l.ptr, 'field', l.value #>> '{}'
    FROM bgs.ref_fields AS r, bgs.leaves(d) AS l
   WHERE r.resource = res AND jsonb_typeof(l.value) = 'string'
     AND l.ptr ~ ('^' || replace(r.ptr, '*', '[0-9]+') || '$')
  UNION
  SELECT l.ptr, 'link', m[1]
    FROM bgs.leaves(d) AS l, regexp_matches(l.value #>> '{}', '[?&]p=([^&#]+)', 'g') AS m
   WHERE jsonb_typeof(l.value) = 'string' AND (l.value #>> '{}') ~ '^[a-z0-9-]+[.]html[?]' $$;

-- Definer rights: product_refs is written only here, never by the admin's role.
CREATE FUNCTION bgs.sync_refs() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  res text := CASE WHEN TG_TABLE_NAME = 'products' THEN 'products'
                   ELSE (CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END) ->> 'key' END;
  owner text := CASE WHEN TG_TABLE_NAME = 'products'
                     THEN (CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END) ->> 'id'
                     ELSE '_' END;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    DELETE FROM bgs.product_refs WHERE resource = res AND owner_id = owner;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    INSERT INTO bgs.product_refs (resource, owner_id, ptr, via, product_id)
    SELECT DISTINCT ON (x.ptr, x.product_id) res, owner, x.ptr, x.via, x.product_id
      FROM bgs.extract_refs(res, NEW.data) AS x;
  END IF;
  RETURN NULL;
END $$;

-- Definer rights: revisions are written only here, in the same transaction as
-- the change, with who and why from the transaction's settings.
CREATE FUNCTION bgs.write_revision() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  who text := bgs.actor();
  r jsonb := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
BEGIN
  INSERT INTO bgs.revisions (txn, actor, reason, resource, entity_id, op, version, pos, body)
  VALUES (current_setting('bgs.txn')::uuid, who, left(current_setting('bgs.reason'), 200),
          CASE WHEN TG_TABLE_NAME = 'products' THEN 'products' ELSE r ->> 'key' END,
          CASE WHEN TG_TABLE_NAME = 'products' THEN r ->> 'id' ELSE '_' END,
          lower(TG_OP), (r ->> 'version')::bigint, (r ->> 'pos')::integer,
          CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE NEW.body END);
  RETURN NULL;
END $$;

-- At commit (or at SET CONSTRAINTS ALL IMMEDIATE): the change's audit_log row.
CREATE FUNCTION bgs.revision_audited() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM bgs.audit_log AS a WHERE a.txn = NEW.txn AND a.ok) THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'revisions_audited',
      MESSAGE = 'bgs: a content change commits only with its audit_log row',
      HINT = 'INSERT INTO bgs.audit_log (txn, actor, action, resources, ok) with the transaction''s bgs.txn.';
  END IF;
  RETURN NULL;
END $$;

-- A migration that changes a locked value changes settings in the same
-- transaction; at commit the two must agree.
CREATE FUNCTION bgs.locked_still_held() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
  probs jsonb;
BEGIN
  SELECT jsonb_agg(p) INTO probs
    FROM bgs.documents AS d, jsonb_array_elements(bgs.locked_problems(d.key, d.data)) AS p;
  IF probs IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'locked_values_held',
      MESSAGE = 'bgs: a document does not hold a locked value', DETAIL = probs::text;
  END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION bgs.append_only() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_TABLE_NAME = 'revisions' AND TG_OP = 'DELETE' AND current_setting('bgs.pruning', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = format('bgs: %s rows are never changed or removed', TG_TABLE_NAME);
END $$;

CREATE TRIGGER products_before BEFORE INSERT OR UPDATE ON bgs.products
  FOR EACH ROW EXECUTE FUNCTION bgs.products_before();
CREATE TRIGGER products_guard_never_discount BEFORE UPDATE ON bgs.products
  FOR EACH ROW EXECUTE FUNCTION bgs.guard_never_discount();
CREATE TRIGGER products_refs_on_write AFTER INSERT OR DELETE ON bgs.products
  FOR EACH ROW EXECUTE FUNCTION bgs.sync_refs();
CREATE TRIGGER products_refs_on_change AFTER UPDATE ON bgs.products
  FOR EACH ROW WHEN (OLD.version IS DISTINCT FROM NEW.version) EXECUTE FUNCTION bgs.sync_refs();
CREATE TRIGGER products_revision_on_write AFTER INSERT OR DELETE ON bgs.products
  FOR EACH ROW EXECUTE FUNCTION bgs.write_revision();
CREATE TRIGGER products_revision_on_change AFTER UPDATE ON bgs.products
  FOR EACH ROW WHEN (OLD.version IS DISTINCT FROM NEW.version) EXECUTE FUNCTION bgs.write_revision();
CREATE TRIGGER products_bump AFTER INSERT OR UPDATE OR DELETE ON bgs.products
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.bump_content_state();
CREATE TRIGGER products_no_truncate BEFORE TRUNCATE ON bgs.products
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.no_truncate();

CREATE TRIGGER documents_before BEFORE INSERT OR UPDATE OR DELETE ON bgs.documents
  FOR EACH ROW EXECUTE FUNCTION bgs.documents_before();
CREATE TRIGGER documents_refs_on_write AFTER INSERT ON bgs.documents
  FOR EACH ROW EXECUTE FUNCTION bgs.sync_refs();
CREATE TRIGGER documents_refs_on_change AFTER UPDATE ON bgs.documents
  FOR EACH ROW WHEN (OLD.version IS DISTINCT FROM NEW.version) EXECUTE FUNCTION bgs.sync_refs();
CREATE TRIGGER documents_revision_on_write AFTER INSERT ON bgs.documents
  FOR EACH ROW EXECUTE FUNCTION bgs.write_revision();
CREATE TRIGGER documents_revision_on_change AFTER UPDATE ON bgs.documents
  FOR EACH ROW WHEN (OLD.version IS DISTINCT FROM NEW.version) EXECUTE FUNCTION bgs.write_revision();
CREATE TRIGGER documents_bump AFTER INSERT OR UPDATE OR DELETE ON bgs.documents
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.bump_content_state();
CREATE TRIGGER documents_no_truncate BEFORE TRUNCATE ON bgs.documents
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.no_truncate();

CREATE CONSTRAINT TRIGGER revisions_audited AFTER INSERT ON bgs.revisions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION bgs.revision_audited();
CREATE CONSTRAINT TRIGGER locked_values_held AFTER INSERT OR UPDATE OR DELETE ON bgs.locked_values
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION bgs.locked_still_held();

CREATE TRIGGER revisions_append_only BEFORE UPDATE OR DELETE ON bgs.revisions
  FOR EACH ROW EXECUTE FUNCTION bgs.append_only();
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON bgs.audit_log
  FOR EACH ROW EXECUTE FUNCTION bgs.append_only();
CREATE TRIGGER revisions_no_truncate BEFORE TRUNCATE ON bgs.revisions
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.no_truncate();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON bgs.audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION bgs.no_truncate();

-- ---- housekeeping and the admin's own role -------------------------------------

-- Old versions older than the given age, keeping the newest keep of every
-- product and document. The only way a revision row is ever removed.
CREATE FUNCTION bgs.prune_revisions(older_than interval, keep integer DEFAULT 50) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
  n integer;
BEGIN
  IF keep IS NULL OR keep < 1 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'bgs: keep at least one version of each';
  END IF;
  PERFORM set_config('bgs.pruning', 'on', true);
  DELETE FROM bgs.revisions AS r
   USING (SELECT x.id, row_number() OVER (PARTITION BY x.resource, x.entity_id ORDER BY x.id DESC) AS k
            FROM bgs.revisions AS x) AS ranked
   WHERE r.id = ranked.id AND ranked.k > keep AND r.at < now() - older_than;
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM set_config('bgs.pruning', 'off', true);
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION bgs.prune_revisions(interval, integer) FROM PUBLIC;

-- The admin's own role, once the owner has created it (one command, as the
-- server's superuser; see admin/README.md). It reads everything, writes
-- content, the file bases and the audit trail, and cannot change the schema,
-- the locked values, the reference fields or history, nor switch a trigger
-- off. Every migration ends by calling this.
CREATE FUNCTION bgs.grant_app_role(app text DEFAULT 'bgs_corner_app') RETURNS boolean
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app) THEN
    RETURN false;
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), app);
  EXECUTE format('GRANT USAGE ON SCHEMA bgs TO %I', app);
  EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA bgs TO %I', app);
  -- read-only on the identity sequences, so pg_dump can run as this role
  EXECUTE format('GRANT SELECT ON ALL SEQUENCES IN SCHEMA bgs TO %I', app);
  EXECUTE format('GRANT INSERT (id, pos, body), UPDATE (pos, body), DELETE ON bgs.products TO %I', app);
  EXECUTE format('GRANT INSERT (key, body), UPDATE (body) ON bgs.documents TO %I', app);
  EXECUTE format('GRANT INSERT, UPDATE ON bgs.content_files TO %I', app);
  EXECUTE format('GRANT INSERT (txn, actor, action, resources, ok, build_ms, problems) ON bgs.audit_log TO %I', app);
  EXECUTE format('GRANT EXECUTE ON FUNCTION bgs.prune_revisions(interval, integer) TO %I', app);
  EXECUTE format('GRANT EXECUTE ON FUNCTION bgs.lock_content_state() TO %I', app);
  RETURN true;
END $$;

SELECT bgs.grant_app_role();
