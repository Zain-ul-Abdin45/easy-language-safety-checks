"""Create or upgrade a project schema: base schema (db/schema.sql) once, then db/migrations/NNN_*.sql in order.
Each file is applied once per schema and recorded in schema_migrations. Nothing is dropped.

Run:  .venv/bin/python src/migrate.py --schema p3_v3_smoke           (use --status to list what is applied, --dry-run to list what would run)
Existing labelled schemas (p3, p3_second, p3_sbs) are only changed when named explicitly. p3_heldout needs the freeze (src/heldout_guard.py).
"""
import argparse
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
LABELLED = {"p3", "p3_second", "p3_sbs", "p3_heldout"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", a.schema):
        raise SystemExit("schema name: lower-case letters, digits, underscore")
    if a.schema == "p3_heldout" and not (a.status or a.dry_run):
        from heldout_guard import FreezeError, require_freeze
        try:
            require_freeze()
        except FreezeError as e:
            raise SystemExit(f"refusing to touch p3_heldout: {e}")
    files = sorted((ROOT / "db/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        exists = conn.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (a.schema,)).fetchone()
        done = set()
        if exists and conn.execute("SELECT to_regclass(%s)", (f"{a.schema}.schema_migrations",)).fetchone()[0]:
            done = {r[0] for r in conn.execute(f"SELECT version FROM {a.schema}.schema_migrations")}
        todo = [f for f in files if f.name not in done]
        if a.status or a.dry_run:
            print(f"schema {a.schema}: {'exists' if exists else 'missing'}; applied: {sorted(done) or 'none'}; to apply: {[f.name for f in todo]}")
            return
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {a.schema}")
        conn.execute(f"SET search_path TO {a.schema}")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
        if "000_base" not in done:
            conn.execute((ROOT / "db/schema.sql").read_text())
            conn.execute("INSERT INTO schema_migrations(version) VALUES ('000_base')")
        for f in todo:
            conn.execute(f.read_text())
            conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (f.name,))
            print("applied", f.name)
        conn.commit()
    print(f"schema {a.schema} is up to date")


if __name__ == "__main__":
    main()
