#!/usr/bin/env bash
# Combined defenses on Claude Haiku 4.5, the only model attacks land on: the rule plus the lock, and
# the rule plus the prompt-armor filter, without attack and with both attacks.
# Usage: scripts/combo_run.sh <prompt-armor version>   e.g. 0.9.5. Needs ANTHROPIC_API_KEY in the environment.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=${1:?prompt-armor version tag}
INSTALLED=$(uv run python -c "import importlib.metadata as m; print(m.version('prompt-armor'))")
[ "$INSTALLED" = "$TAG" ] || { echo "prompt-armor $INSTALLED is installed, not $TAG; change the pin in pyproject.toml" >&2; exit 1; }
OUT=logs/combo-$TAG.log.d
mkdir -p "$OUT"
# One process per condition; detector calls inside it are serialized (smb_injection/agent.py).
uv run python scripts/run.py --stage combo-$TAG-benign --models anthropic/claude-haiku-4-5 --defenses rule+lock,rule+armor --condition benign --max-connections 12 > "$OUT/benign.log" 2>&1
uv run python scripts/run.py --stage combo-$TAG-attacked --models anthropic/claude-haiku-4-5 --defenses rule+lock,rule+armor --condition attacked --attacks important_instructions,owner_note --max-connections 12 > "$OUT/attacked.log" 2>&1
echo "combo run $TAG finished"
