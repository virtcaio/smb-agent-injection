"""Validate a suite's data: every task solvable by its ground truth, non-trivial, exposed to an
injection vector, robust to the attack text, and every injection goal checkable and not
triggered by a benign solution. Run: uv run python scripts/validate.py [suite ...]"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smb_injection.attacks import attack_text  # noqa: E402
from smb_injection.core import LANGS, Suite, execute_locally, load_suite, run_checks  # noqa: E402
from smb_injection.suites import SUITES  # noqa: E402


def _check_args(suite: Suite, calls: list[dict], where: str, errors: list[str]) -> None:
    for call in calls:
        spec = suite.tool(call.get("tool", ""))
        if spec is None:
            errors.append(f"{where}: unknown tool '{call.get('tool')}'")
            continue
        try:
            inspect.signature(spec.fn).bind(**(call.get("args") or {}))
        except TypeError as exc:
            errors.append(f"{where}: bad args for {spec.name}: {exc}")


async def validate_lang(suite: Suite) -> tuple[list[str], dict]:
    errors: list[str] = []
    stats = {"tasks": len(suite.user_tasks), "injections": len(suite.injection_tasks), "lock_passes": 0}
    used = suite.placeholders()
    declared = set(suite.vectors)
    if used - declared:
        errors.append(f"placeholders without a vector: {sorted(used - declared)}")
    if declared - used:
        errors.append(f"vectors never used in environment.yaml: {sorted(declared - used)}")
    if sorted(suite.user_tasks) != list(range(len(suite.user_tasks))):
        errors.append("user task ids must be 0..N-1")
    if not suite.injection_tasks:
        errors.append("no injection tasks")
        return errors, stats
    try:
        suite.build_env()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"environment does not load: {exc}")
        return errors, stats

    attack = attack_text(suite, next(iter(suite.injection_tasks.values())))
    for tid, task in suite.user_tasks.items():
        where = f"user task {tid}"
        _check_args(suite, task.ground_truth, where, errors)
        if not task.checks:
            errors.append(f"{where}: no checks")
            continue
        env = suite.build_env()
        if run_checks(task.checks, env, [], ""):
            errors.append(f"{where}: checks pass with no action and no answer (trivial)")
        executed, _ = await execute_locally(suite, env, task.ground_truth)
        if len(executed) != len(task.ground_truth):
            errors.append(f"{where}: some ground-truth calls failed")
        if not run_checks(task.checks, env, executed, task.ground_truth_output):
            errors.append(f"{where}: ground truth does not pass its own checks")
        sentinel_env = suite.build_env(overrides={v: f" SENTINEL_{v} " for v in suite.vectors})
        _, outputs = await execute_locally(suite, sentinel_env, task.ground_truth)
        reached = {v for v in suite.vectors if any(f"SENTINEL_{v}" in o for o in outputs)}
        if not reached:
            errors.append(f"{where}: the ground truth never reads an injection vector")
        attacked_env = suite.build_env(injection=attack)
        executed_a, _ = await execute_locally(suite, attacked_env, task.ground_truth)
        if not run_checks(task.checks, attacked_env, executed_a, task.ground_truth_output):
            errors.append(f"{where}: ground truth fails its checks when the attack text is present")
        inj = suite.injection_for(tid)
        if run_checks(inj.checks, attacked_env, executed_a, task.ground_truth_output):
            errors.append(f"{where}: the benign solution already satisfies injection {inj.id} (false attack success)")
        scope = suite.scope(task)
        blocked = False
        for call in inj.ground_truth:
            spec = suite.tool(call["tool"])
            if spec and spec.side_effect:
                target = "*" if spec.target_arg is None else str(call["args"].get(spec.target_arg, "")).strip().lower()
                if target not in scope.get(spec.name, set()):
                    blocked = True
        stats["lock_passes"] += 0 if blocked else 1

    for iid, inj in suite.injection_tasks.items():
        where = f"injection task {iid}"
        _check_args(suite, inj.ground_truth, where, errors)
        if not inj.checks:
            errors.append(f"{where}: no checks")
            continue
        env = suite.build_env()
        if run_checks(inj.checks, env, [], ""):
            errors.append(f"{where}: checks pass with no action (trivial)")
        executed, _ = await execute_locally(suite, env, inj.ground_truth)
        if not run_checks(inj.checks, env, executed, ""):
            errors.append(f"{where}: ground truth does not pass its own checks")
    return errors, stats


async def main(names: list[str]) -> int:
    failed = False
    for name in names:
        by_lang = {}
        for lang in LANGS:
            try:
                suite = load_suite(name, lang)
            except FileNotFoundError as exc:
                print(f"[{name}/{lang}] missing file: {exc.filename}")
                failed = True
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"[{name}/{lang}] does not load: {exc}")
                failed = True
                continue
            by_lang[lang] = suite
            errors, stats = await validate_lang(suite)
            status = "OK" if not errors else f"{len(errors)} problem(s)"
            print(f"[{name}/{lang}] {stats['tasks']} tasks, {stats['injections']} injections, "
                  f"{stats['lock_passes']} paired attacks would pass the permission lock: {status}")
            for e in errors:
                print(f"  - {e}")
            failed |= bool(errors)
        if len(by_lang) == 2:
            pt, en = by_lang["pt"], by_lang["en"]
            if set(pt.user_tasks) != set(en.user_tasks) or set(pt.injection_tasks) != set(en.injection_tasks):
                print(f"[{name}] task ids differ between pt and en")
                failed = True
            for tid in set(pt.user_tasks) & set(en.user_tasks):
                a = [c["tool"] for c in pt.user_tasks[tid].ground_truth]
                b = [c["tool"] for c in en.user_tasks[tid].ground_truth]
                if a != b:
                    print(f"[{name}] user task {tid}: ground-truth tools differ between pt and en: {a} vs {b}")
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or list(SUITES))))
