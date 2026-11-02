"""flag_lowest: k = floor(0.3 n) including small n, ties by sentence ID, independent of input order, rate never above 30%.
Run:  .venv/bin/python tests/test_flag_rule.py"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from flag_rule import flag_lowest, n_flagged  # noqa: E402

# k for every n from 0 to 300 equals integer arithmetic floor(3n/10); small n flag nothing until n = 4
assert all(n_flagged(n) == (3 * n) // 10 for n in range(301))
assert [n_flagged(n) for n in range(0, 12)] == [0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3]
assert n_flagged(100, 0.29) == 29      # plain float arithmetic gives 0.29 * 100 = 28.999999999999996, floor 28

rng = random.Random(0)
for n in list(range(0, 41)) + [64, 99, 100, 101, 250]:
    for ties in (False, True):
        rows = [(i, float(rng.randint(0, 4)) if ties else rng.random()) for i in range(n)]
        flagged = flag_lowest(rows)
        k = (3 * n) // 10
        assert len(flagged) == k and len(flagged) <= 0.30 * n + 1e-12, (n, len(flagged))
        # the flagged are the k lowest: nobody unflagged scores below a flagged sentence, and among equal scores the smaller ID is flagged first
        sc = dict(rows)
        for a in flagged:
            for b in sc:
                if b not in flagged:
                    assert (sc[a], a) < (sc[b], b), (a, b)
        # deterministic and independent of input order
        for _ in range(3):
            shuffled = rows[:]; rng.shuffle(shuffled)
            assert flag_lowest(shuffled) == flagged
        assert flag_lowest(rows) == flagged

# all scores equal: the k smallest IDs are flagged
assert flag_lowest([(i, 0.5) for i in (7, 3, 9, 1, 5, 2, 8, 4, 6, 0)]) == {0, 1, 2}
# string and tuple IDs work (unit, position) and tie-break on them
assert flag_lowest([(("T01", 1, i), 0.0) for i in range(10)]) == {("T01", 1, 0), ("T01", 1, 1), ("T01", 1, 2)}
# Llama-style tie at the cut: the percentile rule flags all tied sentences, this one stops at k
rows = [(i, 0.0 if i < 5 else 1.0) for i in range(12)]            # k = 3, five tied at the bottom
assert flag_lowest(rows) == {0, 1, 2}
for bad in ([(1, 0.1), (1, 0.2)], [(1, float("nan"))]):
    try:
        flag_lowest(bad)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
print("ok")
