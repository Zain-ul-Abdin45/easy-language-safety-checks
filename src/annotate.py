"""Blind annotation sheets.

Export:  .venv/bin/python src/annotate.py export
  results/annotate_outputs.csv  one row per UNIQUE output text (identical C3/C4 etc. merged), condition hidden.
      Fill column `errors` as  category:reachable:severity; ...   e.g.  omission:n:2; meaning_change:y:3
      categories: meaning_change omission wrong_number_date_name hallucination altered_condition
                  unclear_reference other.  reachable y/n.  severity 1-3.  Leave empty if no error.
      Put `none` when you checked it and found no error (empty rows are skipped as not yet annotated).
  results/annotate_spans.csv    one row per reachable changed span, probability hidden.
      Fill column `harmful` with y or n.  Used for the January AUC check.

Import:  .venv/bin/python src/annotate.py import --annotator NAME
"""
import argparse
import csv
import hashlib
import random
import sys
from pathlib import Path

from db import connect

RES = Path(__file__).resolve().parents[1] / "results"
CATS = {"meaning_change", "omission", "wrong_number_date_name", "hallucination",
        "altered_condition", "unclear_reference", "other"}


def key(base_id, text):
    return hashlib.sha1(f"{base_id}|{text}".encode()).hexdigest()[:12]


def export():
    RES.mkdir(exist_ok=True)
    with connect() as conn:
        rows = conn.execute("""SELECT co.base_output_id, co.output, t.body FROM condition_outputs co
                               JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id""").fetchall()
        uniq = {key(b, o): (s, o) for b, o, s in rows}
        items = list(uniq.items())
        random.Random(0).shuffle(items)
        with open(RES / "annotate_outputs.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["item", "source", "output", "errors"])
            w.writerows([k, s, o, ""] for k, (s, o) in items)

        spans = conn.execute("""SELECT cs.id, t.body, b.output, cs.source_span, cs.output_span FROM changed_spans cs
                                JOIN base_outputs b ON b.id=cs.base_output_id JOIN texts t ON t.id=b.text_id
                                WHERE cs.reachable ORDER BY random()""").fetchall()
        with open(RES / "annotate_spans.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["span_id", "source_text", "output_text", "source_span", "output_span", "harmful"])
            w.writerows([*r, ""] for r in spans)
    print(f"{len(items)} unique outputs (from {len(rows)} condition outputs), {len(spans)} spans")


def import_(annotator):
    with connect() as conn:
        rows = conn.execute("SELECT id, base_output_id, output FROM condition_outputs").fetchall()
        by_key = {}
        for co_id, b, o in rows:
            by_key.setdefault(key(b, o), []).append(co_id)
        n = 0
        for r in csv.DictReader(open(RES / "annotate_outputs.csv")):
            val = r["errors"].strip()
            if not val:
                continue
            ids = by_key.get(r["item"], [])
            conn.execute("DELETE FROM harm_annotations WHERE annotator=%s AND condition_output_id = ANY(%s)",
                         (annotator, ids))
            if val.lower() == "none":
                continue
            for part in filter(None, (p.strip() for p in val.split(";"))):
                cat, reach, sev = (part.split(":") + ["", ""])[:3]
                if cat not in CATS:
                    sys.exit(f"Unknown category '{cat}' in item {r['item']}")
                for co_id in ids:
                    conn.execute("""INSERT INTO harm_annotations(condition_output_id,annotator,category,reachable,severity)
                                    VALUES (%s,%s,%s,%s,%s)""",
                                 (co_id, annotator, cat, reach.lower().startswith("y"), int(sev) if sev else None))
                    n += 1
        m = 0
        for r in csv.DictReader(open(RES / "annotate_spans.csv")):
            if r["harmful"].strip().lower() in ("y", "n"):
                conn.execute("UPDATE changed_spans SET harmful_gold=%s WHERE id=%s",
                             (r["harmful"].strip().lower() == "y", int(r["span_id"])))
                m += 1
        conn.commit()
    print(f"{n} harm annotations, {m} span labels imported")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "import"])
    ap.add_argument("--annotator", default="pilot")
    a = ap.parse_args()
    export() if a.cmd == "export" else import_(a.annotator)
