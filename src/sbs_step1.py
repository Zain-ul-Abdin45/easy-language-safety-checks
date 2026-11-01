"""Isolated experiment S, step 1 (protocol 11.15): label-free comparison of sentence-by-sentence generation (schema p3_sbs)
with the base C1 (schema p3) on the same dev texts and seeds. No labels are used.

Run:  ANNOTATE_DIR=results/sbs .venv/bin/python src/sbs_step1.py     Writes results/sbs/step1.md
Rule fixed in protocol 11.15: S goes to labelling only if (a) reachable share >= 50%, (b) unaligned output sentences below the base,
(c) FKGL gain kept >= 0.80, (d) protected-item preservation not lower than the base.
"""
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from db import connect
from sentence_screen import load

ROOT = Path(__file__).resolve().parents[1]


def collect(schema):
    conn = connect()
    conn.execute(f"SET search_path TO {schema}")
    units = {(u["text"], u["seed"]): u for u in load(conn)}
    rows = {}
    for tid, seed, wc, fk, sfk, pp, pt, trunc in conn.execute("""SELECT b.text_id, r.seed, co.word_count, co.fkgl, t.fkgl, co.protected_preserved,
            co.protected_total, b.truncated FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id
            JOIN texts t ON t.id=b.text_id WHERE co.condition='C1' AND t.split='dev'""").fetchall():
        rows[(tid, seed)] = dict(words=wc, gain=float(sfk) - float(fk), pp=pp, pt=pt, trunc=bool(trunc))
    spans = defaultdict(lambda: [0, 0])
    for tid, seed, reach in conn.execute("""SELECT b.text_id, r.seed, cs.reachable FROM changed_spans cs JOIN base_outputs b ON b.id=cs.base_output_id
            JOIN runs r ON r.id=b.run_id JOIN texts t ON t.id=b.text_id WHERE t.split='dev'""").fetchall():
        spans[(tid, seed)][0] += int(reach); spans[(tid, seed)][1] += 1
    conn.close()
    per = {}
    for k, u in units.items():
        r = rows[k]
        n = len(u["out"]); un = sum(1 for l in u["link"] if l is None)
        per[k] = dict(reach=spans[k][0], spans=spans[k][1], n=n, un=un, srcs=len(u["src"]),
                      unaligned_src=len(set(range(len(u["src"]))) - {l for l in u["link"] if l is not None}), **r)
    return per


def agg(per, keys):
    g = lambda f: sum(per[k][f] for k in keys)
    return dict(reach=g("reach") / g("spans"), un=g("un") / g("n"), gain=g("gain") / len(keys), pres=g("pp") / g("pt"),
                words=g("words") / len(keys), trunc=g("trunc"), spans=g("spans"), reachable=g("reach"), sent=g("n"),
                src_unaligned=g("unaligned_src") / g("srcs"))


def main():
    rng = np.random.default_rng(0)
    base, s = collect("p3"), collect("p3_sbs")
    keys = sorted(set(base) & set(s))
    texts = sorted({k[0] for k in keys})
    by = defaultdict(list)
    for k in keys:
        by[k[0]].append(k)
    B, S = agg(base, keys), agg(s, keys)
    boots = []
    for _ in range(5000):
        ks = [k for t in rng.choice(texts, len(texts)) for k in by[t]]
        b, x = agg(base, ks), agg(s, ks)
        boots.append((x["reach"] - b["reach"], x["un"] - b["un"], x["gain"] / b["gain"], x["pres"] - b["pres"], x["src_unaligned"] - b["src_unaligned"]))
    boots = np.array(boots)
    ci = lambda i: np.percentile(boots[:, i], [2.5, 97.5])
    ratio = S["gain"] / B["gain"]
    ok = [S["reach"] >= 0.50, S["un"] < B["un"], ratio >= 0.80, S["pres"] >= B["pres"]]
    L = ["# Experiment S, step 1: label-free comparison (dev, Qwen, seeds 1 and 2)", "",
         f"{len(keys)} text and seed units from {len(texts)} texts. Base = whole-text C1 (schema p3); S = sentence-by-sentence C1 (schema p3_sbs). "
         "Rule fixed in protocol 11.15 before any S output existed. Intervals: 95% bootstrap over texts of the difference S minus base.", "",
         "| measure | base C1 | S | difference [95%] | rule | met |", "|---|---|---|---|---|---|",
         f"| (a) reachable share of changed spans | {100 * B['reach']:.1f}% ({B['reachable']} / {B['spans']}) | {100 * S['reach']:.1f}% ({S['reachable']} / {S['spans']}) | "
         f"{100 * (S['reach'] - B['reach']):+.1f} points [{100 * ci(0)[0]:+.1f}, {100 * ci(0)[1]:+.1f}] | S at least 50% | {'yes' if ok[0] else 'no'} |",
         f"| (b) output sentences with no aligned source | {100 * B['un']:.1f}% | {100 * S['un']:.1f}% | {100 * (S['un'] - B['un']):+.1f} points [{100 * ci(1)[0]:+.1f}, {100 * ci(1)[1]:+.1f}] | S below base | {'yes' if ok[1] else 'no'} |",
         f"| (c) FKGL gain kept (S / base) | {B['gain']:.2f} grades | {S['gain']:.2f} grades | {ratio:.2f} [{ci(2)[0]:.2f}, {ci(2)[1]:.2f}] | at least 0.80 | {'yes' if ok[2] else 'no'} |",
         f"| (d) protected items preserved (hand lists) | {B['pres']:.3f} | {S['pres']:.3f} | {S['pres'] - B['pres']:+.3f} [{ci(3)[0]:+.3f}, {ci(3)[1]:+.3f}] | S not lower | {'yes' if ok[3] else 'no'} |",
         f"| (e) words per output | {B['words']:.1f} | {S['words']:.1f} | | report | |",
         f"| (e) outputs cut at the token limit | {B['trunc']} | {S['trunc']} | | report | |",
         f"| extra: source sentences with no aligned output sentence | {100 * B['src_unaligned']:.1f}% | {100 * S['src_unaligned']:.1f}% | {100 * (S['src_unaligned'] - B['src_unaligned']):+.1f} points [{100 * ci(4)[0]:+.1f}, {100 * ci(4)[1]:+.1f}] | report | |", "",
         f"Step 1 rule: **{'met, S goes to labelling' if all(ok) else 'not met, S is not labelled; reported as a negative result'}**."]
    text = "\n".join(L)
    out = ROOT / os.environ.get("ANNOTATE_DIR", "results"); out.mkdir(exist_ok=True)
    (out / "step1.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
