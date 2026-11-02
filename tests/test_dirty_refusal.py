"""The driver refuses a dirty working tree unless --allow-dirty (smoke/dev), and never for held-out. No model is loaded: the refusal comes first.
Run:  .venv/bin/python tests/test_dirty_refusal.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import generate_v3 as G      # noqa: E402
import tokens_store as T     # noqa: E402

row = dict(id="X", split="smoke", body="b", protected=[])
fake = lambda dirty: dict(commit="c" * 40, dirty=dirty, dirty_files=["src/x.py"] if dirty else [])


def refused(split="smoke", schema="p3_v3_smoke", **kw):
    try:
        G.run(schema, [dict(row, split=split)], [1], tok=object(), model=object(), d5=False, **kw)
    except SystemExit as e:
        return str(e)
    except Exception as e:   # past the refusal (e.g. the schema is not there): not a dirty-tree refusal
        return f"past the refusal: {type(e).__name__}"


real = T.git_state
try:
    T.git_state = lambda: fake(True)
    assert "uncommitted" in refused(), "dirty tree must be refused"
    assert "never allowed" in refused(split="heldout", schema="p3_heldout", allow_dirty=True), "held-out must refuse even with allow_dirty"
    T.git_state = lambda: fake(False)
    msg = refused()
    assert "uncommitted" not in (msg or ""), "clean tree must not be refused for being dirty"
finally:
    T.git_state = real
print("ok")
