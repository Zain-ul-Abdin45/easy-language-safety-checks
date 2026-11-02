"""D5 (NLI entailment, protocol 11.6) on the stored sentence tables. Same rule as d5_screen.pairs_of / score_units:
  aligned output sentence    min( P(entail | source sentence -> output sentence), P(entail | output sentence -> source sentence) )
  unaligned output sentence  P(entail | whole source text -> output sentence)   (one direction)
Loading d5_screen sets torch's thread count to cpu_count-1 as a side effect; that would change generation speed in the same process, so the
thread count is restored right after the import.
"""
from __future__ import annotations

import torch


def load_d5():
    n = torch.get_num_threads()
    import d5_screen as D
    torch.set_num_threads(n)
    tok, model, idx = D.load_model("primary")
    assert torch.get_num_threads() == n
    return D, tok, model, idx


def entail_one_batch(D, tok, model, idx, pairs) -> list[float]:
    """All NLI pairs of one output in a single batch, shortest first. Sorting keeps the padding small (a whole-source premise can be several times
    longer than a sentence pair); the scores are returned in the original order. Padding does not change a score beyond float rounding, which
    tests/test_driver_scratch.py checks against the v2 scores."""
    if not pairs:
        return []
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]))
    scored = D.entail(tok, model, idx, [pairs[i] for i in order], bs=len(pairs))
    out = [0.0] * len(pairs)
    for i, p in zip(order, scored):
        out[i] = p
    return out


def score_output(conn, base_output_id: int, D, tok, model, idx) -> tuple[dict[int, float], int]:
    """Returns ({output sentence id: score}, number of NLI pairs scored). Sentences without words are skipped, as in the dev screen."""
    body = conn.execute("SELECT t.body FROM texts t JOIN base_outputs b ON b.text_id=t.id WHERE b.id=%s", (base_output_id,)).fetchone()[0]
    rows = conn.execute("""SELECT s.id, s.body, src.body FROM sentences s JOIN output_alignment a ON a.output_sentence_id=s.id
                           LEFT JOIN sentences src ON src.id=a.source_sentence_id WHERE s.base_output_id=%s AND s.has_words ORDER BY s.idx""",
                        (base_output_id,)).fetchall()
    pairs, owner = [], []
    for sid, out_body, src_body in rows:
        if src_body is None:
            pairs.append((body, out_body)); owner.append(sid)
        else:
            pairs += [(src_body, out_body), (out_body, src_body)]; owner += [sid, sid]
    probs = entail_one_batch(D, tok, model, idx, pairs)
    per: dict[int, list[float]] = {}
    for sid, p in zip(owner, probs):
        per.setdefault(sid, []).append(p)
    return {sid: float(min(v)) for sid, v in per.items()}, len(pairs)
