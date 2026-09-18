-- The shop follows the policies the owner published (18 September 2026).
--
-- The Shipping and Delivery Policy says the shop does not offer cash on
-- delivery and is not registered for VAT, and that an order is dispatched in
-- one to three business days rather than the same day. Cash on delivery and
-- VAT are locked values, which the admin cannot change: a migration changes
-- them, together with the settings document, so the two never disagree.
--
-- An empty database is loaded from flow/content afterwards, where these
-- values are already the new ones; there the updates below find nothing to
-- do and only the locked values move.

SELECT set_config('bgs.txn', gen_random_uuid()::text, true),
       set_config('bgs.actor', 'migration', true),
       set_config('bgs.reason', 'migration 003: the published policies', true);

-- Only a database that holds settings already writes a change: into an empty
-- one the content arrives from flow/content afterwards, with nothing to
-- change and nothing to record. The audit row may follow the change it
-- belongs to: revisions_audited is checked at commit.

UPDATE bgs.locked_values SET value = 'false'::jsonb, reason = 'The shop does not offer cash on delivery.'
  WHERE resource = 'settings' AND ptr = '/payments/cod';
UPDATE bgs.locked_values SET value = '0'::jsonb, reason = 'The business is not registered for VAT.'
  WHERE resource = 'settings' AND ptr = '/store/vat_rate_percent';
UPDATE bgs.locked_values SET value = 'false'::jsonb, reason = 'The business is not registered for VAT.'
  WHERE resource = 'settings' AND ptr = '/store/vat_inclusive';

INSERT INTO bgs.audit_log (txn, actor, action, resources, ok)
  SELECT current_setting('bgs.txn')::uuid, 'migration', 'migration 003: the published policies',
         ARRAY['settings'], true
   WHERE EXISTS (SELECT 1 FROM bgs.documents WHERE key = 'settings');

UPDATE bgs.documents
   SET body = jsonb_set(
                jsonb_set(
                  jsonb_set(
                    jsonb_set(
                      jsonb_set(body::jsonb, '{payments,cod}', 'false'::jsonb),
                      '{store,vat_rate_percent}', '0'::jsonb),
                    '{store,vat_inclusive}', 'false'::jsonb),
                  '{store,sameday}', 'false'::jsonb),
                '{store,dispatch_days}', '"1 to 3 business days"'::jsonb)::json
 WHERE key = 'settings'
   AND (body::jsonb -> 'payments' ->> 'cod' IS DISTINCT FROM 'false'
     OR body::jsonb -> 'store' ->> 'vat_rate_percent' IS DISTINCT FROM '0'
     OR body::jsonb -> 'store' ->> 'vat_inclusive' IS DISTINCT FROM 'false'
     OR body::jsonb -> 'store' ->> 'sameday' IS DISTINCT FROM 'false'
     OR body::jsonb -> 'store' ->> 'dispatch_days' IS DISTINCT FROM '1 to 3 business days');
