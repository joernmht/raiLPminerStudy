"""Structural metrics of one parsed answer (Paper 0, Sections 3.4.1 and 3.4.2).

The graph has one node per objective function, constraint and decision variable
(indexed families count once) and an edge between a variable and every equation
that contains it.

**Completeness** (corrected definition). An answer is structurally complete
when it has exactly one objective function, at least one variable and one
constraint, and every variable appears in at least two equations (objective
function or constraints). The degree condition implements Paper 0's Rules 2
and 4 jointly: a variable in the objective must also appear in a constraint,
and a variable outside the objective in at least two constraints. Rule 3 (an
equation contains a variable) is enforced through coherence, because an
equation without variables is an isolated node. This is what the 2025 code
computed; the 2025 manuscript's Equation (3) stated a different condition.

**Coherence**: the graph is non-empty and connected.

**Linearity** and **integrality** are new: every equation is linear, and at
least one variable is binary or integer (an LP is not a MILP).

**Complexity** (unchanged): minimal size ``max(nV,1)*max(nC,1)``, the
constraint-variable ratio ``nC/nV`` and the graph diameter (the longest
shortest path), defined only for coherent graphs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from genstudy.graphing import Model

Node = tuple[str, int]


@dataclass(frozen=True)
class GraphMetrics:
    contains_formulation: bool
    n_objectives: int
    n_variables: int
    n_constraints: int
    n_edges: int
    dangling_references: int
    low_degree_variables: tuple[int, ...]
    complete_struct: bool
    coherent: bool
    linear: bool
    integral: bool
    minimal_size: int
    cv_ratio: float | None
    diameter: int | None


def build_graph(model: Model) -> tuple[set[Node], dict[Node, set[Node]], int]:
    """Nodes, adjacency and the number of references to undeclared variables."""
    variables = {v.Number for v in model.variablesInModel}
    nodes: set[Node] = {("v", n) for n in variables}
    adj: dict[Node, set[Node]] = {n: set() for n in nodes}
    dangling = 0
    equations = [("o", e) for e in model.objective_functions] + [
        ("c", e) for e in model.constraints
    ]
    for i, (kind, eq) in enumerate(equations):
        node: Node = (kind, i)
        nodes.add(node)
        adj.setdefault(node, set())
        for ref in set(eq.VariablesIncluded):
            if ref not in variables:
                dangling += 1
                continue
            adj[node].add(("v", ref))
            adj[("v", ref)].add(node)
    return nodes, adj, dangling


def _component(start: Node, adj: dict[Node, set[Node]]) -> dict[Node, int]:
    dist = {start: 0}
    queue = deque([start])
    while queue:
        u = queue.popleft()
        for w in adj[u]:
            if w not in dist:
                dist[w] = dist[u] + 1
                queue.append(w)
    return dist


def graph_metrics(model: Model) -> GraphMetrics:
    nodes, adj, dangling = build_graph(model)
    n_obj = len(model.objective_functions)
    n_var = len(model.variablesInModel)
    n_con = len(model.constraints)
    low = tuple(sorted(n for kind, n in nodes if kind == "v" and len(adj[(kind, n)]) < 2))
    complete = n_obj == 1 and n_var > 0 and n_con > 0 and not low

    coherent = False
    diameter = None
    if nodes:
        first = next(iter(sorted(nodes)))
        coherent = len(_component(first, adj)) == len(nodes)
        if coherent:
            diameter = max(max(_component(n, adj).values()) for n in nodes)

    equations = [*model.objective_functions, *model.constraints]
    return GraphMetrics(
        contains_formulation=model.ContainsFormulation,
        n_objectives=n_obj,
        n_variables=n_var,
        n_constraints=n_con,
        n_edges=sum(len(s) for s in adj.values()) // 2,
        dangling_references=dangling,
        low_degree_variables=low,
        complete_struct=complete,
        coherent=coherent,
        linear=all(e.Linear for e in equations) if equations else False,
        integral=any(v.Domain in ("binary", "integer") for v in model.variablesInModel),
        minimal_size=max(n_var, 1) * max(n_con, 1),
        cv_ratio=(n_con / n_var) if n_var else None,
        diameter=diameter,
    )
