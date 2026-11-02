"""D4a / D4b from the token table (v3). Same output shape as d4_screen.collect(), so d4_screen.evaluate() works on it unchanged.
  D4a  mean token log-probability of the output sentence, from output_tokens (low = suspicious)
  D4b  lowest probability among the changed spans inside the sentence (1 if there is none)
Sentences come from the stored `sentences` table, so the unit is the same one the alignment and the omission tags refer to.
Harm labels (tags with severity >= 2 whose quote falls in the sentence) are used when annotations exist; unlabelled schemas give harmful=False.
"""
from __future__ import annotations

from collections import defaultdict

import annotate as A
from tokens_store import load_tokens, sentence_logprob


def collect_stored(conn, split: str | None = None):
    q = """SELECT co.id, b.id, b.text_id, r.seed FROM condition_outputs co JOIN base_outputs b ON b.id=co.base_output_id
           JOIN runs r ON r.id=b.run_id JOIN texts t ON t.id=b.text_id WHERE co.condition='C1' AND b.token_source='generation'"""
    rows = conn.execute(q + (" AND t.split=%s" if split else "") + " ORDER BY b.text_id, r.seed", (split,) if split else ()).fetchall()
    sents = []
    for co_id, b_id, text_id, seed in rows:
        tokens = load_tokens(conn, b_id)
        out_sents = conn.execute("SELECT idx, char_start, char_end, body, has_words FROM sentences WHERE base_output_id=%s ORDER BY idx", (b_id,)).fetchall()
        span_p = defaultdict(list)
        for k, p in conn.execute("SELECT sentence_idx, probability::float FROM changed_spans WHERE base_output_id=%s AND probability IS NOT NULL", (b_id,)):
            span_p[k].append(p)
        harm = defaultdict(set)
        for cat, q_, occ in conn.execute("""SELECT category, output_quote, quote_occurrence FROM harm_annotations WHERE condition_output_id=%s
                                            AND rater_role='primary' AND severity>=2 AND output_quote IS NOT NULL""", (co_id,)):
            need, seen, nq = (occ or 1), 0, A.norm(q_)
            for idx, _, _, body, _ in out_sents:
                c = len(A.find_all(A.norm(body), nq))
                if c and seen + c >= need:
                    harm[idx].add(cat)
                    break
                seen += c
        for idx, a, z, body, has_words in out_sents:
            if not has_words:
                continue
            sents.append(dict(unit=(text_id, seed), text=text_id, a=sentence_logprob(tokens, a, z),
                              b=min(span_p[idx]) if span_p[idx] else 1.0, harmful=bool(harm[idx]), cats=sorted(harm[idx]), idx=idx))
    return sents


def d4_scores(conn, base_output_id: int, span_min: dict[int, float]) -> dict[int, tuple[float, float]]:
    """{output sentence id: (D4a, D4b)} for one output, from the token table. span_min maps sentence index -> lowest changed-span probability."""
    tokens = load_tokens(conn, base_output_id)
    rows = conn.execute("SELECT id, idx, char_start, char_end FROM sentences WHERE base_output_id=%s AND has_words ORDER BY idx", (base_output_id,)).fetchall()
    return {sid: (sentence_logprob(tokens, a, z), span_min.get(idx, 1.0)) for sid, idx, a, z in rows}
