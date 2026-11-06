"""The detector alone, with no model in the loop: run prompt-armor over every tool result of every
ground-truth trajectory, without attack and with each attack, in both languages.

  uv run python scripts/detector_offline.py [--attacks important_instructions,owner_note]

Per suite and language it reports the share of benign tool results the detector blocks (false
positives) and the share of tool results carrying the attack that it blocks (detection), plus
the same at the episode level (any block in the trajectory)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from prompt_armor import analyze  # noqa: E402

from smb_injection.attacks import attack_text  # noqa: E402
from smb_injection.core import LANGS, execute_locally, load_suite  # noqa: E402
from smb_injection.suites import SUITES  # noqa: E402


async def trajectory_outputs(suite, task, injection: str | None) -> list[str]:
    env = suite.build_env(injection=injection)
    _, outputs = await execute_locally(suite, env, task.ground_truth)
    return outputs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacks", default="important_instructions,owner_note")
    ap.add_argument("--out", default="results/detector-offline")
    args = ap.parse_args()
    import importlib.metadata as md

    version = md.version("prompt-armor")
    rows = []
    for name in SUITES:
        for lang in LANGS:
            suite = load_suite(name, lang)
            for tid, task in suite.user_tasks.items():
                for out in asyncio.run(trajectory_outputs(suite, task, None)):
                    r = analyze(out)
                    rows.append({"suite": name, "lang": lang, "task_id": tid, "attack": None, "injection_id": None, "carries_attack": False, "decision": r.decision.value, "risk": r.risk_score})
                for attack in args.attacks.split(","):
                    for inj in suite.injection_tasks.values():
                        text = attack_text(suite, inj, attack)
                        for out in asyncio.run(trajectory_outputs(suite, task, text)):
                            carries = text.strip()[:40] in out or inj.goal[:40] in out
                            if not carries:
                                continue
                            r = analyze(out)
                            rows.append({"suite": name, "lang": lang, "task_id": tid, "attack": attack, "injection_id": inj.id, "carries_attack": True, "decision": r.decision.value, "risk": r.risk_score})
            print(f"{name}/{lang} done", flush=True)
    df = pd.DataFrame(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "tool_outputs.csv", index=False)
    df["blocked"] = df.decision == "block"
    benign = df[~df.carries_attack]
    attacked = df[df.carries_attack]
    print(f"\nprompt-armor {version}")
    print("\nTool results WITHOUT attack blocked (false positives), by language:")
    print(benign.groupby(["lang"]).blocked.agg(["mean", "sum", "count"]).round(3).to_string())
    print(benign.groupby(["suite", "lang"]).blocked.mean().unstack().round(3).to_string())
    print("\nTool results CARRYING the attack blocked (detection), by attack and language:")
    print(attacked.groupby(["attack", "lang"]).blocked.agg(["mean", "count"]).round(3).to_string())
    ep_b = benign.groupby(["suite", "lang", "task_id"]).blocked.any().groupby("lang").mean()
    print("\nBenign episodes with at least one block, by language:")
    print(ep_b.round(3).to_string())


if __name__ == "__main__":
    main()
