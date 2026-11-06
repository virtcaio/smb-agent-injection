"""Run the study (or a slice of it) with Inspect's eval_set.

Examples:
  uv run python scripts/run.py --stage smoke                       # 2 samples x 3 models, no batch
  uv run python scripts/run.py --stage pilot --suites marketplace --tasks 0-5
  uv run python scripts/run.py --stage full --batch

The API key is read from ANTHROPIC_API_KEY. Every model runs at effort "medium", so the three
models differ only in the model itself."""

from __future__ import annotations

import argparse
from pathlib import Path

from inspect_ai import eval_set

from smb_injection.agent import DEFENSES
from smb_injection.core import LANGS
from smb_injection.suites import SUITES
from smb_injection.task import smb_injection

MODELS = ["anthropic/claude-haiku-5-5", "anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5"]
PREVIOUS = ["anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-4-6"]

# Effort "medium" everywhere it exists. Claude Haiku 4.5 has no effort parameter (it errors), so it
# runs with its default: no extended thinking.
EFFORT: dict[str, str | None] = {"anthropic/claude-haiku-4-5": None}


def parse_ids(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    ids: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            ids.extend(range(int(a), int(b) + 1))
        else:
            ids.append(int(part))
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="name of the run; logs go to logs/<stage>")
    ap.add_argument("--suites", default=",".join(SUITES))
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--defenses", default=",".join(DEFENSES))
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--tasks", default=None, help="user task ids, e.g. 0-5 or 0,3,7")
    ap.add_argument("--condition", default="both", choices=["both", "benign", "attacked"])
    ap.add_argument("--attacks", default="important_instructions", help="comma-separated attack templates")
    ap.add_argument("--batch", action="store_true", help="use the Message Batches API (50%% cheaper, slower)")
    ap.add_argument("--max-connections", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tasks = [
        smb_injection(suite=s, lang=lang, defense=d, condition=args.condition, task_ids=parse_ids(args.tasks), batch=args.batch, attack=a)
        for a in args.attacks.split(",")
        for s in args.suites.split(",")
        for lang in args.langs.split(",")
        for d in args.defenses.split(",")
    ]
    all_ok = True
    for model in args.models.split(","):
        # One log directory per model, so each model can use its own generation settings.
        log_dir = Path("logs") / args.stage / model.split("/")[-1]
        ok, _ = eval_set(
            tasks,
            model=model,
            log_dir=str(log_dir),
            effort=EFFORT.get(model, "medium"),
            batch=args.batch or None,
            max_connections=args.max_connections,
            retry_attempts=3,
            limit=args.limit,
            fail_on_error=0.05,
            display="plain",
        )
        all_ok &= ok
    print("all tasks complete" if all_ok else "some tasks did not complete; re-run the same command to resume")


if __name__ == "__main__":
    main()
