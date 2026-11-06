"""Per-task utility across runs, to find tasks that fail because of the task, not the model.

  uv run python scripts/task_report.py logs/<stage> [logs/<stage> ...]

A task that fails for every model, or for a strong model without attack and without defense,
is a candidate for a check that is too strict or a prompt that is ambiguous."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from analyze import episodes  # noqa: E402

frames = [episodes(d) for d in sys.argv[1:]]
df = pd.concat(frames, ignore_index=True)
benign = df[~df.attacked & (df.defense == "none")]
table = benign.pivot_table(index=["suite", "task_id"], columns=["model", "lang"], values="utility", aggfunc="mean")
table["mean"] = table.mean(axis=1)
weak = table[table["mean"] < 0.75].sort_values("mean")
pd.set_option("display.width", 220)
print(f"{len(weak)} of {len(table)} tasks below 75% benign utility without defense:\n")
print(weak.round(2).to_string())
