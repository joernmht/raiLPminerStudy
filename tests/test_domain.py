"""The names the domain analysis reads."""

from __future__ import annotations

from genstudy.domain import names
from genstudy.graphing import Constraint, Model, ObjectiveFunction, Variable


def test_names_are_the_node_labels_without_equation_numbers():
    v = Variable(
        Number=1, Abbreviation="x", Name="route choice", Description="prose", Domain="binary"
    )
    e = dict(Number=1, equation="", description="prose", VariablesIncluded=[1], Linear=True)
    m = Model(ContainsFormulation=True, variablesInModel=[v],
              objective_functions=[ObjectiveFunction(Name="(1) total delay", **e)],
              constraints=[Constraint(Name="(13) line 2: one route per train", **e)])  # fmt: skip
    assert names(m) == ["route choice", "total delay", "one route per train"]
