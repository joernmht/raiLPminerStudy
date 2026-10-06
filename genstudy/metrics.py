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

**The coherent core** (decided after the runs, docs/adr/0005): the connected
component of the objective function. A block that shares no variable with the
objective cannot change its optimum (it can only make the whole model
infeasible), so the core is what the answer actually optimises. Instead of
rejecting an answer that is not connected, the analysis keeps its core and
records what was cut away (:func:`core_metrics`).
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


@dataclass(frozen=True)
class CoreMetrics:
    """The objective's connected component; ``has_core`` needs one objective and a constraint."""

    has_core: bool
    coherent_whole: bool
    core_variables: int
    core_constraints: int
    cut_variables: int
    cut_constraints: int
    linear: bool
    integral: bool
    minimal_size: int
    cv_ratio: float | None
    diameter: int | None


def core_model(model: Model) -> Model | None:
    """The answer reduced to the connected component of its objective (None without exactly one)."""
    if len(model.objective_functions) != 1:
        return None
    _, adj, _ = build_graph(model)
    reach = _component(("o", 0), adj)
    n_obj = len(model.objective_functions)
    keep_c = [c for i, c in enumerate(model.constraints) if ("c", n_obj + i) in reach]
    keep_v = [v for v in model.variablesInModel if ("v", v.Number) in reach]
    return Model(
        ContainsFormulation=model.ContainsFormulation,
        variablesInModel=keep_v,
        objective_functions=list(model.objective_functions),
        constraints=keep_c,
    )


def core_metrics(model: Model) -> CoreMetrics:
    whole = graph_metrics(model)
    core = core_model(model)
    if core is None:
        return CoreMetrics(False, whole.coherent, 0, 0, whole.n_variables, whole.n_constraints,
                           False, False, 0, None, None)  # fmt: skip
    m = graph_metrics(core)
    return CoreMetrics(
        has_core=m.n_variables > 0 and m.n_constraints > 0,
        coherent_whole=whole.coherent,
        core_variables=m.n_variables,
        core_constraints=m.n_constraints,
        cut_variables=whole.n_variables - m.n_variables,
        cut_constraints=whole.n_constraints - m.n_constraints,
        linear=m.linear,
        integral=m.integral,
        minimal_size=m.minimal_size,
        cv_ratio=m.cv_ratio,
        diameter=m.diameter,
    )


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
