"""Classification of answers and the result macros, on synthetic records."""

from __future__ import annotations

from genstudy.analyze import acceptance_table, classify, macros, rows, share


def _metrics(complete=True, coherent=True, contains=True):
    return {
        "contains_formulation": contains,
        "complete_struct": complete,
        "coherent": coherent,
        "linear": True,
        "integral": True,
        "minimal_size": 6,
        "cv_ratio": 1.5,
        "diameter": 4,
    }


def test_classify_covers_every_outcome():
    assert classify(None) == "pending"
    assert classify({"gate_passed": False}) == "no_formulation"
    assert classify({"gate_passed": True, "metrics": None}) == "unparsed"
    assert classify({"gate_passed": True, "metrics": _metrics(contains=False)}) == "no_formulation"
    assert classify({"gate_passed": True, "metrics": _metrics()}) == "accepted"
    assert classify({"gate_passed": True, "metrics": _metrics(complete=False)}) == "incomplete"
    assert classify({"gate_passed": True, "metrics": _metrics(coherent=False)}) == "incoherent"
    both = _metrics(complete=False, coherent=False)
    assert classify({"gate_passed": True, "metrics": both}) == "both"


def _record(run_id, workflow, status="ok"):
    return {
        "run_id": run_id,
        "experiment": "exp1",
        "paper": "P1",
        "model": "a",
        "workflow": workflow,
        "temperature": 0.2,
        "status": status,
        "calls": [{"response": {"usage": {"prompt_tokens": 10, "completion_tokens": 4}}}],
        "wall_s": 2.0,
        "rounds": 1,
    }


def test_rows_tables_and_macros():
    records = [
        _record("r1", "ZS"),
        _record("r2", "ZS"),
        _record("r3", "PS"),
        _record("r4", "PS", status="request_error"),
    ]
    graphs = {
        "r1": {"gate_passed": True, "metrics": _metrics()},
        "r2": {"gate_passed": False},
        "r3": {"gate_passed": True, "metrics": _metrics(coherent=False)},
    }
    data = rows(records, graphs)
    assert [r.outcome for r in data] == [
        "accepted",
        "no_formulation",
        "incoherent",
        "request_error",
    ]
    assert data[0].prompt_tokens == 10 and data[0].requests == 1
    table = acceptance_table(data, ("workflow",))
    assert table[("ZS",)] == {"accepted": 1, "no_formulation": 1}
    assert share(table[("PS",)], "accepted") == 0.0
    m = macros(data)
    assert m["resAcceptZS"] == "50\\,\\%"
    assert m["resAcceptOverall"] == "33\\,\\%"
    assert m["resRunsGraphed"] == "3"


def test_macros_print_tbd_without_data():
    assert macros([])["resAcceptOverall"] == r"\TBD"
