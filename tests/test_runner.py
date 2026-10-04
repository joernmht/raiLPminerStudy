"""The design, the order, the records, and the failure policy."""

from __future__ import annotations

import pytest
from conftest import ScriptedClient, result

from genstudy.config import load_study
from genstudy.llm import EndpointError
from genstudy.runner import execute, plan, run_seed, schedule, store_for


def test_plan_is_the_full_factorial_with_named_cells(study_path):
    spec = load_study(study_path)
    cells = plan(spec)
    assert len(cells) == 1 * 1 * 2 * 2 * 2
    assert cells[0].run_id == "exp1.P1.a.PS.t02.r01"
    assert len({c.run_id for c in cells}) == len(cells)


def test_schedule_and_seeds_are_reproducible(study_path):
    spec = load_study(study_path)
    cells = plan(spec)
    assert schedule(spec, cells, "a") == schedule(spec, list(reversed(cells)), "a")
    assert run_seed(spec, cells[0].run_id) == run_seed(spec, cells[0].run_id)
    assert run_seed(spec, cells[0].run_id) != run_seed(spec, cells[1].run_id)


def _answer(body):
    if body.get("tools") and isinstance(body["tool_choice"], dict):
        from genstudy.llm import ToolCall

        call = ToolCall("c", "or_factory", '{"count": 2, "description": "d"}')
        return result(tool_calls=(call,), body=body)
    return result("min x s.t. x >= 1", body=body)


def test_execute_writes_records_and_resumes(study_path):
    spec = load_study(study_path)
    client = ScriptedClient(_answer)
    first = execute(spec, model="a", client=client, limit=3, log=lambda m: None)
    assert first.written == 3
    assert first.stopped == "limit of 3 runs reached"
    second = execute(spec, model="a", client=client, log=lambda m: None)
    assert second.already_done == 3
    assert second.written == 5
    records = list(store_for(spec, "a").records())
    assert len(records) == 8
    rec = records[0]
    assert rec["status"] == "ok"
    assert rec["spec_sha256"] == spec.sha256
    assert rec["calls"][0]["request"]["messages"][0]["role"] == "system"
    assert rec["prompts"]["version"]


def test_transient_failure_stops_without_a_record(study_path):
    spec = load_study(study_path)

    def answer(body):
        raise EndpointError("HTTP 503", status=503, transient=True)

    summary = execute(spec, model="a", client=ScriptedClient(answer), log=lambda m: None)
    assert summary.written == 0
    assert summary.stopped.startswith("transient endpoint failure")
    assert list(store_for(spec, "a").records()) == []


def test_three_refusals_in_a_row_stop_the_block(study_path):
    spec = load_study(study_path)

    def answer(body):
        raise EndpointError("HTTP 400: context too long", status=400, transient=False)

    summary = execute(spec, model="a", client=ScriptedClient(answer), log=lambda m: None)
    assert summary.written == 3
    assert summary.request_errors == 3
    assert summary.stopped == "three refused requests in a row"
    assert {r["status"] for r in store_for(spec, "a").records()} == {"request_error"}


def test_unknown_model_is_an_error(study_path):
    spec = load_study(study_path)
    with pytest.raises(KeyError):
        execute(spec, model="nope", client=ScriptedClient(_answer), log=lambda m: None)
