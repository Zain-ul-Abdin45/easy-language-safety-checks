"""Check that the Python environment and the database are ready.

Run:  .venv/bin/python src/check_env.py
"""
import importlib
import platform
import sys

from db import connect

PACKAGES = ["torch", "transformers", "accelerate", "yaml", "pandas", "sklearn",
            "textstat", "spacy", "sentence_transformers", "psycopg"]

ok = True
print(f"Python {sys.version.split()[0]} on {platform.machine()}")
for name in PACKAGES:
    try:
        mod = importlib.import_module(name)
        print(f"  ok   {name} {getattr(mod, '__version__', '')}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  FAIL {name}: {exc}")

import spacy, textstat, torch  # noqa: E402
spacy.load("en_core_web_sm")
print("  ok   spaCy English model")
print(f"  torch CPU threads: {torch.get_num_threads()}, MPS available: {torch.backends.mps.is_available()}")
print(f"  textstat FKGL sample: {textstat.flesch_kincaid_grade('Report sick leave to your manager by 9 am.')}")

with connect() as conn:
    tables = conn.execute(
        "select count(*) from information_schema.tables where table_schema='p3' and table_type='BASE TABLE'"
    ).fetchone()[0]
    views = conn.execute("select count(*) from information_schema.views where table_schema='p3'").fetchone()[0]
    texts = conn.execute("select count(*) from texts").fetchone()[0]
    print(f"Database: {tables} tables, {views} views, {texts} texts loaded")
    for row in conn.execute("select month, planned_hours, hours_spent, pct_of_plan from v_progress"):
        print("  ", row)

print("READY" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
