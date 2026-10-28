"""Blind annotation sheets.

Export:  .venv/bin/python src/annotate.py export [--subset 0.2]
  results/annotate_outputs.csv  one row per UNIQUE output text (identical C3/C4 etc. merged), condition hidden.
      Fill column `errors` with tags separated by `;;`, each tag as  category|severity|quote
          e.g.  wrong_number_date_name|3|before noon;;omission|2|
      categories: meaning_change omission wrong_number_date_name hallucination altered_condition
                  unclear_reference repetition other.   severity 1-3.
      quote = the smallest wrong piece, copied from the OUTPUT (checked against the output text on import).
      If the quote occurs more than once in the output, add the occurrence number: `before noon#2` is the
      second occurrence (the import asks for it). Leave the quote empty only for an omission. `reachable` is not typed: it is computed on import by
      mapping the quote to the aligned changed spans (at most max_span_tokens words and overlapping a
      reachable span), so the split is the same in every analysis.
      Put `none` when you checked it and found no error (empty rows are skipped as not yet annotated).
      Column `simplicity` (not harm): lexical, structural or both, when the output is harder than needed.
      Column `discuss`: y when unsure; the item goes to the second pass.
  results/annotate_spans.csv    one row per reachable changed span, probability hidden.
      Fill column `harmful` with y, n or f.  y/n = harmful or not harmful; f = fragment (the diff cut a rewritten
      sentence into pieces, so the span is not a word swap). Fragments are counted but left out of the AUC.
      Column `discuss`: y when unsure. See docs/06_codebook.md.
  --subset F also writes annotate_outputs_subset.csv / annotate_spans_subset.csv with a random fraction F of
  the rows (fixed seed) for the second person and the consistency check.

Import:  .venv/bin/python src/annotate.py import --annotator NAME [--role primary|second|consistency]
                                                 [--outputs FILE] [--spans FILE]
  primary      the labels the analysis uses (harm per 100 words, AUC). One annotator only.
  second       second person on the subset: stored for the agreement analysis, never counted in the views.
  consistency  the primary annotator's repeat a week later: same, agreement analysis only.
"""
import argparse
import csv
import hashlib
import random
import re
import sys
from pathlib import Path

import yaml

from db import connect

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
MAX_SPAN_TOKENS = yaml.safe_load(open(ROOT / "config/pilot.yaml"))["max_span_tokens"]
CATS = {"meaning_change", "omission", "wrong_number_date_name", "hallucination",
        "altered_condition", "unclear_reference", "repetition", "other"}
SIMPLICITY = {"lexical": ["simplicity_lexical"], "structural": ["simplicity_structural"],
              "both": ["simplicity_lexical", "simplicity_structural"]}
ROLES = ("primary", "second", "consistency")


def key(base_id, text):
    return hashlib.sha1(f"{base_id}|{text}".encode()).hexdigest()[:12]


def norm(text):
    return " ".join(text.lower().split())


def find_all(text, piece):
    """(start, end) of every whole-word occurrence of piece in text (both already normalised)."""
    if not piece:
        return []
    return [m.span() for m in re.finditer(r"(?<!\w)" + re.escape(piece) + r"(?!\w)", text)]


def locate_quote(output_text, quote, occurrence, item):
    """Range of the quoted piece in the normalised output. A quote that occurs more than once needs #n."""
    hits = find_all(norm(output_text), norm(quote))
    if not hits:
        sys.exit(f"Item {item}: quote '{quote}' does not occur in the output text")
    if len(hits) > 1 and occurrence is None:
        sys.exit(f"Item {item}: quote '{quote}' occurs {len(hits)} times in the output; add #1 to #{len(hits)} "
                 f"to say which one (for example '{quote}#2')")
    if occurrence is not None and not 1 <= occurrence <= len(hits):
        sys.exit(f"Item {item}: quote '{quote}' occurs {len(hits)} time(s), got #{occurrence}")
    return hits[(occurrence or 1) - 1]


def quote_reachable(output_text, quote_range, quote, span_strings):
    """Frozen reach definition applied to a harm tag: the quote is at most max_span_tokens words and the quoted
    occurrence overlaps an occurrence of a reachable changed span (as generated, or as left by the condition's
    check). Known limit: if the changed span's own text occurs twice in the output, either occurrence counts."""
    if quote_range is None or len(quote.split()) > MAX_SPAN_TOKENS:
        return False
    out_n = norm(output_text)
    q0, q1 = quote_range
    return any(s0 < q1 and q0 < s1 for t in span_strings if t for s0, s1 in find_all(out_n, norm(t)))


def export(subset=None):
    RES.mkdir(exist_ok=True)
    with connect() as conn:
        rows = conn.execute("""SELECT co.base_output_id, co.output, t.body FROM condition_outputs co
                               JOIN base_outputs b ON b.id=co.base_output_id JOIN texts t ON t.id=b.text_id""").fetchall()
        uniq = {key(b, o): (s, o) for b, o, s in rows}
        items = list(uniq.items())
        random.Random(0).shuffle(items)
        out_rows = [[k, s, o, "", "", ""] for k, (s, o) in items]
        spans = conn.execute("""SELECT cs.id, t.body, b.output, cs.source_span, cs.output_span FROM changed_spans cs
                                JOIN base_outputs b ON b.id=cs.base_output_id JOIN texts t ON t.id=b.text_id
                                WHERE cs.reachable ORDER BY random()""").fetchall()
        span_rows = [[*r, "", ""] for r in spans]
    out_head = ["item", "source", "output", "errors", "simplicity", "discuss"]
    span_head = ["span_id", "source_text", "output_text", "source_span", "output_span", "harmful", "discuss"]
    files = [("annotate_outputs", out_head, out_rows), ("annotate_spans", span_head, span_rows)]
    if subset:
        rng = random.Random(1)
        files += [("annotate_outputs_subset", out_head, rng.sample(out_rows, round(len(out_rows) * subset))),
                  ("annotate_spans_subset", span_head, rng.sample(span_rows, round(len(span_rows) * subset)))]
    for name, head, data in files:
        with open(RES / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(data)
    print(f"{len(items)} unique outputs (from {len(rows)} condition outputs), {len(spans)} spans"
          + (f"; subset {subset:.0%} written" if subset else ""))


def parse_tags(val, item):
    tags = []
    for part in filter(None, (p.strip() for p in val.split(";;"))):
        cat, sev, quote = ([x.strip() for x in part.split("|", 2)] + ["", ""])[:3]
        occurrence = None
        m = re.match(r"^(.*)#(\d+)$", quote)
        if m:
            quote, occurrence = m.group(1).strip(), int(m.group(2))
        if cat not in CATS:
            sys.exit(f"Item {item}: unknown category '{cat}'")
        if sev not in ("", "1", "2", "3"):
            sys.exit(f"Item {item}: severity must be 1-3, got '{sev}'")
        if not quote and cat != "omission":
            sys.exit(f"Item {item}: tag '{cat}' needs a quote copied from the output (only omission may leave it empty)")
        tags.append((cat, int(sev) if sev else None, quote, occurrence))
    return tags


def import_(annotator, role="primary", outputs_file=None, spans_file=None):
    outputs_file = Path(outputs_file) if outputs_file else RES / "annotate_outputs.csv"
    spans_file = Path(spans_file) if spans_file else RES / "annotate_spans.csv"
    with connect() as conn:
        if role == "primary":
            other = conn.execute("""SELECT DISTINCT annotator FROM output_reviews
                                    WHERE rater_role='primary' AND annotator<>%s
                                    UNION SELECT DISTINCT labelled_by FROM changed_spans
                                    WHERE labelled_by IS NOT NULL AND labelled_by<>%s""", (annotator, annotator)).fetchall()
            if other:
                sys.exit(f"Primary labels already come from {other[0][0]}. Only one primary annotator is allowed, "
                         f"otherwise harm is counted twice. Use --role second or --role consistency.")
        rows = conn.execute("""SELECT co.id, co.base_output_id, co.output, co.condition FROM condition_outputs co""").fetchall()
        by_key, info = {}, {}
        for co_id, b, o, cond in rows:
            by_key.setdefault(key(b, o), []).append(co_id)
            info[co_id] = (b, o, cond)
        span_cache = {}

        def spans_for(co_id):
            b, _, cond = info[co_id]
            if (b, cond) not in span_cache:
                got = conn.execute("""SELECT cs.output_span, sa.final_span FROM changed_spans cs
                                      LEFT JOIN span_actions sa ON sa.span_id=cs.id AND sa.condition=%s
                                      WHERE cs.base_output_id=%s AND cs.reachable""", (cond, b)).fetchall()
                span_cache[(b, cond)] = [t for pair in got for t in pair if t]
            return span_cache[(b, cond)]

        n = 0
        for r in csv.DictReader(open(outputs_file)):
            val = r["errors"].strip()
            if not val:
                continue
            ids = by_key.get(r["item"], [])
            if not ids:
                sys.exit(f"Item {r['item']} not found in the database (stale sheet? re-export)")
            output_text = info[ids[0]][1]
            conn.execute("DELETE FROM harm_annotations WHERE annotator=%s AND rater_role=%s AND condition_output_id = ANY(%s)",
                         (annotator, role, ids))
            conn.execute("DELETE FROM output_flags WHERE annotator=%s AND rater_role=%s AND condition_output_id = ANY(%s)",
                         (annotator, role, ids))
            for co_id in ids:
                conn.execute("""INSERT INTO output_reviews(condition_output_id,annotator,rater_role) VALUES (%s,%s,%s)
                                ON CONFLICT (condition_output_id, annotator, rater_role) DO UPDATE SET reviewed_at=now()""",
                             (co_id, annotator, role))
            simp = (r.get("simplicity") or "").strip().lower()
            if simp and simp not in SIMPLICITY:
                sys.exit(f"Item {r['item']}: simplicity must be lexical, structural or both, got '{simp}'")
            kinds = SIMPLICITY.get(simp, []) + (["discuss"] if (r.get("discuss") or "").strip().lower() == "y" else [])
            for co_id in ids:
                for kind in kinds:
                    conn.execute("INSERT INTO output_flags(condition_output_id,annotator,rater_role,kind) VALUES (%s,%s,%s,%s)",
                                 (co_id, annotator, role, kind))
            if val.lower() == "none":
                continue
            for cat, sev, quote, occ in parse_tags(val, r["item"]):
                qrange = locate_quote(output_text, quote, occ, r["item"]) if quote else None
                for co_id in ids:
                    conn.execute("""INSERT INTO harm_annotations(condition_output_id,annotator,rater_role,category,
                                    output_quote,quote_occurrence,reachable,severity) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                 (co_id, annotator, role, cat, quote or None, occ,
                                  quote_reachable(output_text, qrange, quote, spans_for(co_id)), sev))
                    n += 1
        m = 0
        for r in csv.DictReader(open(spans_file)):
            v = r["harmful"].strip().lower()
            if not v:
                continue
            if v not in ("y", "n", "f"):
                sys.exit(f"Span {r['span_id']}: harmful must be y, n or f, got '{v}'")
            disc = (r.get("discuss") or "").strip().lower() == "y"
            harmful = None if v == "f" else v == "y"
            conn.execute("""INSERT INTO span_labels(span_id,annotator,rater_role,harmful,fragment,discuss)
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (span_id, annotator, rater_role) DO UPDATE
                            SET harmful=EXCLUDED.harmful, fragment=EXCLUDED.fragment, discuss=EXCLUDED.discuss,
                                labelled_at=now()""", (int(r["span_id"]), annotator, role, harmful, v == "f", disc))
            if role == "primary":   # the primary label is also kept on the span itself, which the views read
                conn.execute("""UPDATE changed_spans SET harmful_gold=%s, fragment=%s, discuss=%s, labelled_by=%s,
                                labelled_at=now() WHERE id=%s""", (harmful, v == "f", disc, annotator, int(r["span_id"])))
            m += 1
        conn.commit()
    print(f"[{role}] {n} harm annotations, {m} span labels imported")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "import"])
    ap.add_argument("--annotator", default="pilot")
    ap.add_argument("--role", choices=ROLES, default="primary")
    ap.add_argument("--subset", type=float, default=None, help="export: also write a random fraction for the second person")
    ap.add_argument("--outputs", default=None, help="import: path of the outputs sheet")
    ap.add_argument("--spans", default=None, help="import: path of the spans sheet")
    a = ap.parse_args()
    export(a.subset) if a.cmd == "export" else import_(a.annotator, a.role, a.outputs, a.spans)
