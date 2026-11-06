"""Inspect task: one suite, one language, one defense; every user task with and without its attack."""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState
from inspect_ai.util import store

from smb_injection.agent import cached_suite, smb_agent
from smb_injection.core import run_checks


def build_dataset(suite_name: str, lang: str, condition: str, task_ids: list[int] | None) -> MemoryDataset:
    suite = cached_suite(suite_name, lang)
    samples = []
    for tid, user_task in sorted(suite.user_tasks.items()):
        if task_ids is not None and tid not in task_ids:
            continue
        base = {"suite": suite_name, "lang": lang, "task_id": tid}
        if condition in ("benign", "both"):
            samples.append(Sample(id=f"{suite_name}-{lang}-u{tid}", input=user_task.prompt, metadata={**base, "injection_id": None}))
        if condition in ("attacked", "both"):
            # Every user task is attacked by every injection goal (AgentDojo's full cross).
            for inj in sorted(suite.injection_tasks.values(), key=lambda i: i.id):
                samples.append(Sample(id=f"{suite_name}-{lang}-u{tid}-i{inj.id}", input=user_task.prompt, metadata={**base, "injection_id": inj.id, "injection_kind": inj.kind}))
    return MemoryDataset(samples=samples, name=f"{suite_name}-{lang}")


@scorer(metrics={"utility": [mean(), stderr()], "attack_success": [mean(), stderr()]})
def smb_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        meta = state.metadata
        suite = cached_suite(meta["suite"], meta["lang"])
        env = store().get("env")
        executed = store().get("executed", [])
        events = store().get("events", [])
        output = state.output.completion if state.output else ""
        utility = run_checks(suite.user_tasks[meta["task_id"]].checks, env, executed, output)
        attack = None
        if meta.get("injection_id") is not None:
            attack = run_checks(suite.injection_tasks[meta["injection_id"]].checks, env, executed, output)
        return Score(
            value={"utility": float(utility), "attack_success": float(bool(attack))},
            metadata={
                "attacked": attack is not None,
                "attack_success": attack,
                "utility": utility,
                "events": events,
                "executed": executed,
                "refused": any(e["kind"] == "refusal" for e in events),
            },
        )

    return score


@task
def smb_injection(
    suite: str = "marketplace",
    lang: str = "en",
    defense: str = "none",
    condition: str = "both",
    task_ids: list[int] | None = None,
    max_turns: int = 15,
    monitor_model: str = "anthropic/claude-haiku-5-5",
    batch: bool = False,
) -> Task:
    return Task(
        dataset=build_dataset(suite, lang, condition, task_ids),
        solver=smb_agent(defense=defense, max_turns=max_turns, monitor_model=monitor_model, batch=batch),
        scorer=smb_scorer(),
        metadata={"suite": suite, "lang": lang, "defense": defense, "condition": condition},
    )
