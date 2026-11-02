#!/bin/bash
# Overnight v3 run. Start it, plug in the charger, go to sleep.
#
#   cd "/Users/kashifali/Documents/Research Project/Project 3"
#   nohup caffeinate -i bash scripts/overnight_v3.sh > results/v3/overnight_console.log 2>&1 &
#
# Keep the lid open (a closed lid sleeps the Mac even under caffeinate). Quit Chrome and other apps first: the timed stages refuse to start while
# another process uses 10% CPU or more, and wait for it.
#
# What it does, in order (about 1 to 1.5 hours of work; the timed part is about 15 minutes):
#   0  preflight: environment check, database dump (outside the repo), fast tests
#   if the machine is ready (mains, nothing else busy) at the start:  timed stages first, then the reproduction
#   otherwise:                                                        the reproduction first (needs no mains), then wait for the charger
#   T1 D5 timing study         why 0.045 s per sentence in v2 and about 0.4 in the first v3 output; batching and thread count compared
#   T2 clean overhead run      1 warm-up output (discarded) + 27 measured, mains, nothing else running; median and max for D5 alone and the full pipeline
#   R  reproduction            every dev script re-run against the stored outputs and labels, for Qwen and Llama; D4 regenerates to score
#   R2 comparison with the reported files, and the 0.404 / 0.409 go/no-go check
#   S  summary in results/v3/overnight_summary.md
# A failed stage is logged and the run continues with the next one. Nothing writes to the labelled schemas p3, p3_second, p3_sbs (read-only), no git
# commands that change anything, no model download (offline).
#
# DRY=1 bash scripts/overnight_v3.sh   prints the plan without running anything.
# WAIT_MIN=180 (default) is how long the timed stages wait for the charger and an idle machine.

set -u
ROOT="/Users/kashifali/Documents/Research Project/Project 3"
cd "$ROOT" || exit 1
PY=.venv/bin/python
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="results/v3/overnight/$STAMP"
SCHEMA="p3_v3_ovh_$STAMP"
WAIT_MIN=${WAIT_MIN:-180}
DRY=${DRY:-0}
mkdir -p "$LOG" results/v3/repro/qwen results/v3/repro/llama "$HOME/Backups/project3"
set -a; . ./.env; set +a
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1
STATUS="$LOG/status.tsv"; : > "$STATUS"

say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG/run.log"; }
stage() {   # stage NAME COMMAND...   (stdout and stderr to $LOG/NAME.log; the exit code goes to status.tsv)
  local name=$1; shift
  say "START $name"
  if [ "$DRY" = 1 ]; then say "  dry run: $*"; printf "%s\t%s\t%s\t%s\n" "$name" "dry" 0 "$*" >> "$STATUS"; return 0; fi
  local t0=$(date +%s); "$@" > "$LOG/$name.log" 2>&1; local rc=$?
  printf "%s\t%s\t%s\t%s\n" "$name" "$([ $rc = 0 ] && echo ok || echo FAILED)" "$(( $(date +%s) - t0 ))" "$rc" >> "$STATUS"
  say "END   $name rc=$rc ($(( $(date +%s) - t0 ))s)"
}
ready_now() { [ "$DRY" = 1 ] && return 0; $PY src/machine_ready.py --wait 0 > /dev/null 2>&1; }

timed_stages() {
  say "waiting up to ${WAIT_MIN} min for mains power and an idle machine"
  if [ "$DRY" != 1 ] && ! $PY src/machine_ready.py --wait "$WAIT_MIN" >> "$LOG/run.log" 2>&1; then
    say "SKIPPED the timed stages: the machine did not become ready (mains, nothing else busy) within ${WAIT_MIN} min"
    printf "%s\t%s\t%s\t%s\n" timed_stages SKIPPED 0 "not ready" >> "$STATUS"; return
  fi
  stage d5_timing_study $PY src/d5_timing_study.py --outputs 12
  # the machine can change state between the two; the report flags every output that ran unclean
  [ "$DRY" != 1 ] && $PY src/machine_ready.py --wait 5 >> "$LOG/run.log" 2>&1
  stage overhead_migrate $PY src/migrate.py --schema "$SCHEMA"
  stage overhead_run $PY src/generate_v3.py --schema "$SCHEMA" --split smoke --texts data/smoke/smoke_texts.jsonl \
        --seeds 0 1 2 3 4 5 6 --allow-dirty --warmup 1 --min-measured 20
}

repro_model() {   # repro_model NAME REFDIR SCHEMA CONFIG
  local m=$1 ref=$2 schema=$3 cfg=$4 out="results/v3/repro/$1"
  cp "$ref/omission_backfill_confirmed.csv" "$out/" 2>/dev/null     # hand-confirmed input of the D3 screen, not a result
  local env="ANNOTATE_DIR=$out DB_SCHEMA=$schema"; [ -n "$cfg" ] && env="$env PILOT_CONFIG=$cfg"
  stage "${m}_controls"        env $env $PY src/controls.py
  stage "${m}_sentence_screen" env $env $PY src/sentence_screen.py
  stage "${m}_digit_guard"     env $env $PY src/digit_guard.py
  stage "${m}_d4_regenerate"   env $env $PY src/run_pinned.py src/d4_screen.py          # regenerates each output with its seed: the slow step
  stage "${m}_d5"              env $env $PY src/d5_screen.py          # both NLI models
  stage "${m}_d3"              env $env $PY src/d3_screen.py          # reads the D4 and D5 scores written just above
  stage "${m}_auc_decision"    env $env $PY src/auc_decision.py
}
reproduction() {
  [ "$DRY" != 1 ] && $PY src/machine_ready.py --heavy-ok --wait "$WAIT_MIN" >> "$LOG/run.log" 2>&1
  repro_model qwen  results/dev24       p3        ""
  repro_model llama results/llama_dev24 p3_second config/second_model.yaml
  stage repro_compare $PY src/repro_compare.py
}

say "overnight v3 run $STAMP; schema for the overhead run: $SCHEMA; log folder: $LOG"
stage preflight_env     $PY src/check_env.py
stage backup            bash -c "pg_dump \"$DATABASE_URL\" -n p3 -n p3_second -n p3_sbs -f \"$HOME/Backups/project3/easylang_p3_$STAMP.sql\" && test -s \"$HOME/Backups/project3/easylang_p3_$STAMP.sql\""
stage tests_flag_rule   $PY tests/test_flag_rule.py
stage tests_guard       $PY tests/test_heldout_guard.py
stage tests_dirty       $PY tests/test_dirty_refusal.py
stage tests_d5_labels   $PY tests/test_d5_labels.py
stage tests_roundtrip   $PY tests/test_token_roundtrip.py
stage tests_driver      $PY tests/test_driver_scratch.py
stage tests_prompt_pin  $PY tests/test_prompt_pin.py

if ready_now; then
  say "machine ready at the start: timed stages first"
  timed_stages; reproduction
else
  say "machine not ready at the start ($(pmset -g batt | head -2 | tail -1 | cut -c1-60)): reproduction first, then wait for the charger"
  reproduction; timed_stages
fi

stage summary $PY scripts/overnight_summary.py "$LOG" "$SCHEMA"
say "DONE. Read results/v3/overnight_summary.md"
touch "$LOG/DONE"
