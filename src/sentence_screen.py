"""Gate A screen, part 1: rule-based fact (D1) and condition (D2) checks at sentence level, on the dev labels.

Rule of the screen (docs/01_protocol_draft.md, section 11.1, fixed before this was computed):
  unit            output sentence of a C1 output (dev split, primary labels)
  harmful         the quote of at least one severity 2-3 tag lies in the sentence
  recall          harmful sentences flagged / all harmful sentences
  flag rate       flagged / all sentences, pooled
  random control  same number of sentences flagged per output at random; expected recall computed exactly
  goes on if      flag rate <= 30% and the lower bound of (recall - random recall) > 0, 95% bootstrap over texts
Omission tags have no quote and are reported separately (they need the source-sentence backfill; see omission_backfill.py).

Run:  .venv/bin/python src/sentence_screen.py [--boot 5000 --seed 0]
Writes results/<ANNOTATE_DIR>/screen_d1_d2.md.
"""
import argparse
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import annotate as A
from db import connect
from pilot import CFG, EMB, NLP

ROOT = Path(__file__).resolve().parents[1]
MAX_FLAG_RATE = 0.30

# ------------------------------------------------------------------ D1: facts
NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
del NUMBER_WORDS["one"]   # "one" is too often a pronoun (day one, no one); a digit 1 is still a fact
NUMBER_WORDS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90", "hundred": "100"})
MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()
NUM_WORD_RE = r"(?:%s)" % "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
MONTH_RE = r"(?:%s)" % "|".join(MONTHS)
TIME1 = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(a\.?m\.?|p\.?m\.?)?", re.I)
TIME2 = re.compile(r"\b(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)(?!\w)", re.I)
DATE1 = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s)\b" % MONTH_RE, re.I)
DATE2 = re.compile(r"\b(%s)\s+(\d{1,2})(?:st|nd|rd|th)?\b" % MONTH_RE, re.I)
NUM = re.compile(r"\b\d+(?:[.,]\d+)?\b")
NUMW = re.compile(r"\b%s\b" % NUM_WORD_RE, re.I)
TITLE = re.compile(r"\b(Ms|Mr|Mrs|Dr)\b\.?")
CAPS = re.compile(r"\b[A-Z][A-Za-z]+\b|\b[A-Z]{2,}\b")
NOT_NAMES = set(w.capitalize() for w in MONTHS) | set(w.capitalize() for w in WEEKDAYS)


def _t24(h, m, ap):
    h = int(h)
    if ap:
        ap = ap.lower().replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    return f"T:{h:02d}:{m}"


def facts(sent: str) -> set:
    """Numbers, times, dates, weekdays and names of a sentence, normalised (three = 3, 09:00 = 9 AM, 31 March = March 31)."""
    f, s = set(), re.sub(r"(?m)^\s*\d+[.)]\s+", " ", sent)   # ordered-list markers (1. 2. 3.) are not facts
    for m in TIME1.finditer(s):
        f.add(_t24(m.group(1), m.group(2), m.group(3)))
    s = TIME1.sub(" ", s)
    for m in TIME2.finditer(s):
        f.add(_t24(m.group(1), "00", m.group(2)))
    s = TIME2.sub(" ", s)
    for m in DATE1.finditer(s):
        f.add(f"D:{MONTHS[m.group(2).lower()]}-{int(m.group(1))}")
    s = DATE1.sub(" ", s)
    for m in DATE2.finditer(s):
        f.add(f"D:{MONTHS[m.group(1).lower()]}-{int(m.group(2))}")
    s = DATE2.sub(" ", s)
    for m in NUM.finditer(s):
        f.add("N:" + m.group(0).replace(",", "."))
    for m in NUMW.finditer(s):
        f.add("N:" + NUMBER_WORDS[m.group(0).lower()])
    low = s.lower()
    for d in WEEKDAYS:
        if re.search(r"\b%ss?\b" % d, low):
            f.add("W:" + d)
    for m in TITLE.finditer(s):
        f.add("P:" + m.group(1).lower())
    first = re.match(r"\W*(\w+)", s)
    for m in CAPS.finditer(s):
        w = m.group(0)
        if w in NOT_NAMES or w in ("Ms", "Mr", "Mrs", "Dr"):
            continue
        if first and m.start() <= (first.start(1)) and not w.isupper():
            continue   # sentence-initial capital
        f.add("C:" + w.lower())
    return f


# ------------------------------------------------------------------ D2: conditions
PROHIB = re.compile(r"\b(must not|may not|shall not|not allowed|not permitted|cannot|can't|can not|do not|don't|never|prohibited|forbidden|"
                    r"must never|not be (?:used|utili[sz]ed)|not to)\b", re.I)
OBLIG = re.compile(r"\b(must|shall|required|requires?|need(?:s)? to|have to|has to|had to|mandatory|obliged|obligatory)\b", re.I)
PERMIT = re.compile(r"\b(may|can|allowed|permitted|optional|able to|entitled)\b", re.I)
RECOMM = re.compile(r"\b(should|ought|recommended|advised)\b", re.I)
COND = re.compile(r"\b(if|unless|provided that|in case|in the event|only when|only if|only)\b", re.I)
DEADLINE = re.compile(r"\b(before|by|until|within|no later than|not later than|at the latest|at least|prior to|in advance|after)\b"
                      r"(?:\W+\w+){0,3}?\W+(\d|%s|%s|noon|midnight|the end|next)" % (NUM_WORD_RE, "|".join(WEEKDAYS + list(MONTHS))), re.I)


def conds(sent: str) -> set:
    c = set()
    if PROHIB.search(sent):
        c.add("prohibition")
    rest = PROHIB.sub(" ", sent)
    if OBLIG.search(rest):
        c.add("obligation")
    if PERMIT.search(rest):
        c.add("permission")
    if RECOMM.search(rest):
        c.add("recommendation")
    if COND.search(sent):
        c.add("condition")
    if DEADLINE.search(sent):
        c.add("deadline")
    return c


# ------------------------------------------------------------------ data
def sentences(text):
    return [s for s in NLP(text).sents if any(not t.is_punct and not t.is_space for t in s)]


def load(conn, split="dev"):
    rows = conn.execute("""SELECT co.id, b.text_id, r.seed, t.body, co.output FROM condition_outputs co
                           JOIN base_outputs b ON b.id=co.base_output_id JOIN runs r ON r.id=b.run_id JOIN texts t ON t.id=b.text_id
                           WHERE co.condition='C1' AND t.split=%s ORDER BY b.text_id, r.seed""", (split,)).fetchall()
    units = []
    for co_id, text_id, seed, body, out in rows:
        src_s, out_s = sentences(body), sentences(out)
        sim = EMB.similarity(EMB.encode([x.text for x in out_s]), EMB.encode([x.text for x in src_s])).numpy()
        link = [int(sim[k].argmax()) if sim[k].max() >= CFG["min_sentence_similarity"] else None for k in range(len(out_s))]
        tags = conn.execute("""SELECT category, output_quote, quote_occurrence FROM harm_annotations WHERE condition_output_id=%s
                               AND rater_role='primary' AND severity>=2""", (co_id,)).fetchall()
        harm = [set() for _ in out_s]      # categories of the tags that lie in each sentence
        omissions, lost = 0, 0
        for cat, q, occ in tags:
            if not q:
                omissions += 1
                continue
            need, seen, placed = (occ or 1), 0, False
            nq = A.norm(q)
            for k, s in enumerate(out_s):
                n = len(A.find_all(A.norm(s.text), nq))
                if n and seen + n >= need:
                    harm[k].add(cat); placed = True; break
                seen += n
            lost += not placed
        units.append(dict(text=text_id, seed=seed, src=src_s, out=out_s, link=link, harm=harm, omissions=omissions, lost=lost))
    return units


def flags(u):
    """D1 and D2 flags per output sentence, each over the group of output sentences aligned to one source sentence."""
    n = len(u["out"])
    d1, d2 = [False] * n, [False] * n
    src_all = set().union(*[facts(s.text) for s in u["src"]]) if u["src"] else set()
    by_src = defaultdict(list)
    for k, j in enumerate(u["link"]):
        if j is not None:
            by_src[j].append(k)
        else:   # no source sentence: flag if it brings a fact the source does not have
            if facts(u["out"][k].text) - src_all:
                d1[k] = True
    for j, ks in by_src.items():
        sf, of = facts(u["src"][j].text), set().union(*[facts(u["out"][k].text) for k in ks])
        sc, oc = conds(u["src"][j].text), set().union(*[conds(u["out"][k].text) for k in ks])
        bad1 = bool(sf - of) or bool((of - src_all))   # a source fact is missing here, or an output fact exists nowhere in the source
        bad2 = bool(sc - oc) or ("permission" in oc and "permission" not in sc)
        for k in ks:
            d1[k] |= bad1
            d2[k] |= bad2
    return d1, d2


def screen(units, which, boot, rng):
    """which: 0 for D1, 1 for D2. Returns dict of numbers."""
    per = []   # per unit: (n sentences, n flagged, n harmful, n harmful flagged, harm categories flagged)
    for u in units:
        fl = flags(u)[which]
        h = [bool(x) for x in u["harm"]]
        per.append(dict(text=u["text"], n=len(fl), f=sum(fl), h=sum(h), hf=sum(1 for a, b in zip(fl, h) if a and b),
                        exp=(sum(fl) / len(fl)) * sum(h) if fl else 0.0,
                        cats=[(c, fl[k]) for k, hs in enumerate(u["harm"]) for c in hs]))
    texts = sorted({p["text"] for p in per})
    by = defaultdict(list)
    for p in per:
        by[p["text"]].append(p)

    def est(tx):
        ps = [p for t in tx for p in by[t]]
        H, N = sum(p["h"] for p in ps), sum(p["n"] for p in ps)
        if H == 0 or N == 0:
            return np.nan, np.nan, np.nan, np.nan
        rec, rnd = sum(p["hf"] for p in ps) / H, sum(p["exp"] for p in ps) / H
        return rec, rnd, rec - rnd, sum(p["f"] for p in ps) / N
    point = est(texts)
    ds = np.array([est(list(rng.choice(texts, len(texts)))) for _ in range(boot)])
    lo, hi = np.nanpercentile(ds[:, 2], [2.5, 97.5])
    cat = defaultdict(lambda: [0, 0])
    for p in per:
        for c, f in p["cats"]:
            cat[c][0] += 1
            cat[c][1] += int(f)
    return dict(rec=point[0], rnd=point[1], diff=point[2], rate=point[3], lo=lo, hi=hi, cat=dict(cat),
                H=sum(p["h"] for p in per), N=sum(p["n"] for p in per), F=sum(p["f"] for p in per))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    with connect() as conn:
        units = load(conn)
    nh = sum(sum(1 for x in u["harm"] if x) for u in units)
    L = ["# Gate A screen, part 1: D1 facts and D2 conditions (dev, C1 outputs)", "",
         f"{len(units)} outputs, {sum(len(u['out']) for u in units)} sentences, {nh} harmful sentences (a sentence is harmful if a severity 2-3 tag's quote lies in it). "
         f"{sum(u['omissions'] for u in units)} omission tags have no quote and are not counted here; {sum(u['lost'] for u in units)} tags could not be placed in a sentence.", "",
         "Rule fixed before computing (protocol 11.1): goes on if flag rate <= 30% and the lower bound of (recall - random recall) > 0 "
         "(95% bootstrap over texts). Random recall is the exact expectation for the same number of flags per output. "
         "Descriptive; with this few harmful sentences the interval is wide.", "",
         "| check | flagged / sentences | flag rate | harm recall | random recall | difference [95%] | Gate A |", "|---|---|---|---|---|---|---|"]
    detail = []
    for which, name in enumerate(["D1 facts", "D2 conditions"]):
        r = screen(units, which, a.boot, rng)
        ok = r["rate"] <= MAX_FLAG_RATE and r["lo"] > 0
        L.append(f"| {name} | {r['F']} / {r['N']} | {100 * r['rate']:.0f}% | {100 * r['rec']:.0f}% | {100 * r['rnd']:.0f}% | "
                 f"{100 * r['diff']:+.0f} points [{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}] | {'passes' if ok else 'does not pass'} |")
        detail.append((name, r))
    L += ["", "Recall by the category of the tag in the sentence (a sentence with two tags counts once per tag):", "",
          "| check | category | tags caught / tags |", "|---|---|---|"]
    for name, r in detail:
        for c, (n, f) in sorted(r["cat"].items(), key=lambda x: -x[1][0]):
            L.append(f"| {name} | {c} | {f} / {n} |")
    text = "\n".join(L)
    out = ROOT / os.environ.get("ANNOTATE_DIR", "results")
    out.mkdir(exist_ok=True)
    (out / "screen_d1_d2.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
