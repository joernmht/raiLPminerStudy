"""The parser test cases: known structure, known verdicts, deterministic text."""

from __future__ import annotations

from genstudy import instrument
from genstudy.notation import notation


def _by_variant():
    return {c.case_id: c for c in instrument.cases()}


def test_case_inventory():
    cases = list(instrument.cases())
    per_fixture = len(instrument.MUTATIONS) + len(instrument.NEGATIVES)
    assert len(cases) == len(instrument.FIXTURES) * per_fixture
    assert len({c.case_id for c in cases}) == len(cases)


def test_base_fixtures_are_valid_milps():
    for f in instrument.FIXTURES:
        m = instrument.cases  # noqa: F841 - keep the import used for readability
        exp = _by_variant()[f"{f.key}.identity"].expected
        assert exp.contains_formulation and exp.complete_struct and exp.coherent, f.key
        assert exp.linear and exp.integral, f.key


def test_mutations_have_their_intended_effect():
    cases = _by_variant()
    for f in instrument.FIXTURES:
        assert cases[f"{f.key}.drop_objective"].expected.n_objectives == 0
        assert cases[f"{f.key}.drop_objective"].expected.complete_struct is False
        single = cases[f"{f.key}.single_use_variable"].expected
        assert single.complete_struct is False and single.coherent is True
        block = cases[f"{f.key}.disconnected_block"].expected
        assert block.coherent is False and block.complete_struct is True
        assert cases[f"{f.key}.nonlinear_objective"].expected.linear is False
        base = cases[f"{f.key}.identity"].expected
        words = cases[f"{f.key}.words_constraint"].expected
        assert words.n_constraints == base.n_constraints - 1
        for neg in instrument.NEGATIVES:
            e = cases[f"{f.key}.{neg}"].expected
            assert e.contains_formulation is False and e.n_variables == 0


def test_rendering_is_deterministic_and_negatives_carry_no_formulation():
    a = [c.text for c in instrument.cases()]
    b = [c.text for c in instrument.cases()]
    assert a == b
    for c in instrument.cases():
        if c.variant in instrument.NEGATIVES:
            assert "$" not in c.text and not notation(c.text).passed, c.case_id
        else:
            assert "$$" in c.text, c.case_id


def test_words_constraint_is_in_the_text_but_not_in_the_truth():
    cases = _by_variant()
    f = instrument.FIXTURES[0]
    case = cases[f"{f.key}.words_constraint"]
    assert f.constraints[-1].words in case.text
    assert f.constraints[-1].latex not in case.text


def test_score_compares_every_verdict():
    cases = _by_variant()
    exp = cases["single_track_order.identity"].expected
    assert all(instrument.score(exp, exp).values())
    wrong = cases["single_track_order.prose"].expected
    s = instrument.score(exp, wrong)
    assert s["contains_formulation"] is False and s["accepted"] is False
    assert instrument.score(exp, None) == {"parsed": False}
