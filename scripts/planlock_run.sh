#!/usr/bin/env bash
# The realistic lock (planlock) on Claude Haiku 4.5, alone and with the rule, without attack and with
# both attacks. First the planner on its own against the oracle lock (scripts/plan_check.py).
# Usage: scripts/planlock_run.sh [--skip-check]. Needs ANTHROPIC_API_KEY in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=logs/planlock.log.d
mkdir -p "$OUT"
[ "${1:-}" = "--skip-check" ] || uv run python scripts/plan_check.py > "$OUT/plan_check.log" 2>&1
uv run python scripts/run.py --stage planlock-benign --models anthropic/claude-haiku-4-5 --defenses planlock,rule+planlock --condition benign --max-connections 12 > "$OUT/benign.log" 2>&1
uv run python scripts/run.py --stage planlock-attacked --models anthropic/claude-haiku-4-5 --defenses planlock,rule+planlock --condition attacked --attacks important_instructions,owner_note --max-connections 12 > "$OUT/attacked.log" 2>&1
echo "planlock run finished"
