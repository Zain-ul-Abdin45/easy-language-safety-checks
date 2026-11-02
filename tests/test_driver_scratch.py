"""Driver test in a scratch schema, on dev text D01 / seed 1 (labelled v2 schemas are only read):
 - C1..C5 outputs equal the stored v2 outputs (generation is reproducible and the stored-token path gives the same conditions)
 - D4a and D4b from the token table equal the v2 D4 scores in results/dev24/d4_scores.json
 - stored alignment agrees with pilot.align (unaligned output sentences), covers every source sentence, and flags many-to-one
 - an omission tag without a source sentence is rejected by the database, and one with a source sentence is accepted
Run:  .venv/bin/python tests/test_driver_scratch.py   (about 1 minute; creates and drops schema p3_zz_driver)"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SCHEMA = "p3_zz_driver"
os.environ["DB_SCHEMA"] = SCHEMA
# D4a/D4b: v2 scored the same tokens through the same forward pass; agreement should be at float32 rounding. Same reasoning as LOGPROB_TOL
# in test_token_roundtrip.py: 1e-4 absorbs thread-count differences and still catches a wrong token window or a temperature.
SCORE_TOL = 1e-4

import psycopg                                   # noqa: E402
import pilot                                     # noqa: E402
import generate_v3 as G                          # noqa: E402
from d4_stored import collect_stored             # noqa: E402
from db import connect                           # noqa: E402

subprocess.run([sys.executable, str(ROOT / "src/migrate.py"), "--schema", SCHEMA], check=True, capture_output=True)
try:
    row = next(json.loads(l) for l in open(ROOT / "data/dev/dev_texts.jsonl") if json.loads(l)["id"] == "D01")
    G.run(SCHEMA, [row], [1], quiet=True, allow_dirty=True)   # the tree is dirty while this is being built; the refusal itself is tested in test_dirty_refusal.py
    with connect() as conn:
        # 1. conditions equal v2
        mine = dict(conn.execute("SELECT co.condition, co.output FROM condition_outputs co").fetchall())
        with psycopg.connect(os.environ["DATABASE_URL"]) as c2:
            old = dict(c2.execute("""SELECT co.condition, co.output FROM p3.condition_outputs co JOIN p3.base_outputs b ON b.id=co.base_output_id
                                     JOIN p3.runs r ON r.id=b.run_id WHERE b.text_id='D01' AND r.seed=1""").fetchall())
        assert mine == old, {k: (mine[k], old.get(k)) for k in mine if mine[k] != old.get(k)}
        print("C1-C5 equal v2:", sorted(mine))

        # 2. D4a / D4b equal v2
        new = [s for s in collect_stored(conn) if s["text"] == "D01"]
        v2 = [s for s in json.load(open(ROOT / "results/dev24/d4_scores.json"))["sents"] if s["text"] == "D01" and tuple(s["unit"]) == ("D01", 1)]
        assert len(new) == len(v2), (len(new), len(v2))
        da = max(abs(x["a"] - y["a"]) for x, y in zip(new, v2)); db_ = max(abs(x["b"] - y["b"]) for x, y in zip(new, v2))
        assert da < SCORE_TOL and db_ < SCORE_TOL, (da, db_)
        print(f"D4a/D4b vs v2: {len(new)} sentences, max diff {da:.2e} / {db_:.2e}")

        # 2b. D5 from the stored sentences equals the v2 D5 scores (min of both directions; whole source for unaligned sentences)
        d5 = [v for (v,) in conn.execute("""SELECT ss.score FROM sentence_scores ss JOIN sentences s ON s.id=ss.output_sentence_id
                                            WHERE ss.check_name='D5' ORDER BY s.idx""")]
        v2d5 = [x["a"] for x in json.load(open(ROOT / "results/dev24/d5_scores_primary.json"))["sents"] if x["text"] == "D01" and tuple(x["unit"]) == ("D01", 1)]
        assert len(d5) == len(v2d5) and max(abs(x - y) for x, y in zip(d5, v2d5)) < SCORE_TOL, (d5, v2d5)
        print(f"D5 vs v2: {len(d5)} sentences, max diff {max(abs(x - y) for x, y in zip(d5, v2d5)):.2e}")

        # 3. alignment
        b_id, out = conn.execute("SELECT id, output FROM base_outputs").fetchone()
        spans = pilot.align(row["body"], out)
        v2_unaligned = {s.sent_idx for s in spans if s.src is None}
        mine_un = {i for (i,) in conn.execute("""SELECT s.idx FROM sentences s JOIN output_alignment a ON a.output_sentence_id=s.id
                                                 WHERE s.base_output_id=%s AND a.source_sentence_id IS NULL AND s.has_words""", (b_id,))}
        assert mine_un == v2_unaligned, (mine_un, v2_unaligned)
        n_src = conn.execute("SELECT count(*) FROM sentences WHERE base_output_id IS NULL").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM source_alignment WHERE base_output_id=%s", (b_id,)).fetchone()[0] == n_src
        assert conn.execute("SELECT count(*) FROM output_alignment a JOIN sentences s ON s.id=a.output_sentence_id WHERE s.base_output_id=%s", (b_id,)).fetchone()[0] \
            == conn.execute("SELECT count(*) FROM sentences WHERE base_output_id=%s", (b_id,)).fetchone()[0]
        m2o = conn.execute("SELECT count(*) FROM output_alignment WHERE many_to_one").fetchone()[0]
        print(f"alignment: {n_src} source sentences, unaligned output sentences {sorted(mine_un)}, many-to-one outputs {m2o}")

        # 4. omission rule
        co = conn.execute("SELECT id FROM condition_outputs WHERE condition='C1'").fetchone()[0]
        src_sid = conn.execute("SELECT id FROM sentences WHERE base_output_id IS NULL ORDER BY idx LIMIT 1").fetchone()[0]
        try:
            with conn.transaction():   # savepoint: the rejected insert must not roll back the connection's search_path
                conn.execute("INSERT INTO harm_annotations(condition_output_id,annotator,category,reachable,severity) VALUES (%s,'t','omission',false,2)", (co,))
            raise AssertionError("omission without a source sentence was accepted")
        except psycopg.errors.CheckViolation:
            pass
        conn.execute("INSERT INTO harm_annotations(condition_output_id,annotator,category,reachable,severity,source_sentence_id) VALUES (%s,'t','omission',false,2,%s)", (co, src_sid))
        conn.execute("INSERT INTO harm_annotations(condition_output_id,annotator,category,reachable,severity) VALUES (%s,'t','hallucination',false,2)", (co,))
        conn.execute("DELETE FROM harm_annotations")   # so the scratch schema holds no labels and can be reset
        conn.commit()
        print("omission rule: rejected without a source sentence, accepted with one")
    print("ok")
finally:
    subprocess.run(["psql", os.environ["DATABASE_URL"], "-q", "-v", f"schema={SCHEMA}", "-f", str(ROOT / "db/reset_dev_only.sql")],
                   env=dict(os.environ, ALLOW_DEV_RESET=SCHEMA), capture_output=True)
