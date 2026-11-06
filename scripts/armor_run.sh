#!/usr/bin/env bash
# The armor (prompt-armor) slice of the full run, for one prompt-armor version: every model
# without attack, and Haiku 4.5 (the only model attacks land on) with both attacks.
# Usage: scripts/armor_run.sh <tag>   e.g. 0.9.3. Needs ANTHROPIC_API_KEY in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=${1:?prompt-armor version tag}
OUT=logs/armor-$TAG.log.d
mkdir -p "$OUT"
# One process at a time: each loads its own detector, and the detector calls inside a process
# are serialized (smb_injection/agent.py), so no layer times out on CPU contention.
for m in claude-haiku-4-5 claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5 claude-sonnet-4-6; do
  uv run python scripts/run.py --stage armor-$TAG-benign --models anthropic/$m --defenses armor --condition benign --max-connections 12 >> "$OUT/benign.log" 2>&1
done
uv run python scripts/run.py --stage armor-$TAG-attacked --models anthropic/claude-haiku-4-5 --defenses armor --condition attacked --attacks important_instructions,owner_note --max-connections 12 > "$OUT/attacked.log" 2>&1
echo "armor run $TAG finished"
