#!/usr/bin/env bash
# The full run (November 2026), one process per model, after the pilot and the probes.
# Claude 5.5 models resisted every attack framing in the probes (0 of 2,000+ attacked episodes) and
# Sonnet 4.6 nearly so (2 of 324), so they run every defense without attack (utility cost) and both
# attacks without defense. Haiku 4.5, where attacks land (10% to 37%), runs the whole grid. The armor defense runs
# separately, one prompt-armor version at a time (scripts/armor_run.sh). Needs ANTHROPIC_API_KEY in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-logs/full-run.log.d}
mkdir -p "$OUT"
DEF=none,rule,lock,monitor
ATT=important_instructions,owner_note

for m in claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5 claude-sonnet-4-6; do
  ( uv run python scripts/run.py --stage full-benign --models anthropic/$m --defenses $DEF --condition benign --max-connections 16
    uv run python scripts/run.py --stage full-attacked --models anthropic/$m --defenses none --condition attacked --attacks $ATT --max-connections 16
  ) > "$OUT/$m.log" 2>&1 &
done
for m in claude-haiku-4-5; do
  ( uv run python scripts/run.py --stage full-benign --models anthropic/$m --defenses $DEF --condition benign --max-connections 16
    uv run python scripts/run.py --stage full-attacked --models anthropic/$m --defenses $DEF --condition attacked --attacks $ATT --max-connections 16
  ) > "$OUT/$m.log" 2>&1 &
done
wait
echo "full run finished"
