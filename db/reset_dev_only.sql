-- Wipes ONE schema. Meant for dev experiments that hold no labels. It refuses unless all of these hold:
--   1. the environment variable ALLOW_DEV_RESET equals the schema name,
--   2. the schema is not p3_heldout,
--   3. the schema holds no label rows (harm_annotations, span_labels, output_reviews, output_flags, changed_spans.harmful_gold).
-- Run:  ALLOW_DEV_RESET=p3_v3_smoke psql -d easylang_p3 -v schema=p3_v3_smoke -f db/reset_dev_only.sql
-- Labelled schemas (p3, p3_second, p3_sbs, p3_heldout) are never reset with this file; restore from a dump instead.
\set ON_ERROR_STOP on
\if :{?schema}
\else
  \echo 'give the schema: -v schema=<name>'
  \quit
\endif
\set allow `echo "$ALLOW_DEV_RESET"`
SELECT set_config('reset.schema', :'schema', false), set_config('reset.allow', :'allow', false);
DO $$
DECLARE s text := current_setting('reset.schema'); n bigint := 0; t text;
BEGIN
  IF current_setting('reset.allow') <> s THEN
    RAISE EXCEPTION 'refusing: set ALLOW_DEV_RESET=% to confirm', s;
  END IF;
  IF s = 'p3_heldout' THEN RAISE EXCEPTION 'refusing: p3_heldout is never reset'; END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = s) THEN
    RAISE EXCEPTION 'schema % does not exist', s;
  END IF;
  FOREACH t IN ARRAY ARRAY['harm_annotations','span_labels','output_reviews','output_flags'] LOOP
    IF to_regclass(format('%I.%I', s, t)) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I.%I', s, t) INTO n;
      IF n > 0 THEN RAISE EXCEPTION 'refusing: %.% holds % label rows', s, t, n; END IF;
    END IF;
  END LOOP;
  IF to_regclass(format('%I.changed_spans', s)) IS NOT NULL THEN
    EXECUTE format('SELECT count(*) FROM %I.changed_spans WHERE harmful_gold IS NOT NULL', s) INTO n;
    IF n > 0 THEN RAISE EXCEPTION 'refusing: %.changed_spans holds % span labels', s, n; END IF;
  END IF;
END $$;
SELECT format('DROP SCHEMA %I CASCADE', :'schema') \gexec
\echo 'schema dropped; recreate with src/migrate.py --schema' :schema
