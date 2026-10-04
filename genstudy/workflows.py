"""The four workflows of Paper 0 as explicit code paths.

* **ZS** (Zero-Shot): one request, general system prompt, the paper's input.
* **CFC** (Code-First-Chain), **OE** (Operator-Expert), **PS**
  (Parallelization-Selection): an orchestrator with the workflow's system prompt
  and one tool (``or_coder`` / ``or_operator`` / ``or_factory``). The tool is
  executed here, by a sub-agent request with the sub-agent's own prompts.

The orchestrator keeps its autonomy (what to write to the tool, whether to call
it again, how many factory instances to start) with one exception: its first
turn is a *forced* call of its tool. In 2025 the orchestrators were free not to
call their tools and o4-mini almost never did (2/0/0 % of CFC/OE/PS runs), so the
"workflow" factor measured a tool offered, not a workflow run (ADR-0001). Every
deviation from the plain path (a clamped factory count, a round limit, an
unparseable tool argument) is written into :attr:`RunTrace.notes`.

Each request gets its own seed, derived from the run seed and the request's
position, so independent factory instances are independent samples and a
replayed run sends the same seeds again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from genstudy import prompts
from genstudy.config import ModelSpec, PacingSpec
from genstudy.llm import CallResult, ChatClient, ToolCall


@dataclass
class RunTrace:
    """Everything a workflow did, in order; serialised into the run record."""

    workflow: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_requested: int = 0
    tool_calls_executed: int = 0
    subcalls: int = 0
    rounds: int = 0
    final_answer: str = ""
    final_finish_reason: str | None = None
    notes: list[str] = field(default_factory=list)


class _Run:
    """One workflow execution: the client, the model, the seed sequence and the trace."""

    def __init__(
        self,
        workflow: str,
        client: ChatClient,
        model: ModelSpec,
        temperature: float,
        seed: int,
        pacing: PacingSpec,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.pacing = pacing
        self.trace = RunTrace(workflow=workflow)
        self._n = 0

    def _body(self, messages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model.served_id,
            "messages": messages,
            "temperature": self.temperature,
            "seed": (self.seed + 1009 * self._n) % 2**31,
            "max_tokens": self.model.max_tokens,
            **dict(self.model.extra),
            **extra,
        }
        self._n += 1
        return body

    def call(self, agent: str, messages: list[dict[str, Any]], **extra: Any) -> CallResult:
        result = self.client.complete(self._body(messages, **extra), describe=agent)
        record = result.to_record()
        record["agent"] = agent
        self.trace.calls.append(record)
        return result


def run_workflow(
    workflow: str,
    *,
    client: ChatClient,
    model: ModelSpec,
    temperature: float,
    seed: int,
    paper_text: str,
    pacing: PacingSpec,
) -> RunTrace:
    """Run one workflow end to end and return its trace."""
    run = _Run(workflow, client, model, temperature, seed, pacing)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompts.system_prompt(workflow)},
        {"role": "user", "content": prompts.opening_message(paper_text)},
    ]
    if workflow == "ZS":
        result = run.call("single", messages)
        _finish(run.trace, result)
        return run.trace
    if workflow not in prompts.WORKFLOW_TOOL:
        raise ValueError(f"unknown workflow {workflow!r}")
    _orchestrate(run, messages, prompts.WORKFLOW_TOOL[workflow])
    return run.trace


def _finish(trace: RunTrace, result: CallResult) -> None:
    trace.final_answer = result.content.strip()
    trace.final_finish_reason = result.finish_reason
    if not trace.final_answer:
        trace.notes.append("final answer is empty")


def _orchestrate(run: _Run, messages: list[dict[str, Any]], tool_name: str) -> None:
    tools = [prompts.TOOLS[tool_name]]
    trace = run.trace
    while True:
        if trace.rounds == 0:
            choice: Any = {"type": "function", "function": {"name": tool_name}}
        elif trace.rounds >= run.pacing.max_tool_rounds:
            choice = "none"
        else:
            choice = "auto"
        result = run.call("orchestrator", messages, tools=tools, tool_choice=choice)

        if not result.tool_calls or choice == "none":
            if trace.rounds == 0:
                trace.notes.append("forced first tool call not honoured")
            if result.tool_calls:
                trace.notes.append("tool calls returned after the round limit were ignored")
            if choice == "none":
                trace.notes.append(f"tool round limit ({run.pacing.max_tool_rounds}) reached")
            _finish(trace, result)
            return

        trace.rounds += 1
        messages.append(
            {
                "role": "assistant",
                "content": result.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in result.tool_calls
                ],
            }
        )
        for tc in result.tool_calls:
            trace.tool_calls_requested += 1
            output = _execute_tool(run, tc, tool_name)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})


def _execute_tool(run: _Run, tc: ToolCall, tool_name: str) -> str:
    trace = run.trace
    if tc.name != tool_name:
        trace.notes.append(f"call of unknown tool {tc.name!r} answered with an error")
        return f"Error: there is no tool named {tc.name!r}. The available tool is {tool_name}."
    try:
        args = json.loads(tc.arguments) if tc.arguments.strip() else {}
        if not isinstance(args, dict):
            raise ValueError("arguments are not an object")
    except ValueError:
        trace.notes.append(f"unparseable arguments for {tc.name}")
        return "Error: the tool arguments were not valid JSON."
    description = str(args.get("description", "")).strip()
    if not description:
        trace.notes.append(f"{tc.name} called without a description")
        return "Error: the tool needs a non-empty description."

    if tool_name == "or_factory":
        return _factory(run, args, description)

    if not _reserve_subcalls(run, 1):
        return "Error: the sub-agent call limit of this run is reached."
    if tool_name == "or_coder":
        sub = [{"role": "user", "content": prompts.tool_message(prompts.CODER_CALL, description)}]
        agent = "coder"
    else:
        sub = [
            {"role": "system", "content": prompts.OPERATOR_SYSTEM},
            {"role": "user", "content": prompts.tool_message(prompts.OPERATOR_CALL, description)},
        ]
        agent = "operator"
    result = run.call(agent, sub)
    trace.tool_calls_executed += 1
    if not result.content.strip():
        trace.notes.append(f"{agent} returned empty content")
    return result.content.strip()


def _factory(run: _Run, args: dict[str, Any], description: str) -> str:
    trace = run.trace
    lo, hi = run.pacing.ps_count_min, run.pacing.ps_count_max
    raw = args.get("count")
    try:
        requested = int(raw)
    except (TypeError, ValueError):
        requested = lo
        trace.notes.append(f"or_factory count {raw!r} is not an integer; used {lo}")
    count = min(max(requested, lo), hi)
    if count != requested:
        trace.notes.append(f"or_factory count {requested} clamped to {count}")
    if not _reserve_subcalls(run, count):
        return "Error: the sub-agent call limit of this run is reached."
    models = []
    for i in range(count):
        sub = [
            {"role": "system", "content": prompts.FACTORY_SYSTEM},
            {"role": "user", "content": prompts.tool_message(prompts.FACTORY_CALL, description)},
        ]
        result = run.call(f"factory[{i + 1}/{count}]", sub)
        if not result.content.strip():
            trace.notes.append(f"factory instance {i + 1} returned empty content")
        models.append(f"Model {i + 1}:\n{result.content.strip()}")
    trace.tool_calls_executed += 1
    return "\n\n".join(models)


def _reserve_subcalls(run: _Run, n: int) -> bool:
    if run.trace.subcalls + n > run.pacing.max_subcalls:
        run.trace.notes.append(f"sub-call limit ({run.pacing.max_subcalls}) reached")
        return False
    run.trace.subcalls += n
    return True
