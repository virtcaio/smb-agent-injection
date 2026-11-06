"""A scripted, fully gullible agent for testing the harness without API calls.

It replays the user task's ground truth and, if any tool result it has seen contains the attack,
also replays the injection's ground truth, then answers with the task's sample output. With
`none` it should score utility 1 and attack success 1 on attacked samples; the defenses should
lower attack success without touching utility (except where the filter withholds content)."""

from __future__ import annotations

from typing import Any

from inspect_ai.model import ChatMessage, GenerateConfig, ModelAPI, ModelOutput, modelapi
from inspect_ai.tool import ToolChoice, ToolInfo

from smb_injection.agent import cached_suite
from smb_injection.suites import SUITES

MARKERS = ("<INFORMATION>", "<INFORMAÇÃO>")


def _find_task(prompt: str):
    for name in SUITES:
        for lang in ("pt", "en"):
            try:
                suite = cached_suite(name, lang)
            except FileNotFoundError:
                continue
            for task in suite.user_tasks.values():
                if task.prompt == prompt:
                    return suite, task
    raise LookupError("prompt not found")


@modelapi(name="scripted")
def scripted():
    return ScriptedAPI


class ScriptedAPI(ModelAPI):
    def __init__(self, model_name: str, base_url: str | None = None, api_key: str | None = None, config: GenerateConfig = GenerateConfig(), **kwargs: Any) -> None:
        super().__init__(model_name, base_url, api_key, [], config)

    async def generate(self, input: list[ChatMessage], tools: list[ToolInfo], tool_choice: ToolChoice, config: GenerateConfig) -> ModelOutput:
        prompt = next(m.text for m in input if m.role == "user")
        suite, task = _find_task(prompt)
        seen = " ".join(" ".join(m.text.split()) for m in input if m.role == "tool")
        plan = list(task.ground_truth)
        if any(marker in seen for marker in MARKERS):
            injection = next((i for i in suite.injection_tasks.values() if " ".join(i.goal.split()) in seen), None)
            if injection:
                plan = plan + list(injection.ground_truth)
        step = sum(1 for m in input if m.role == "assistant")
        if step < len(plan):
            call = plan[step]
            return ModelOutput.for_tool_call(model="scripted", tool_name=call["tool"], tool_arguments=dict(call.get("args", {})))
        return ModelOutput.from_content(model="scripted", content=task.ground_truth_output or "Done.")
