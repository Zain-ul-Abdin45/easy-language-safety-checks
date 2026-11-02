"""Held-out guard test: every freeze condition is checked with a fake git, plus the real repo state and migrate.py.
Run:  .venv/bin/python tests/test_heldout_guard.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import heldout_guard as G  # noqa: E402

C = "a" * 40


def fake_git(tag=C, ancestor=True, dirty=False):
    def git(*a):
        if a[0] == "rev-parse":
            return (0, tag) if tag else (1, "")
        if a[0] == "merge-base":
            return (0 if ancestor else 1, "")
        if a[0] == "status":
            return 0, (" M file" if dirty else "")
    return git


def raises(fn):
    try:
        fn()
    except G.FreezeError as e:
        return str(e)
    raise AssertionError("expected FreezeError")


with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "h.jsonl"
    f.write_text(json.dumps({"id": "H01", "split": "heldout", "body": "x"}) + "\n")
    good = dict(frozen=True, protocol_freeze_commit=C, heldout_file=str(f), heldout_sha256=G.sha256_file(f))
    log = Path(d) / "access.log"
    G.ROOT = Path("/")   # the temp file path is absolute; ROOT / absolute = absolute
    ld = lambda cfg, git: G.load_texts("heldout", cfg=cfg, git=git, log_path=log)

    assert ld(good, fake_git())[0]["id"] == "H01" and C in log.read_text(), "good case must load and log"
    raises(lambda: ld(dict(good, frozen=False), fake_git()))
    raises(lambda: ld(dict(good, protocol_freeze_commit=None), fake_git()))
    raises(lambda: ld(good, fake_git(tag=None)))               # tag missing
    raises(lambda: ld(good, fake_git(tag="b" * 40)))           # tag moved
    raises(lambda: ld(good, fake_git(ancestor=False)))
    raises(lambda: ld(good, fake_git(dirty=True)))
    raises(lambda: ld(dict(good, heldout_sha256="0" * 64), fake_git()))
    f.write_text("changed\n")
    raises(lambda: ld(good, fake_git()))                       # file changed after hashing
    raises(lambda: G.load_texts("dev", paths=[f"{d}/data/heldout/x.jsonl"]))
print("fake-git cases ok")

G.ROOT = ROOT
rc, _ = G._git("rev-parse", "--verify", "-q", f"refs/tags/{G.TAG}")
if rc == 0:
    print("tag protocol-freeze exists: skipping the real-state checks")
else:
    raises(lambda: G.load_texts("heldout"))
    r = subprocess.run([sys.executable, str(ROOT / "src/migrate.py"), "--schema", "p3_heldout"], capture_output=True, text=True)
    assert r.returncode != 0 and "refusing" in (r.stdout + r.stderr), r.stdout + r.stderr
    print("real state: load_texts('heldout') and migrate.py --schema p3_heldout both refuse")
print("ok")
