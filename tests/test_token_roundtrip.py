"""Token storage test (migration 001), on one dev text in a throwaway schema.
Checks: stored IDs decode back to the stored raw text exactly; offsets tile the text; cleaned text = raw[cut:]; stored log-probabilities equal
the v2 scoring path (pilot.token_probs) on the same IDs; the table feeds pilot.span_prob / sentence_logprob. Prints (does not assert) whether
regeneration reproduces the stored v2 output, which is the CPU-determinism question behind the "do not regenerate dev" rule.
Run:  .venv/bin/python tests/test_token_roundtrip.py   (about 1 minute, CPU; creates and drops schema p3_zz_test)
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Stored log-probabilities vs the v2 scoring path (pilot.token_probs) on the same IDs. Both run the same forward pass in float32 on CPU, so
# they should agree to float32 rounding (about 1e-6 on a log-probability); 1e-4 leaves room for a different thread count or BLAS while still
# catching a real difference such as a wrong position shift or a temperature applied.
LOGPROB_TOL = 1e-4
sys.path.insert(0, str(ROOT / "src"))
SCHEMA = "p3_zz_test"
os.environ["DB_SCHEMA"] = SCHEMA

import pilot                                   # noqa: E402
import tokens_store as T                       # noqa: E402
from db import connect                         # noqa: E402

subprocess.run([sys.executable, str(ROOT / "src/migrate.py"), "--schema", SCHEMA], check=True, capture_output=True)
try:
    row = next(json.loads(l) for l in open(ROOT / "data/dev/dev_texts.jsonl") if json.loads(l)["id"] == "D01")
    tok, model = pilot.load_model()
    g = T.generate_tokens(tok, model, row["body"], 1)
    cleaned, cut, log = T.clean_output(g["raw"])
    with connect() as conn:
        conn.execute("INSERT INTO texts(id,source,split,body) VALUES ('D01','t','dev',%s)", (row["body"],))
        rid = conn.execute("INSERT INTO runs(model,backend,seed,prompt_version,manifest) VALUES ('m','transformers',1,'t',%s) RETURNING id",
                           (json.dumps(T.run_manifest(tok, model, 1, pilot.INSTRUCTION)),)).fetchone()[0]
        bid = conn.execute("INSERT INTO base_outputs(run_id,text_id,output,truncated) VALUES (%s,'D01',%s,%s) RETURNING id",
                           (rid, cleaned, g["hit_limit"])).fetchone()[0]
        T.store_tokens(conn, bid, g, cut)
        conn.commit()

        raw, c, src = conn.execute("SELECT raw_output, clean_cut, token_source FROM base_outputs WHERE id=%s", (bid,)).fetchone()
        ids = [r[0] for r in conn.execute("SELECT token_id FROM output_tokens WHERE base_output_id=%s ORDER BY position", (bid,))]
        assert tok.decode(ids) == raw, "stored IDs do not decode to the stored raw text"
        assert raw[c:] == cleaned and src == "generation"
        offs = [(r[0], r[1]) for r in conn.execute("SELECT char_start, char_end FROM output_tokens WHERE base_output_id=%s ORDER BY position", (bid,))]
        assert offs[0][0] == 0 and offs[-1][1] == len(raw) and all(offs[k][1] == offs[k + 1][0] for k in range(len(offs) - 1)), "offsets do not tile the text"

        # same quantity as v2, on the same IDs
        prompt = pilot.build_prompt_ids(tok, row["body"]).to(pilot.CFG["device"])
        _, v2 = pilot.token_probs(tok, model, prompt, ids)
        stored = T.load_tokens(conn, bid)
        raw_tokens = [(a, z, lp) for (a, z), lp in zip(offs, [r[0] for r in conn.execute("SELECT logprob FROM output_tokens WHERE base_output_id=%s ORDER BY position", (bid,))])]
        diff = max(abs(math.log(max(p, 1e-12)) - lp) for (_, _, p), (_, _, lp) in zip(v2, raw_tokens))
        assert diff < LOGPROB_TOL, f"stored log-probs differ from the v2 scoring path by {diff}"
        sp = T.prob_spans(stored)
        a, z = 0, len(cleaned)
        assert abs(pilot.span_prob(sp, a, z) - pilot.span_prob([(s - c, e - c, p) for s, e, p in v2 if e > c], a, z)) < LOGPROB_TOL
        print(f"D4a of whole output {T.sentence_logprob(stored, a, z):.3f}; {len(ids)} tokens; hit limit: {g['hit_limit']}; lead-in cut: {cut} chars")
    with connect() as c2:
        c2.execute("SET search_path TO p3")
        v2_out = c2.execute("SELECT b.output FROM base_outputs b JOIN runs r ON r.id=b.run_id WHERE b.text_id='D01' AND r.seed=1").fetchone()
    print("regenerated text equals the stored v2 output:", v2_out is not None and v2_out[0].strip() == cleaned.strip())
    print("ok")
finally:
    env = dict(os.environ, ALLOW_DEV_RESET=SCHEMA)
    subprocess.run(["psql", os.environ.get("DATABASE_URL") or "", "-q", "-v", f"schema={SCHEMA}", "-f", str(ROOT / "db/reset_dev_only.sql")], env=env, capture_output=True)
