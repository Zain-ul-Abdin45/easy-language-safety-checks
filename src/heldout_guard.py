"""The only way to read held-out texts. Refuses unless the protocol is frozen:
  1. config/freeze.yaml says frozen: true and names the protocol commit,
  2. git tag "protocol-freeze" exists and points at that commit, and that commit is an ancestor of HEAD,
  3. the working tree has no uncommitted changes to tracked files,
  4. the SHA-256 of the held-out file equals the recorded one.
Every successful read is appended to results/heldout_access.log. Any script that opens the held-out file directly is a bug.
Also used by migrate.py to refuse creating the p3_heldout schema before the freeze.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FREEZE_CONFIG = ROOT / "config/freeze.yaml"
TAG = "protocol-freeze"
ACCESS_LOG = ROOT / "results/heldout_access.log"


class FreezeError(RuntimeError):
    pass


def _git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_freeze(cfg: dict | None = None, git=_git, check_file: bool = True) -> dict:
    """Raises FreezeError unless the freeze conditions hold. Returns the config. `git` is injectable for tests."""
    cfg = cfg if cfg is not None else yaml.safe_load(FREEZE_CONFIG.read_text())
    commit = cfg.get("protocol_freeze_commit")
    if not cfg.get("frozen") or not commit:
        raise FreezeError("protocol not frozen: config/freeze.yaml needs frozen: true and protocol_freeze_commit")
    rc, tagged = git("rev-parse", "--verify", "-q", f"refs/tags/{TAG}^{{commit}}")
    if rc != 0:
        raise FreezeError(f"protocol not frozen: git tag {TAG!r} does not exist")
    if tagged != commit:
        raise FreezeError(f"tag {TAG!r} points at {tagged[:10]}, config says {commit[:10]}")
    if git("merge-base", "--is-ancestor", commit, "HEAD")[0] != 0:
        raise FreezeError("the frozen commit is not an ancestor of HEAD")
    if git("status", "--porcelain", "--untracked-files=no")[1]:
        raise FreezeError("uncommitted changes in the working tree")
    if check_file:
        path = ROOT / cfg["heldout_file"]
        if not cfg.get("heldout_sha256"):
            raise FreezeError("config/freeze.yaml has no heldout_sha256")
        if not path.exists() or sha256_file(path) != cfg["heldout_sha256"]:
            raise FreezeError("held-out file missing or changed since the hash was recorded")
    return cfg


def load_texts(split: str, paths: list[str | Path] | None = None, cfg: dict | None = None, git=_git, log_path: Path = ACCESS_LOG) -> list[dict]:
    """Rows of a text file as dicts. split 'heldout' goes through require_freeze and ignores `paths`; 'dev' and 'smoke' need `paths`."""
    if split == "heldout":
        cfg = require_freeze(cfg, git)
        files = [ROOT / cfg["heldout_file"]]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{cfg['protocol_freeze_commit']}\t{cfg['heldout_sha256']}\t{' '.join(sys.argv)}\n")
    elif split in ("dev", "smoke"):
        if not paths:
            raise ValueError(f"split {split!r} needs paths")
        files = [ROOT / p for p in paths]
        if any("heldout" in str(f) for f in files):
            raise FreezeError("a held-out path was passed as a dev/smoke file")
    else:
        raise ValueError(f"unknown split {split!r}")
    rows = [json.loads(l) for f in files for l in open(f, encoding="utf-8") if l.strip()]
    bad = [r["id"] for r in rows if r["split"] != split]
    if bad:
        raise FreezeError(f"rows with the wrong split for {split!r}: {bad[:3]}")
    return rows
