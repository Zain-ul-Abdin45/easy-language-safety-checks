"""Digit guard (D1-digit): how far can a sentence-level check keep numbers, times and dates secure? (protocol 11.2)

D1-digit = D1 of sentence_screen.py restricted to digit facts (numbers N:, times T:, dates D:). A group of output sentences
aligned to one source sentence is flagged if a source digit fact is missing in it, or if it holds a digit fact that occurs
nowhere in the source. Descriptive, dev split, C1 outputs, primary labels.

Run:  .venv/bin/python src/digit_guard.py
Writes results/<ANNOTATE_DIR>/digit_guard.md.
"""
import os
from collections import defaultdict
from pathlib import Path

import annotate as A
from db import connect
from pilot import preserved
from sentence_screen import facts, load

ROOT = Path(__file__).resolve().parents[1]


def dfacts(text):
    return {f for f in facts(text) if f[0] in "NTD"}


def flag_digit(u):
    n = len(u["out"])
    fl = [False] * n
    src_all = set().union(*[dfacts(s.text) for s in u["src"]]) if u["src"] else set()
    by_src = defaultdict(list)
    for k, j in enumerate(u["link"]):
        if j is None:
            fl[k] = bool(dfacts(u["out"][k].text) - src_all)
        else:
            by_src[j].append(k)
    for j, ks in by_src.items():
        sf = dfacts(u["src"][j].text)
        of = set().union(*[dfacts(u["out"][k].text) for k in ks])
        if (sf - of) or (of - src_all):
            for k in ks:
                fl[k] = True
    return fl


def main():
    with connect() as conn:
        units = load(conn)
        co = {(r[0], r[1]): r for r in conn.execute("""SELECT b.text_id, r.seed, co.id, co.word_count, co.output, co.protected_preserved,
                    co.protected_total FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id
                    JOIN texts t ON t.id=b.text_id WHERE co.condition='C1' AND t.split='dev'""").fetchall()}
        prot = defaultdict(list)
        for tid, kind, val in conn.execute("""SELECT p.text_id, p.kind, p.value FROM protected_items p JOIN texts t ON t.id=p.text_id
                                              WHERE t.split='dev' AND p.kind IN ('number','date')""").fetchall():
            prot[tid].append(val)
        tags = defaultdict(list)
        for cid, cat, q, occ in conn.execute("""SELECT condition_output_id, category, output_quote, quote_occurrence FROM harm_annotations
                    WHERE rater_role='primary' AND severity>=2 AND category='wrong_number_date_name'""").fetchall():
            tags[cid].append((q, occ))
    words = sum(r[3] for r in co.values())
    tot_src = lost = out_loses = out_extra = outs = 0
    conf = defaultdict(int)
    tag_digit = tag_caught = tag_all = 0
    flagged_sent = flagged_clean = sent_with_digits = sent_clean_digits = 0
    caught_missed = []
    for u in units:
        r = co[(u["text"], u["seed"])]
        src_d = set().union(*[dfacts(s.text) for s in u["src"]]) if u["src"] else set()
        out_d = set().union(*[dfacts(s.text) for s in u["out"]]) if u["out"] else set()
        tot_src += len(src_d); lost += len(src_d - out_d)
        out_loses += bool(src_d - out_d); out_extra += bool(out_d - src_d); outs += 1
        fl = flag_digit(u)
        hand_miss = any(not preserved(r[4], v) for v in prot[u["text"]])
        conf[(bool(any(fl)), hand_miss)] += 1
        # tags: which sentence holds each wrong_number tag
        tag_sent = set()
        for q, occ in tags[r[2]]:
            tag_all += 1
            need, seen = (occ or 1), 0
            nq = A.norm(q) if q else ""
            for k, s in enumerate(u["out"]):
                c = len(A.find_all(A.norm(s.text), nq)) if nq else 0
                if c and seen + c >= need:
                    tag_sent.add(k)
                    if dfacts(q) or dfacts(s.text) != set():
                        pass
                    if dfacts(q):
                        tag_digit += 1; tag_caught += int(fl[k])
                        if not fl[k]:
                            caught_missed.append((u["text"], u["seed"], q))
                    break
                seen += c
        for k, s in enumerate(u["out"]):
            has = bool(dfacts(s.text) or (u["link"][k] is not None and dfacts(u["src"][u["link"][k]].text)))
            if has:
                sent_with_digits += 1
            if k not in tag_sent and has:
                sent_clean_digits += 1; flagged_clean += int(fl[k])
            flagged_sent += int(fl[k])
    missed_tags = tag_digit - tag_caught
    L = ["# Digit guard (D1-digit) on the dev C1 outputs (exploratory, descriptive)", "",
         f"{outs} outputs, {words} words. Digit facts = numbers, times, dates (normalised: three = 3, 09:00 = 9 AM, 31 March = March 31).", "",
         "## Baseline: how secure are the digits without a check", "",
         f"- Source digit facts: {tot_src}; missing from the output: {lost} ({100 * lost / tot_src:.0f}%), so {100 * (tot_src - lost) / tot_src:.0f}% are kept.",
         f"- Outputs that lose at least one source digit fact: {out_loses} of {outs}; outputs that add a digit fact the source does not have: {out_extra}.", "",
         "## Agreement with the hand lists (protected items of kind number or date)", "",
         "| | hand list: an item is missing | hand list: all present |", "|---|---|---|",
         f"| D1-digit flags the output | {conf[(True, True)]} | {conf[(True, False)]} |",
         f"| D1-digit does not flag | {conf[(False, True)]} | {conf[(False, False)]} |", "",
         "The hand lists accept alternative spellings (for example 24 hours|one day|a day) and the automatic proxy matches text, "
         "so the two are not the same test; the table shows how far they agree, not which is right.", "",
         "## Against the `wrong_number_date_name` tags (severity 2-3)", "",
         f"- Tags in total: {tag_all}; tags whose quote holds a digit fact: {tag_digit}; of those, in a flagged sentence: {tag_caught} "
         f"({100 * tag_caught / max(tag_digit, 1):.0f}%); not flagged: {missed_tags}.",
         f"- Sentences with digit facts and no such tag: {sent_clean_digits}; flagged anyway: {flagged_clean} ({100 * flagged_clean / max(sent_clean_digits, 1):.0f}%).",
         f"- Flagged sentences in all: {flagged_sent} of {sum(len(u['out']) for u in units)}.",
         f"- Residual `wrong_number_date_name` tags per 100 words if flagged sentences are fixed: "
         f"{100 * (tag_all - tag_caught) / words:.2f} (without the guard: {100 * tag_all / words:.2f}).", ""]
    if caught_missed:
        L += ["Digit-tag quotes not flagged:", ""] + [f"- {t} seed {s}: {q}" for t, s, q in caught_missed]
    text = "\n".join(L)
    out = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    out.mkdir(exist_ok=True)
    (out / "digit_guard.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
