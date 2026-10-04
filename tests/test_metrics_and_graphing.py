"""Metrics on hand-built structures, the parser schema, and the notation gate."""

from __future__ import annotations

import json

import pytest

from genstudy.config import GrapherSpec
from genstudy.graphing import (
    MODEL_SCHEMA,
    Constraint,
    Model,
    ObjectiveFunction,
    Variable,
    grapher_body,
    parse_reply,
)
from genstudy.metrics import graph_metrics
from genstudy.notation import notation


def _var(n, domain="continuous"):
    return Variable(Number=n, Abbreviation=f"v{n}", Name="", Description="", Domain=domain)


def _eq(cls, n, refs, linear=True):
    return cls(
        Name="", Number=n, equation="", description="", VariablesIncluded=refs, Linear=linear
    )


def _model(variables, objectives, constraints, contains=True):
    return Model(
        ContainsFormulation=contains,
        variablesInModel=variables,
        objective_functions=objectives,
        constraints=constraints,
    )


def test_complete_coherent_model():
    m = _model(
        [_var(1), _var(2, "binary")],
        [_eq(ObjectiveFunction, 0, [1])],
        [_eq(Constraint, 1, [1, 2]), _eq(Constraint, 2, [2])],
    )
    g = graph_metrics(m)
    assert (g.complete_struct, g.coherent, g.linear, g.integral) == (True, True, True, True)
    assert (g.n_objectives, g.n_variables, g.n_constraints) == (1, 2, 2)
    assert g.minimal_size == 4
    assert g.cv_ratio == 1.0
    assert g.diameter == 4


def test_variable_in_one_equation_is_incomplete():
    m = _model([_var(1), _var(2)], [_eq(ObjectiveFunction, 0, [1])], [_eq(Constraint, 1, [1, 2])])
    g = graph_metrics(m)
    assert g.complete_struct is False
    assert g.low_degree_variables == (2,)
    assert g.coherent is True


def test_missing_objective_is_incomplete_and_observable():
    m = _model([_var(1)], [], [_eq(Constraint, 1, [1]), _eq(Constraint, 2, [1])])
    g = graph_metrics(m)
    assert g.n_objectives == 0
    assert g.complete_struct is False


def test_disconnected_block_is_incoherent_without_a_diameter():
    m = _model(
        [_var(1), _var(2)],
        [_eq(ObjectiveFunction, 0, [1])],
        [_eq(Constraint, 1, [1]), _eq(Constraint, 2, [2]), _eq(Constraint, 3, [2])],
    )
    g = graph_metrics(m)
    assert g.complete_struct is True
    assert g.coherent is False
    assert g.diameter is None


def test_nonlinear_equation_and_dangling_reference():
    m = _model(
        [_var(1)],
        [_eq(ObjectiveFunction, 0, [1, 9], linear=False)],
        [_eq(Constraint, 1, [1])],
    )
    g = graph_metrics(m)
    assert g.linear is False
    assert g.dangling_references == 1
    assert g.integral is False


def test_empty_model():
    g = graph_metrics(_model([], [], [], contains=False))
    assert (g.contains_formulation, g.complete_struct, g.coherent) == (False, False, False)
    assert g.minimal_size == 1


def test_schema_has_no_refs_and_requires_the_exit_field():
    text = json.dumps(MODEL_SCHEMA)
    assert "$ref" not in text and "$defs" not in text
    assert "ContainsFormulation" in MODEL_SCHEMA["required"]


def test_parse_reply_accepts_valid_and_fenced_json_and_rejects_the_rest():
    m = _model([_var(1)], [_eq(ObjectiveFunction, 0, [1])], [_eq(Constraint, 1, [1])])
    raw = m.model_dump_json()
    assert parse_reply(raw) == m
    assert parse_reply("```json\n" + raw + "\n```") == m
    with pytest.raises(ValueError):
        parse_reply('{"ContainsFormulation": true}')


def test_grapher_body_is_deterministic_and_schema_constrained():
    g = GrapherSpec("org/grapher", temperature=0.0, seed=7, max_tokens=99)
    body = grapher_body(g, "  answer  ")
    assert body["temperature"] == 0.0 and body["seed"] == 7
    assert body["response_format"]["json_schema"]["schema"] == MODEL_SCHEMA
    assert body["messages"][1]["content"].endswith("answer")
    assert grapher_body(g, "x", seed_offset=1)["seed"] == 8


@pytest.mark.parametrize(
    ("text", "groups"),
    [
        (
            r"$$\min \sum_i x_i$$ s.t. $x_i \le 1 \;\forall i$, $y \ge 0$",
            ("le", "ge", "sum", "forall", "st"),
        ),
        (r"$t_j \ge t_i + h$ and $x \leq 1$ for all trains", ("le", "ge", "forall")),
        ("x <= 5, y >= 2, subject to", ("le", "ge", "st")),
        ("The model decides the order of trains and minimizes delay.", ()),
    ],
)
def test_notation_groups(text, groups):
    assert notation(text).groups == groups


def test_notation_threshold_is_more_than_half():
    assert notation(r"$x \le 1$, $y \ge 0$, $\sum_i z_i$").passed is True
    assert notation(r"$x \le 1$, $y \ge 0$").passed is False
    assert notation(r"\left| x \right|").passed is False


def test_every_text_field_is_length_capped():
    """Runaway strings were the grapher's failure mode; the decoder must be able to stop."""

    def strings(node):
        if isinstance(node, dict):
            if node.get("type") == "string" and "enum" not in node:
                yield node
            for v in node.values():
                yield from strings(v)
        elif isinstance(node, list):
            for v in node:
                yield from strings(v)

    found = list(strings(MODEL_SCHEMA))
    assert found and all("maxLength" in s for s in found)


def test_grapher_modes():
    schema_mode = grapher_body(GrapherSpec("g", whitespace_pattern=r"[ \n]?"), "x")
    assert schema_mode["guided_whitespace_pattern"] == r"[ \n]?"
    prompt_mode = grapher_body(GrapherSpec("g", mode="prompt"), "THE ANSWER")
    content = prompt_mode["messages"][1]["content"]
    assert "response_format" not in prompt_mode
    assert content.index(json.dumps(MODEL_SCHEMA)) < content.index("THE ANSWER")
    assert content.rstrip().endswith("without code fences.")
    with pytest.raises(ValueError):
        grapher_body(GrapherSpec("g", mode="nope"), "x")


def test_key_repair_maps_case_and_drops_schema_keywords():
    reply = {
        "additionalProperties": False,
        "ContainsFormulation": True,
        "linear": True,
        "objective_functions": [],
        "constraints": [
            {"name": "c", "number": 1, "equation": "x >= 1", "description": "",
             "variablesIncluded": [1], "linear": True}
        ],
        "variablesInModel": [
            {"Number": 1, "abbreviation": "x", "Name": "x", "Description": "", "domain": "binary"}
        ],
    }  # fmt: skip
    repairs: list[str] = []
    m = parse_reply(json.dumps(reply), repairs)
    assert m.constraints[0].VariablesIncluded == [1] and m.constraints[0].Linear is True
    assert m.variablesInModel[0].Domain == "binary"
    assert "dropped model.additionalProperties" in repairs
    assert "renamed equation.variablesIncluded" in repairs
    with pytest.raises(ValueError):
        parse_reply("not json")


def test_narrow_repairs_and_schema_echo():
    m = _model([_var(1)], [_eq(ObjectiveFunction, 0, [1])], [_eq(Constraint, 1, [1])])
    raw = m.model_dump_json()
    repairs: list[str] = []
    assert parse_reply(raw + "\nI hope this helps.", repairs) == m
    assert repairs == ["ignored text after the JSON object"]
    no_key = raw.replace('"equation":"",', '"x >= 1",').replace('"equation": "",', '"x >= 1",')
    no_key = json.dumps(json.loads(raw)).replace('"equation": "", ', '"x >= 1", ')
    repairs = []
    fixed = parse_reply(no_key, repairs)
    assert fixed.constraints[0].equation == "x >= 1"
    assert "inserted missing equation keys" in repairs
    with pytest.raises(ValueError, match="echoes the schema"):
        parse_reply(json.dumps(MODEL_SCHEMA))


def test_raw_latex_backslashes_are_escaped_only_on_failure():
    m = _model([_var(1)], [_eq(ObjectiveFunction, 0, [1])], [_eq(Constraint, 1, [1])])
    good = m.model_dump_json().replace('"equation":""', '"equation":"x \\\\le 1"', 1)
    repairs: list[str] = []
    assert parse_reply(good, repairs).objective_functions[0].equation == "x \\le 1"
    assert repairs == []
    raw_latex = good.replace("\\\\le", "\\le")
    repairs = []
    assert parse_reply(raw_latex, repairs).objective_functions[0].equation == "x \\le 1"
    assert repairs == ["escaped stray backslashes"]
