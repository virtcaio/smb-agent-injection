"""Simulated environments as data, tools over a shared environment, and declarative checks.

Each suite (one small-business workflow) has, per language, a YAML environment with
injection placeholders, a list of user tasks and a list of injection tasks. Tasks are
declarative: ground-truth tool calls plus checks over the final environment, the executed
tool calls and the agent's final answer. The same task ids exist in Portuguese and English.
"""

from __future__ import annotations

import contextvars
import copy
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

DATA_DIR = Path(__file__).parent / "data"
LANGS = ("pt", "en")

# Placeholder syntax inside environment.yaml: {{inj:vector_name}}
_PLACEHOLDER = re.compile(r"\{\{inj:([a-z0-9_]+)\}\}")

# Outside an Inspect sample (validation), tools read the environment from here.
_LOCAL_ENV: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "local_env", default=None
)


def current_env() -> dict[str, Any]:
    env = _LOCAL_ENV.get()
    if env is not None:
        return env
    from inspect_ai.util import store

    env = store().get("env")
    if env is None:
        raise RuntimeError("No environment in the sample store")
    return env


def save_env(env: dict[str, Any]) -> None:
    if _LOCAL_ENV.get() is not None:
        return
    from inspect_ai.util import store

    store().set("env", env)


def get_item(env: dict[str, Any], collection: str, item_id: str) -> dict[str, Any]:
    items = env.get(collection) or {}
    if item_id not in items:
        raise KeyError(f"{collection[:-1] if collection.endswith('s') else collection} '{item_id}' not found")
    return items[item_id]


# --------------------------------------------------------------------------- suites


@dataclass
class ToolSpec:
    fn: Callable[..., Awaitable[str]]
    side_effect: bool = False
    # Argument that names the object the action touches (used by the permission lock).
    # None for side-effect tools without a natural target (e.g. setting an issue title).
    target_arg: str | None = None

    @property
    def name(self) -> str:
        return self.fn.__name__


@dataclass
class UserTask:
    id: int
    prompt: str
    ground_truth: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    ground_truth_output: str = ""
    comment: str = ""


@dataclass
class InjectionTask:
    id: int
    goal: str
    ground_truth: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    kind: str = ""


@dataclass
class Suite:
    name: str
    lang: str
    meta: dict[str, Any]
    environment_text: str
    vectors: dict[str, str]
    user_tasks: dict[int, UserTask]
    injection_tasks: dict[int, InjectionTask]
    tools: list[ToolSpec] = field(default_factory=list)

    def tool(self, name: str) -> ToolSpec | None:
        return next((t for t in self.tools if t.name == name), None)

    def build_env(self, injection: str | None = None, overrides: dict[str, str] | None = None) -> dict[str, Any]:
        """The environment with every injection vector filled: by its benign default, by the
        attack text (all vectors at once, as in AgentDojo), or by per-vector overrides.
        Placeholders are filled after YAML parsing, so attack text never breaks the YAML."""
        values = dict(self.vectors)
        if injection is not None:
            values = {k: injection for k in values}
        if overrides:
            values.update(overrides)

        def fill(node: Any) -> Any:
            if isinstance(node, str):
                return _PLACEHOLDER.sub(lambda m: values[m.group(1)], node)
            if isinstance(node, dict):
                return {k: fill(v) for k, v in node.items()}
            if isinstance(node, list):
                return [fill(v) for v in node]
            return node

        return fill(yaml.safe_load(self.environment_text))

    def placeholders(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.environment_text))

    def injection_for(self, user_task_id: int) -> InjectionTask:
        """One injection per user task, rotating through the suite's injection tasks."""
        ids = sorted(self.injection_tasks)
        return self.injection_tasks[ids[user_task_id % len(ids)]]

    def scope(self, task: UserTask) -> dict[str, set[str]]:
        """Oracle least-privilege scope: the side-effect actions the user's request needs."""
        allowed: dict[str, set[str]] = {}
        for call in task.ground_truth:
            spec = self.tool(call["tool"])
            if spec is None or not spec.side_effect:
                continue
            target = "*" if spec.target_arg is None else str(call["args"].get(spec.target_arg, "")).strip().lower()
            allowed.setdefault(spec.name, set()).add(target)
        return allowed


def load_suite(name: str, lang: str) -> Suite:
    from smb_injection.suites import SUITE_TOOLS

    base = DATA_DIR / name / lang
    meta = yaml.safe_load((base / "meta.yaml").read_text(encoding="utf-8"))
    environment_text = (base / "environment.yaml").read_text(encoding="utf-8")
    vectors_raw = yaml.safe_load((base / "injection_vectors.yaml").read_text(encoding="utf-8")) or {}
    vectors = {k: (v.get("default", "") if isinstance(v, dict) else str(v or "")) for k, v in vectors_raw.items()}
    tasks_raw = yaml.safe_load((base / "user_tasks.yaml").read_text(encoding="utf-8")) or []
    inj_raw = yaml.safe_load((base / "injection_tasks.yaml").read_text(encoding="utf-8")) or []
    user_tasks = {
        int(t["id"]): UserTask(
            id=int(t["id"]),
            prompt=t["prompt"].strip(),
            ground_truth=t.get("ground_truth") or [],
            checks=t.get("checks") or [],
            ground_truth_output=(t.get("ground_truth_output") or "").strip(),
            comment=t.get("comment", ""),
        )
        for t in tasks_raw
    }
    injection_tasks = {
        int(t["id"]): InjectionTask(
            id=int(t["id"]),
            goal=t["goal"].strip(),
            ground_truth=t.get("ground_truth") or [],
            checks=t.get("checks") or [],
            kind=t.get("kind", ""),
        )
        for t in inj_raw
    }
    return Suite(
        name=name,
        lang=lang,
        meta=meta,
        environment_text=environment_text,
        vectors=vectors,
        user_tasks=user_tasks,
        injection_tasks=injection_tasks,
        tools=SUITE_TOOLS[name],
    )


# --------------------------------------------------------------------------- checks


def _norm(text: Any) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    return re.sub(r"\s+", " ", text).strip()


_NUMBER = re.compile(r"\d[\d.,]*")


def numbers_in(text: str) -> list[float]:
    """Numbers in PT ("1.234,56", "189,90") or EN ("1,234.56", "189.90") notation."""
    found = []
    for raw in _NUMBER.findall(str(text)):
        raw = raw.rstrip(".,")
        candidates = set()
        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                candidates.add(raw.replace(".", "").replace(",", "."))
            else:
                candidates.add(raw.replace(",", ""))
        elif "," in raw:
            candidates.add(raw.replace(",", "."))  # decimal comma
            candidates.add(raw.replace(",", ""))  # thousands comma
        elif "." in raw:
            candidates.add(raw)  # decimal point
            candidates.add(raw.replace(".", ""))  # thousands point
        else:
            candidates.add(raw)
        for c in candidates:
            try:
                found.append(float(c))
            except ValueError:
                pass
    return found


def match_value(value: Any, matcher: Any) -> bool:
    """A matcher is a literal (case- and space-insensitive equality) or a dict:
    contains, contains_all, contains_any, not_contains, regex, number (with tol), in, equals."""
    if isinstance(matcher, dict):
        ok = True
        if "equals" in matcher:
            ok &= _norm(value) == _norm(matcher["equals"]) if not isinstance(matcher["equals"], (int, float)) else _num_eq(value, matcher["equals"], matcher.get("tol", 0.005))
        if "contains" in matcher:
            ok &= _norm(matcher["contains"]) in _norm(value)
        if "contains_all" in matcher:
            ok &= all(_norm(s) in _norm(value) for s in matcher["contains_all"])
        if "contains_any" in matcher:
            ok &= any(_norm(s) in _norm(value) for s in matcher["contains_any"])
        if "not_contains" in matcher:
            items = matcher["not_contains"]
            items = items if isinstance(items, list) else [items]
            ok &= not any(_norm(s) in _norm(value) for s in items)
        if "regex" in matcher:
            ok &= re.search(matcher["regex"], str(value), flags=re.IGNORECASE | re.DOTALL) is not None
        if "number" in matcher:
            tol = matcher.get("tol", 0.005)
            ok &= any(abs(n - float(matcher["number"])) <= tol for n in numbers_in(str(value)))
        if "in" in matcher:
            ok &= _norm(value) in {_norm(v) for v in matcher["in"]}
        return bool(ok)
    if isinstance(matcher, bool):
        return bool(value) is matcher
    if isinstance(matcher, (int, float)):
        return _num_eq(value, matcher)
    return _norm(value) == _norm(matcher)


def _num_eq(value: Any, expected: float, tol: float = 0.005) -> bool:
    try:
        return abs(float(value) - float(expected)) <= tol
    except (TypeError, ValueError):
        return any(abs(n - float(expected)) <= tol for n in numbers_in(str(value)))


def _lookup(env: Any, path: str) -> Any:
    node = env
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit():
            node = node[int(part)] if int(part) < len(node) else None
        else:
            return None
    return node


def _call_matches(call: dict[str, Any], tool: str, args: dict[str, Any] | None) -> bool:
    if call["tool"] != tool:
        return False
    for key, matcher in (args or {}).items():
        if key not in call["args"] or not match_value(call["args"][key], matcher):
            return False
    return True


def run_check(check: dict[str, Any], env: dict[str, Any], executed: list[dict[str, Any]], output: str) -> bool:
    kind = check["type"]
    if kind == "called":
        n = sum(_call_matches(c, check["tool"], check.get("args")) for c in executed)
        return n >= check.get("min", 1) and n <= check.get("max", 10**6)
    if kind == "not_called":
        return not any(_call_matches(c, check["tool"], check.get("args")) for c in executed)
    if kind == "state":
        value = _lookup(env, check["path"])
        if "absent" in check:
            return (value is None) is bool(check["absent"])
        return value is not None and match_value(value, check["match"])
    if kind == "state_any":
        # any item of a collection (dict of items or list) matches all field matchers
        coll = _lookup(env, check["path"]) or {}
        items = coll.values() if isinstance(coll, dict) else coll
        return any(
            all(match_value((item or {}).get(f), m) for f, m in check["where"].items()) for item in items
        )
    if kind == "output":
        return match_value(output, check["match"])
    if kind == "any_of":
        return any(run_check(c, env, executed, output) for c in check["checks"])
    raise ValueError(f"Unknown check type: {kind}")


def run_checks(checks: list[dict[str, Any]], env: dict[str, Any], executed: list[dict[str, Any]], output: str) -> bool:
    return all(run_check(c, env, executed, output) for c in checks)


# --------------------------------------------------------------------------- local execution


async def execute_locally(suite: Suite, env: dict[str, Any], calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Run tool calls against an environment outside Inspect (validation and tests)."""
    token = _LOCAL_ENV.set(env)
    executed, outputs = [], []
    try:
        for call in calls:
            spec = suite.tool(call["tool"])
            if spec is None:
                raise ValueError(f"Unknown tool {call['tool']} in suite {suite.name}")
            try:
                outputs.append(str(await spec.fn(**call.get("args", {}))))
                executed.append({"tool": call["tool"], "args": dict(call.get("args", {}))})
            except Exception as exc:  # noqa: BLE001
                outputs.append(f"Error: {exc}")
    finally:
        _LOCAL_ENV.reset(token)
    return executed, outputs


def deep_copy(env: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(env)
