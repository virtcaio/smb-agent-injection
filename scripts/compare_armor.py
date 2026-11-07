"""Put the prompt-armor slice next to the other defenses: benign utility and block rate by
language, attack success and utility under attack for Claude Haiku 4.5, by attack, language and
injection kind, with 95% Wilson intervals.

  uv run python scripts/compare_armor.py results [0.9.3]  # reads full-* and armor-<version>-*
"""

import math
import sys
from pathlib import Path

import pandas as pd

root = Path(sys.argv[1])


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def rate(s):
    k, n = int(s.sum()), len(s)
    lo, hi = wilson(k, n)
    return f"{k / n:.3f} [{lo:.3f}, {hi:.3f}] n={n}" if n else "-"


fb = pd.read_csv(root / "full-benign/episodes.csv")
fa = pd.read_csv(root / "full-attacked/episodes.csv")
version = sys.argv[2] if len(sys.argv) > 2 else "0.9.3"
ab = pd.read_csv(root / f"armor-{version}-benign/episodes.csv")
aa = pd.read_csv(root / f"armor-{version}-attacked/episodes.csv")
for df in (fb, fa, ab, aa):
    df["any_block"] = (df.lock_blocks + df.monitor_blocks + df.armor_blocks) > 0

print("skipped layers (L1 rule skips) benign:", int(ab.armor_skipped_layers.sum()), "episodes with any:", int((ab.armor_skipped_layers > 0).sum()), "/", len(ab))
print("skipped layers attacked:", int(aa.armor_skipped_layers.sum()), "episodes with any:", int((aa.armor_skipped_layers > 0).sum()), "/", len(aa))
print("errors:", int(ab.error.sum()), int(aa.error.sum()))

benign = pd.concat([fb[~fb.attacked], ab[~ab.attacked]], ignore_index=True)
print("\n== Benign utility by model x defense x lang ==")
for (m, d), g in benign.groupby(["model", "defense"]):
    row = [f"{m:18s} {d:8s}"]
    for lang in ("en", "pt"):
        gl = g[g.lang == lang]
        row.append(f"{lang}: util {gl.utility.mean():.3f} block {gl.any_block.mean():.3f} (n={len(gl)})")
    print("  ".join(row))

print("\n== Benign utility, armor vs none, pooled CI ==")
for m, g in benign.groupby("model"):
    for d in ("none", "armor"):
        gd = g[g.defense == d]
        print(f"{m:18s} {d:6s} util {rate(gd.utility)}  block {rate(gd.any_block)}")

print("\n== Armor benign: utility when blocked vs not ==")
a = ab[~ab.attacked]
for lang in ("en", "pt"):
    gl = a[a.lang == lang]
    print(lang, "blocked:", rate(gl[gl.any_block].utility), "| not blocked:", rate(gl[~gl.any_block].utility))

print("\n== Armor benign blocks by suite x lang (all models) ==")
print(a.groupby(["suite", "lang"]).any_block.mean().unstack().round(3).to_string())

att = pd.concat([fa[(fa.model == "claude-haiku-4-5") & fa.attacked], aa[aa.attacked]], ignore_index=True)
print("\n== Haiku 4.5 attacked: ASR by attack x defense ==")
for (atk, d), g in att.groupby(["attack", "defense"]):
    print(f"{atk:24s} {d:8s} asr {rate(g.attack_success)}  util_att {g.utility.mean():.3f}")

print("\n== Haiku 4.5 attacked: ASR by attack x defense x lang ==")
print(att.groupby(["attack", "defense", "lang"]).attack_success.mean().unstack().round(3).to_string())

print("\n== Haiku 4.5 attacked: ASR by injection kind (armor vs none) ==")
sub = att[att.defense.isin(["none", "armor"])]
print(sub.groupby(["attack", "injection_kind", "defense"]).attack_success.mean().unstack().round(3).to_string())

print("\n== Armor attacked: episodes with a block, by lang ==")
print(aa.groupby(["attack", "lang"]).any_block.mean().unstack().round(3).to_string())
print("\n== Armor attacked: ASR when no block fired vs when it fired ==")
for atk, g in aa.groupby("attack"):
    print(atk, "blocked:", rate(g[g.any_block].attack_success), "| no block:", rate(g[~g.any_block].attack_success))
