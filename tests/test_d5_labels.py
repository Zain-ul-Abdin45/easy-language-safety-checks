"""D5 label test: a clear entailment scores high and a clear contradiction low, for both models.
Run:  .venv/bin/python tests/test_d5_labels.py   (from the project root)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from d5_screen import load_model, entail

SRC = "The meeting starts at 9 AM on Monday in room 12."
ENT = "The meeting is on Monday morning."
CON = "The meeting is on Friday afternoon."

for key in ("primary", "minicheck"):
    tok, model, idx = load_model(key)
    e, c = entail(tok, model, idx, [(SRC, ENT), (SRC, CON)])
    print(f"{key}: P(entail|entailing pair)={e:.3f}  P(entail|contradicting pair)={c:.3f}")
    assert e > 0.9 and c < 0.1, f"{key}: label index looks wrong"
print("ok")
