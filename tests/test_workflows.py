"""The workflows send what the paper reports, and the trace says what happened.

The first test is the regression test for the 2025 harness: every request a
workflow sends carries the system prompt, the temperature and the seed.
"""

from __future__ import annotations

import json

from conftest import ScriptedClient, result

from genstudy import prompts
from genstudy.config import ModelSpec
from genstudy.llm import ToolCall
from genstudy.workflows import run_workflow

MODEL = ModelSpec("a", "org/model-a", "", "", "", max_tokens=123)


def _tool(name: str, **args) -> ToolCall:
    return ToolCall(id=f"c-{name}", name=name, arguments=json.dumps(args))


def test_every_request_carries_system_prompt_temperature_and_seed(pacing):
    def answer(body):
        if (
            body.get("tool_choice", "x") != "auto"
            and body.get("tools")
            and body["tool_choice"] != "none"
        ):
            return result(tool_calls=(_tool("or_operator", description="d"),), body=body)
        return result("final model", body=body)

    for wf in ("ZS", "CFC", "OE", "PS"):
        client = ScriptedClient(answer)
        run_workflow(
            wf,
            client=client,
            model=MODEL,
            temperature=0.6,
            seed=11,
            paper_text="paper",
            pacing=pacing,
        )
        for body in client.bodies:
            assert body["temperature"] == 0.6
            assert isinstance(body["seed"], int)
            assert body["max_tokens"] == 123
            assert body["model"] == "org/model-a"
        orchestrator = client.bodies[0]
        assert orchestrator["messages"][0] == {
            "role": "system",
            "content": prompts.system_prompt(wf),
        }
        assert orchestrator["messages"][1]["content"].startswith(prompts.GENERAL_CALL)
        assert orchestrator["messages"][1]["content"].endswith("paper")


def test_zero_shot_is_one_request(pacing):
    client = ScriptedClient(lambda body: result("min x s.t. x >= 1", body=body))
    trace = run_workflow(
        "ZS", client=client, model=MODEL, temperature=0.2, seed=1, paper_text="p", pacing=pacing
    )
    assert len(client.bodies) == 1
    assert "tools" not in client.bodies[0]
    assert trace.final_answer == "min x s.t. x >= 1"
    assert trace.notes == []


def test_first_orchestrator_turn_forces_the_tool(pacing):
    def answer(body):
        if body.get("tools") and isinstance(body["tool_choice"], dict):
            return result(tool_calls=(_tool("or_coder", description="model it"),), body=body)
        if body.get("tools"):
            return result("equations only", body=body)
        return result("import pyomo  # code", body=body)

    client = ScriptedClient(answer)
    trace = run_workflow(
        "CFC", client=client, model=MODEL, temperature=1.0, seed=3, paper_text="p", pacing=pacing
    )
    first = client.bodies[0]
    assert first["tool_choice"] == {"type": "function", "function": {"name": "or_coder"}}
    assert first["tools"] == [prompts.TOOLS["or_coder"]]
    coder = client.bodies[1]
    assert "tools" not in coder
    assert coder["messages"] == [
        {"role": "user", "content": prompts.tool_message(prompts.CODER_CALL, "model it")}
    ]
    assert client.bodies[2]["tool_choice"] == "auto"
    assert client.bodies[2]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "c-or_coder",
        "content": "import pyomo  # code",
    }
    assert trace.final_answer == "equations only"
    assert (trace.tool_calls_requested, trace.tool_calls_executed, trace.rounds) == (1, 1, 1)


def test_ignored_forced_call_is_noted(pacing):
    client = ScriptedClient(lambda body: result("I answer directly", body=body))
    trace = run_workflow(
        "OE", client=client, model=MODEL, temperature=0.2, seed=1, paper_text="p", pacing=pacing
    )
    assert trace.notes == ["forced first tool call not honoured"]
    assert trace.tool_calls_executed == 0


def test_factory_count_is_clamped_and_instances_get_distinct_seeds(pacing):
    def answer(body):
        if body.get("tools") and isinstance(body["tool_choice"], dict):
            return result(tool_calls=(_tool("or_factory", count=9, description="d"),), body=body)
        if body.get("tools"):
            return result("Model 2 is best: min ...", body=body)
        return result(f"model with seed {body['seed']}", body=body)

    client = ScriptedClient(answer)
    trace = run_workflow(
        "PS", client=client, model=MODEL, temperature=1.0, seed=5, paper_text="p", pacing=pacing
    )
    factory = [b for b in client.bodies if "tools" not in b]
    assert len(factory) == pacing.ps_count_max
    assert len({b["seed"] for b in factory}) == len(factory)
    assert all(b["messages"][0]["content"] == prompts.FACTORY_SYSTEM for b in factory)
    assert "or_factory count 9 clamped to 5" in trace.notes
    tool_reply = client.bodies[-1]["messages"][-1]["content"]
    assert tool_reply.startswith("Model 1:") and "Model 5:" in tool_reply


def test_round_limit_switches_tools_off(pacing):
    def answer(body):
        if body.get("tools") and body["tool_choice"] != "none":
            return result(tool_calls=(_tool("or_operator", description="again"),), body=body)
        return result("final", body=body)

    client = ScriptedClient(answer)
    trace = run_workflow(
        "OE", client=client, model=MODEL, temperature=0.2, seed=1, paper_text="p", pacing=pacing
    )
    choices = [b["tool_choice"] for b in client.bodies if "tools" in b]
    assert choices[-1] == "none"
    assert trace.rounds == pacing.max_tool_rounds
    assert f"tool round limit ({pacing.max_tool_rounds}) reached" in trace.notes
    assert trace.final_answer == "final"


def test_bad_tool_arguments_are_answered_not_executed(pacing):
    def answer(body):
        if body.get("tools") and isinstance(body["tool_choice"], dict):
            return result(tool_calls=(ToolCall("c1", "or_operator", "{not json"),), body=body)
        return result("final", body=body)

    client = ScriptedClient(answer)
    trace = run_workflow(
        "OE", client=client, model=MODEL, temperature=0.2, seed=1, paper_text="p", pacing=pacing
    )
    assert trace.tool_calls_requested == 1
    assert trace.tool_calls_executed == 0
    assert "unparseable arguments for or_operator" in trace.notes
    assert client.bodies[1]["messages"][-1]["content"].startswith("Error:")
