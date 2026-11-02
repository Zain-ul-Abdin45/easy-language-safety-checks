"""Is the machine in the state a timing run needs? On mains, no low-power mode, no thermal speed limit, no other process using 10% CPU or more.
Run:  .venv/bin/python src/machine_ready.py [--wait MINUTES]     exit 0 = ready, 1 = not ready (after waiting up to MINUTES, polling every 20 s)
"""
import argparse
import sys
import time

import tokens_store as T


def reasons(m: dict) -> list[str]:
    r = []
    if not m["on_ac"]:
        r.append("on battery")
    if m["low_power_mode"]:
        r.append("low-power mode on")
    if (m["cpu_speed_limit"] or 100) < 100:
        r.append(f"CPU speed limited to {m['cpu_speed_limit']}%")
    if m["other_busy"]:
        r.append("other processes busy: " + ", ".join(m["other_busy"]))
    return r


def heavy_ok_reasons(m: dict, floor: int = 20) -> list[str]:
    """Untimed heavy work only needs enough power to finish: on mains, or battery at or above the floor."""
    return [] if m["on_ac"] or int(m["battery"] or 100) >= floor else [f"battery at {m['battery']}% and not charging"]


def wait_ready(minutes: float = 0, poll: int = 20, say=print, heavy_ok: bool = False) -> bool:
    deadline = time.time() + 60 * minutes
    last = None
    while True:
        r = heavy_ok_reasons(T.machine_state()) if heavy_ok else reasons(T.machine_state())
        if not r:
            return True
        if r != last:
            say(f"{time.strftime('%H:%M:%S')} not ready: {'; '.join(r)}")
            last = r
        if time.time() >= deadline:
            return False
        time.sleep(poll)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=0)
    ap.add_argument("--heavy-ok", action="store_true", help="only check there is enough power for untimed heavy work (mains, or battery of at least 20%)")
    a = ap.parse_args()
    ok = wait_ready(a.wait, say=lambda s: print(s, flush=True), heavy_ok=a.heavy_ok)
    print("ready" if ok else "NOT ready")
    sys.exit(0 if ok else 1)
