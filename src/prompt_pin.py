"""One place that builds the chat prompt for v3 runs, with the date the chat template would otherwise take from the clock.

The Llama 3.2 template calls strftime_now("%d %b %Y") for "Today Date:" in the system prompt, so the prompt (and the sampled tokens) change from day to
day. config/model_pins.yaml holds the one date to use (chat_template_date_string); it is passed as date_string to every model whose template uses the
date. For other models (Qwen) the template has no date and the prompt is unchanged. pilot.py is not edited: install() replaces pilot.build_prompt_ids
for scripts started through src/run_pinned.py (the v2 screens when re-run on Llama)."""
import hashlib

import torch
import yaml

import pilot
from pilot import INSTRUCTION, ROOT, SYSTEM

DATE_STRING = yaml.safe_load(open(ROOT / "config/model_pins.yaml"))["chat_template_date_string"]


def uses_date(tok) -> bool:
    return "strftime_now" in (tok.chat_template or "")


def messages(text: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": INSTRUCTION.format(text=text)}]


def build_prompt_ids(tok, text: str) -> torch.Tensor:
    kw = {"date_string": DATE_STRING} if uses_date(tok) else {}
    return tok.apply_chat_template(messages(text), add_generation_prompt=True, return_tensors="pt", return_dict=True, **kw)["input_ids"]


def rendered_prompt_sha256(tok, text: str) -> str:
    kw = {"date_string": DATE_STRING} if uses_date(tok) else {}
    return hashlib.sha256(tok.apply_chat_template(messages(text), add_generation_prompt=True, tokenize=False, **kw).encode()).hexdigest()


def install() -> None:
    """Make pilot.generate (and so the v2 scripts) use the pinned prompt."""
    pilot.build_prompt_ids = build_prompt_ids
