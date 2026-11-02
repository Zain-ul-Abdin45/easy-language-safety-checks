"""Run a v2 script with the pinned chat-template date:  python src/run_pinned.py src/d4_screen.py [args]   (pilot.py stays untouched)."""
import runpy
import sys

import prompt_pin

prompt_pin.install()
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
