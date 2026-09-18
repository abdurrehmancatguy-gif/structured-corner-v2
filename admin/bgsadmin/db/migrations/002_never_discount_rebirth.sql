-- Never discounted survives a delete and a fresh insert.
--
-- 001 guards never_discount on UPDATE: it changes only when the transaction
-- names the product in bgs.confirmed, as the admin asks the owner to confirm.
-- A delete followed by an insert of the same id went round that guard: the
-- new row is an insert, so nothing compared it with what the product was.
-- Anyone able to write to the database in psql could take a piece out of
-- Never discounted that way, which is the one product rule the shop promises
-- structurally.
--
-- An insert now looks the product up in bgs.revisions, which every delete and
-- every save writes: if the last revision of that id is a delete, the new
-- never_discount has to match the one the product had when it was deleted,
-- or the same confirmation the update guard asks for has to be there. A
-- product that never existed, and a re-created one that keeps its setting,
-- are untouched.

CREATE FUNCTION bgs.guard_never_discount_reborn() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $$
DECLARE
  deleted boolean;
  was json;
BEGIN
  SELECT r.op = 'delete' INTO deleted FROM bgs.revisions AS r
    WHERE r.resource = 'products' AND r.entity_id = NEW.id
    ORDER BY r.id DESC LIMIT 1;
  IF NOT coalesce(deleted, false) THEN
    RETURN NEW;
  END IF;
  SELECT r.body INTO was FROM bgs.revisions AS r
    WHERE r.resource = 'products' AND r.entity_id = NEW.id AND r.body IS NOT NULL
    ORDER BY r.id DESC LIMIT 1;
  IF was IS NOT NULL
     AND (was::jsonb -> 'never_discount') IS DISTINCT FROM (NEW.body::jsonb -> 'never_discount')
     AND NOT ((NEW.id || '/never_discount') = ANY (string_to_array(coalesce(current_setting('bgs.confirmed', true), ''), ','))) THEN
    RAISE EXCEPTION USING ERRCODE = '23514', CONSTRAINT = 'products_never_discount_guarded',
      MESSAGE = format('bgs: never_discount of %s changes only when the change is confirmed, a delete and a new row included', NEW.id),
      DETAIL = '[{"path":"/never_discount","code":"guarded_field"}]',
      HINT = 'SELECT set_config(''bgs.confirmed'', ''<id>/never_discount'', true) in the same transaction.';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER products_guard_never_discount_reborn BEFORE INSERT ON bgs.products
  FOR EACH ROW EXECUTE FUNCTION bgs.guard_never_discount_reborn();
