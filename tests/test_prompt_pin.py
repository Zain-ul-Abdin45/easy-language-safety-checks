"""The rendered prompt must not depend on the day (for both models). Tokenizers only, no weights; the clock inside the chat template is faked.
Control: without the pin the Llama prompt does change with the date, so this test can fail.
Run:  .venv/bin/python tests/test_prompt_pin.py"""
import datetime as dt
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import transformers.utils.chat_template_utils as ctu    # noqa: E402
from transformers import AutoTokenizer                  # noqa: E402

import prompt_pin as P                                  # noqa: E402

TEXT = "Please send the form to the office by 5 May 2026."
DAYS = [dt.datetime(2026, 10, 31, 9), dt.datetime(2026, 11, 2, 23, 59), dt.datetime(2030, 1, 5, 0, 1)]
REAL = ctu.datetime


def on_day(day):
    class Fake(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return day
    ctu.datetime = Fake


def tokenizers():
    pins = yaml.safe_load(open(ROOT / "config/model_pins.yaml"))["generator"]
    qwen = AutoTokenizer.from_pretrained(pins["repo"], revision=pins["revision"], local_files_only=True)
    llama = AutoTokenizer.from_pretrained(str(ROOT / yaml.safe_load(open(ROOT / "config/second_model.yaml"))["model_path"]), local_files_only=True)
    return {"qwen": qwen, "llama": llama}


def unpinned(tok):
    return tok.apply_chat_template(P.messages(TEXT), add_generation_prompt=True, tokenize=False)


try:
    toks = tokenizers()
    assert P.uses_date(toks["llama"]) and not P.uses_date(toks["qwen"]), "template detection changed"
    for name, tok in toks.items():
        hashes, ids, raw = set(), [], set()
        for day in DAYS:
            on_day(day)
            hashes.add(P.rendered_prompt_sha256(tok, TEXT)); ids.append(P.build_prompt_ids(tok, TEXT).tolist()); raw.add(unpinned(tok))
        assert len(hashes) == 1 and all(i == ids[0] for i in ids), f"{name}: the pinned prompt changed with the date"
        if name == "llama":
            assert len(raw) == len(DAYS), "control failed: the unpinned Llama prompt should change with the date"
            assert f"Today Date: {P.DATE_STRING}" in tok.decode(ids[0][0]), "pinned date not in the rendered prompt"
        else:
            assert len(raw) == 1, "Qwen's template unexpectedly uses the date"
        print(f"{name}: one prompt hash across {len(DAYS)} days ({next(iter(hashes))[:12]}); unpinned render changes with the date: {len(raw) > 1}")
finally:
    ctu.datetime = REAL
import tokens_store as T                                 # noqa: E402
assert T.build_prompt_ids is P.build_prompt_ids, "the v3 generation path must use the pinned prompt builder"
print("ok")
