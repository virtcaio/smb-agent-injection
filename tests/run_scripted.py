"""Run the scripted agent through every defense (except the LLM monitor) and print the scores.
Usage: uv run python tests/run_scripted.py <suite> <lang> <log_dir>"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scripted  # noqa: E402,F401  (registers the "scripted" model provider)
from inspect_ai import eval  # noqa: E402

from smb_injection.task import smb_injection  # noqa: E402

suite, lang, log_dir = sys.argv[1], sys.argv[2], sys.argv[3]
for defense in ("none", "rule", "lock", "armor", "rule+lock", "rule+armor"):
    log = eval(smb_injection(suite=suite, lang=lang, defense=defense), model="scripted/gullible", log_dir=log_dir, display="none")[0]
    rows = [s.scores["smb_scorer"].metadata for s in log.samples]
    benign = [r for r in rows if not r["attacked"]]
    attacked = [r for r in rows if r["attacked"]]
    ut_b = sum(r["utility"] for r in benign) / max(1, len(benign))
    ut_a = sum(r["utility"] for r in attacked) / max(1, len(attacked))
    asr = sum(bool(r["attack_success"]) for r in attacked) / max(1, len(attacked))
    flags_benign = sum(any(e["kind"] == "armor" and e["decision"] == "block" for e in r["events"]) for r in benign)
    print(f"{suite}/{lang} {defense:10s} utility benign {ut_b:.2f} | utility attacked {ut_a:.2f} | attack success {asr:.2f} | benign samples with a filter block {flags_benign}/{len(benign)}")
