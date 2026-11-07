"""Turn Inspect logs into one row per episode and the study's tables.

  uv run python scripts/analyze.py logs/<stage> [--out results/<stage>]

Outputs episodes.csv (one row per sample), summary.csv (per model x defense, with 95% Wilson
intervals) and cost.csv (tokens and dollars per episode, by model)."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd
from inspect_ai.log import list_eval_logs, read_eval_log

from smb_injection.agent import cached_suite
from smb_injection.core import run_checks

# US$ per million tokens: input, output, cache read, cache write (5 min). Batch halves all four.
PRICES = {
    "claude-haiku-4-5": (1.00, 5.00, 0.10, 1.25),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30, 3.75),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}


def cost(model: str, usage, batch: bool) -> float:
    key = model.split("/")[-1]
    if key not in PRICES:
        return float("nan")
    p_in, p_out, p_read, p_write = PRICES[key]
    total = (
        usage.input_tokens * p_in
        + usage.output_tokens * p_out
        + (usage.input_tokens_cache_read or 0) * p_read
        + (usage.input_tokens_cache_write or 0) * p_write
    ) / 1e6
    return total * (0.5 if batch else 1.0)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def rescore(s) -> tuple[bool, bool | None]:
    """Recompute utility and attack success from the logged final environment, executed calls
    and answer, with the current check definitions (so a fixed check applies to old logs too)."""
    suite = cached_suite(s.metadata["suite"], s.metadata["lang"])
    store = s.store or {}
    env, executed = store.get("env") or {}, store.get("executed") or []
    output = s.output.completion if s.output else ""
    utility = run_checks(suite.user_tasks[s.metadata["task_id"]].checks, env, executed, output)
    inj = s.metadata.get("injection_id")
    attack = None if inj is None else run_checks(suite.injection_tasks[inj].checks, env, executed, output)
    return utility, attack


def episodes(log_dir: str) -> pd.DataFrame:
    rows = []
    for info in list_eval_logs(log_dir, recursive=True):
        log = read_eval_log(info)
        if log.status != "success" or not log.samples:
            continue
        model = log.eval.model
        meta = log.eval.task_args
        batch = bool(meta.get("batch"))
        for s in log.samples:
            sc = s.scores.get("smb_scorer") if s.scores else None
            if sc is None:
                continue
            m = sc.metadata or {}
            events = m.get("events", [])
            usage = s.model_usage or {}
            agent_cost = sum(cost(k, u, batch) for k, u in usage.items() if k == model)
            monitor_cost = sum(cost(k, u, batch) for k, u in usage.items() if k != model)
            agent_usage = usage.get(model)
            utility, attack_success = rescore(s)
            rows.append({
                "model": model.split("/")[-1],
                "suite": s.metadata["suite"],
                "lang": s.metadata["lang"],
                "defense": meta.get("defense"),
                "attack": meta.get("attack", "important_instructions"),
                "task_id": s.metadata["task_id"],
                "attacked": bool(m.get("attacked")),
                "injection_id": s.metadata.get("injection_id"),
                "injection_kind": {"link": "exfil", "price": "state"}.get(s.metadata.get("injection_kind"), s.metadata.get("injection_kind")),
                "utility": bool(utility),
                "attack_success": bool(attack_success) if attack_success is not None else None,
                "logged_attack_success": bool(m.get("attack_success")) if m.get("attacked") else None,
                "refused": bool(m.get("refused")),
                "lock_blocks": sum(e["kind"] == "lock_block" for e in events),
                "planlock_blocks": sum(e["kind"] == "planlock_block" for e in events),
                "plan_error": any(e["kind"] == "plan" and e.get("error") for e in events),
                "monitor_blocks": sum(e["kind"] == "monitor_block" for e in events),
                "armor_blocks": sum(e["kind"] == "armor" and e.get("decision") == "block" for e in events),
                "armor_skipped_layers": sum(e.get("skipped_layers", 0) for e in events if e["kind"] == "armor"),
                "turns": sum(1 for msg in s.messages if msg.role == "assistant"),
                "input_tokens": getattr(agent_usage, "input_tokens", 0),
                "output_tokens": getattr(agent_usage, "output_tokens", 0),
                "cache_read_tokens": getattr(agent_usage, "input_tokens_cache_read", 0) or 0,
                "cost_agent": agent_cost,
                "cost_monitor": monitor_cost,
                "error": bool(s.error),
            })
    return pd.DataFrame(rows)


def summary(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (model, attack, defense), g in df.groupby(["model", "attack", "defense"]):
        benign, attacked = g[~g.attacked], g[g.attacked]
        k_asr, n_asr = int(attacked.attack_success.sum()), len(attacked)
        k_ub, n_ub = int(benign.utility.sum()), len(benign)
        k_ua, n_ua = int(attacked.utility.sum()), len(attacked)
        fp = int(((benign.lock_blocks + benign.planlock_blocks + benign.monitor_blocks + benign.armor_blocks) > 0).sum())
        out.append({
            "model": model, "attack": attack, "defense": defense,
            "attack_success": k_asr / n_asr if n_asr else float("nan"), "asr_ci": wilson(k_asr, n_asr),
            "utility_benign": k_ub / n_ub if n_ub else float("nan"), "ub_ci": wilson(k_ub, n_ub),
            "utility_attacked": k_ua / n_ua if n_ua else float("nan"), "ua_ci": wilson(k_ua, n_ua),
            "benign_with_defense_block": fp / n_ub if n_ub else float("nan"), "fp_ci": wilson(fp, n_ub),
            "refusals": int(g.refused.sum()),
            "cost_per_episode": (g.cost_agent + g.cost_monitor).mean(),
            "n_benign": n_ub, "n_attacked": n_asr,
        })
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    df = episodes(args.log_dir)
    if df.empty:
        print("no finished samples")
        return
    out = Path(args.out or Path("results") / Path(args.log_dir).name)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "episodes.csv", index=False)
    s = summary(df)
    s.to_csv(out / "summary.csv", index=False)
    c = df.groupby("model")[["input_tokens", "output_tokens", "cache_read_tokens", "turns", "cost_agent", "cost_monitor"]].mean()
    c["episodes"] = df.groupby("model").size()
    c["total_cost"] = df.groupby("model")[["cost_agent", "cost_monitor"]].sum().sum(axis=1)
    c.to_csv(out / "cost.csv")
    pd.set_option("display.width", 200)
    print(s[["model", "attack", "defense", "attack_success", "utility_benign", "utility_attacked", "benign_with_defense_block", "refusals", "cost_per_episode", "n_attacked"]].round(3).to_string(index=False))
    print()
    print(c.round(4).to_string())
    print(f"\ntotal cost: US$ {c.total_cost.sum():.2f}")


if __name__ == "__main__":
    main()
