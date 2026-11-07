"""Put the combined defenses next to the single ones on Claude Haiku 4.5: benign utility and how
often a defense fires, attack success and utility under attack, by attack, language and injection
kind, with 95% Wilson intervals.

  uv run python scripts/compare_combos.py results [0.9.5]  # reads full-*, armor-<version>-*, combo-<version>-* and planlock-*
"""

import math
import sys
from pathlib import Path

import pandas as pd

root = Path(sys.argv[1])
version = sys.argv[2] if len(sys.argv) > 2 else "0.9.5"
MODEL = "claude-haiku-4-5"
ORDER = ["none", "rule", "lock", "planlock", "armor", "monitor", "rule+lock", "rule+planlock", "rule+armor"]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{p:.3f} [{max(0, c - h):.3f}, {c + h:.3f}]"


stages = ["full-benign", "full-attacked", f"armor-{version}-benign", f"armor-{version}-attacked",
          f"combo-{version}-benign", f"combo-{version}-attacked", "planlock-benign", "planlock-attacked"]
frames = [pd.read_csv(root / f"{stage}/episodes.csv") for stage in stages if (root / stage).exists()]
df = pd.concat(frames, ignore_index=True)
df = df[df.model == MODEL]
for col in ("planlock_blocks", "plan_error"):
    df[col] = df[col].fillna(0) if col in df else 0
df["fired"] = (df.lock_blocks + df.planlock_blocks + df.monitor_blocks + df.armor_blocks) > 0
df["defense"] = pd.Categorical(df.defense, ORDER, ordered=True)
benign, attacked = df[~df.attacked], df[df.attacked]

print(f"{MODEL}, prompt-armor {version}\n\n== Without attack ==")
for d, g in benign.groupby("defense", observed=True):
    print(f"{d:11s} utility {wilson(int(g.utility.sum()), len(g))}  fired {wilson(int(g.fired.sum()), len(g))}  n={len(g)}")

print("\n== With attack: attack success | utility under attack ==")
for (a, d), g in attacked.groupby(["attack", "defense"], observed=True):
    print(f"{a:22s} {d:11s} asr {wilson(int(g.attack_success.sum()), len(g))}  utility {g.utility.mean():.3f}  n={len(g)}")

print("\n== Attack success by language ==")
print(attacked.groupby(["attack", "defense", "lang"], observed=True).attack_success.mean().unstack().round(3).to_string())
print("\n== Attack success by injection kind ==")
print(attacked.groupby(["attack", "injection_kind", "defense"], observed=True).attack_success.mean().unstack().round(3).to_string())
print("\n== Cost per episode (US$) ==")
print(df.groupby("defense", observed=True)[["cost_agent", "cost_monitor"]].mean().sum(axis=1).round(4).to_string())
