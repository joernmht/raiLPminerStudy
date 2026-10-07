"""The names a model's graph carries, the input of the domain analysis.

The parser names every decision variable and every equation of an answer (the labels
of the graph's nodes). ``scripts/domain_vectors.py`` turns these names into TF-IDF
vectors to measure how close a generated model is to the input paper's own formulation
(domain relevance) and how far the models of one setting lie apart (diversity),
docs/adr/0006. Hand-made keyword categories were tried first and dropped: the vectors
need no patterns tuned by hand.
"""

from __future__ import annotations

import re

from genstudy.graphing import Model

#: Equation labels the annotators put in front of reference names: "(2a) ...", "(13) line 4: ...".
_LABEL = re.compile(r"^\(\w+\)\s*(line \d+:)?\s*")


def names(model: Model) -> list[str]:
    """Names of the variables, objective functions and constraints, without equation labels."""
    return [_LABEL.sub("", n) for n in (
        [v.Name for v in model.variablesInModel]
        + [e.Name for e in (*model.objective_functions, *model.constraints)]
    )]  # fmt: skip
