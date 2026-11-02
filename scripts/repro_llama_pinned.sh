#!/bin/bash
# Re-run of the Llama part of the reproduction with the chat-template date pinned (config/model_pins.yaml). Same stages as overnight_v3.sh.
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
export HF_HUB_OFFLINE=1 ANNOTATE_DIR=results/v3/repro/llama DB_SCHEMA=p3_second PILOT_CONFIG=config/second_model.yaml
PY=.venv/bin/python
for s in controls sentence_screen digit_guard; do $PY src/$s.py > /dev/null || echo "FAILED $s"; done
$PY src/run_pinned.py src/d4_screen.py > results/v3/repro/llama/d4_console.log 2>&1 || echo "FAILED d4"
for s in d5_screen d3_screen auc_decision; do $PY src/$s.py > /dev/null || echo "FAILED $s"; done
$PY src/repro_compare.py > /dev/null || echo "FAILED compare"
echo DONE
