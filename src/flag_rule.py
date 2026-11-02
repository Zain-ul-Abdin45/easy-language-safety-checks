"""The flag rule for the sentence-level checks: flag exactly the k = floor(rate * n) lowest-scoring sentences, ties broken by sentence ID
(smaller ID first), so the flagged set does not depend on the order the rows arrive in and the flag rate never exceeds `rate`.

n is the number of sentences in the pooled population being scored (all dev sentences in the dev sensitivity line; all held-out sentences in the
held-out run). With rate 0.30, populations of fewer than 4 sentences flag nothing (floor(0.3 * 3) = 0). The rate is read as a decimal string and
k is computed with exact fractions, so 0.29 * 100 cannot become 28.999... and flag one sentence too few.

v2 (dev Gate A) used "score at or below the 30th percentile", which flags every tied sentence and can exceed 30% (Llama D4a: 30.25%). That rule is
not changed for the dev results already reported; this one applies from the held-out run on, and to the dev sensitivity line.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Hashable, Iterable


def n_flagged(n: int, rate: float = 0.30) -> int:
    return math.floor(Fraction(str(rate)) * n)


def flag_lowest(rows: Iterable[tuple[Hashable, float]], rate: float = 0.30) -> set:
    """rows: (sentence_id, score) pairs; returns the set of flagged sentence IDs. IDs must be unique and orderable; scores must not be NaN."""
    rows = list(rows)
    ids = [r[0] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate sentence IDs")
    if any(s != s for _, s in rows):
        raise ValueError("NaN score")
    k = n_flagged(len(rows), rate)
    return {sid for sid, _ in sorted(rows, key=lambda r: (r[1], r[0]))[:k]}
