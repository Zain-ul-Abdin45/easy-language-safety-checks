"""Sentences and two-direction alignment, stored once (migration 002). Same splitter (spaCy en_core_web_sm), same embedding model and same
threshold (CFG["min_sentence_similarity"]) as pilot.align(), so the output->source link of every sentence is identical to v2.
"""
from __future__ import annotations

import numpy as np

from pilot import CFG, EMB, NLP


def _has_words(sent) -> bool:
    return any(not t.is_punct and not t.is_space for t in sent)


def store_alignment(conn, text_id: str, base_output_id: int, source: str, output: str) -> dict:
    """Stores source sentences (once per text), output sentences, output->source and source->output. `output` is the cleaned output text."""
    src_sents, out_sents = list(NLP(source).sents), list(NLP(output).sents)
    src_ids = [r[0] for r in conn.execute("SELECT id FROM sentences WHERE text_id=%s AND base_output_id IS NULL ORDER BY idx", (text_id,))]
    if not src_ids:
        src_ids = [conn.execute("""INSERT INTO sentences(text_id,idx,char_start,char_end,body,has_words) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                                (text_id, k, s.start_char, s.end_char, s.text, _has_words(s))).fetchone()[0] for k, s in enumerate(src_sents)]
    out_ids = [conn.execute("""INSERT INTO sentences(text_id,base_output_id,idx,char_start,char_end,body,has_words) VALUES (%s,%s,%s,%s,%s,%s,%s)
                               RETURNING id""", (text_id, base_output_id, k, s.start_char, s.end_char, s.text, _has_words(s))).fetchone()[0]
               for k, s in enumerate(out_sents)]
    sim = np.asarray(EMB.similarity(EMB.encode([x.text for x in out_sents]), EMB.encode([x.text for x in src_sents])))
    thr = CFG["min_sentence_similarity"]
    best_src = sim.argmax(axis=1)
    linked = [int(best_src[k]) if sim[k, best_src[k]] >= thr else None for k in range(len(out_sents))]
    n_match = {j: sum(1 for x in linked if x == j) for j in range(len(src_sents))}
    for k, j in enumerate(linked):
        conn.execute("INSERT INTO output_alignment VALUES (%s,%s,%s,%s)",
                     (out_ids[k], None if j is None else src_ids[j], float(sim[k, best_src[k]]), j is not None and n_match[j] > 1))
    best_out = sim.argmax(axis=0)
    for j in range(len(src_sents)):
        ok = sim[best_out[j], j] >= thr
        conn.execute("INSERT INTO source_alignment VALUES (%s,%s,%s,%s,%s)",
                     (base_output_id, src_ids[j], out_ids[best_out[j]] if ok else None, float(sim[best_out[j], j]), n_match[j]))
    return dict(n_out=len(out_sents), n_src=len(src_sents), unaligned_out=sum(x is None for x in linked),
                unmatched_src=[j for j in range(len(src_sents)) if sim[best_out[j], j] < thr])
