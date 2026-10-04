"""Validating the parser: test cases with known structure, scored per verdict.

LP2Graph v2 is a language model filling a schema (:mod:`genstudy.graphing`), so
its verdicts are measurements with an error rate, and the study reports that
rate. The test cases are built here, without any other library:

* six small railway MILPs whose structure is known exactly (:data:`FIXTURES`);
* five **mutations** of each, every one with a known effect on the verdicts:
  a dropped objective (incomplete), a variable used in a single equation
  (incomplete), a disconnected constraint block (incoherent), an absolute value
  in the objective (nonlinear), a constraint stated only in words (one
  constraint fewer);
* two **negative renderings** of each base model with no formulation in them, a
  prose description and a refusal, the two answer types the 2025 parser turned
  into complete graphs;
* one **long rendering** of each base model: the same formulation inside a long
  answer with a notation table, explanations, assumptions and a code listing,
  none of which may be counted (:func:`render_long`).

The expected verdicts of a case are computed by :func:`genstudy.metrics.graph_metrics`
on the case's known structure, so the parser is scored against the same
definitions the study applies. Rendering is deterministic: the same fixture and
mutation always produce the same text.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any

from genstudy.graphing import Constraint, Model, ObjectiveFunction, Variable
from genstudy.metrics import GraphMetrics, graph_metrics


@dataclass(frozen=True)
class FVar:
    symbol: str
    name: str
    domain: str
    declaration: str


@dataclass(frozen=True)
class FEq:
    name: str
    latex: str
    variables: tuple[str, ...]
    words: str
    linear: bool = True


@dataclass(frozen=True)
class Fixture:
    key: str
    title: str
    problem: str
    sets_params: str
    variables: tuple[FVar, ...]
    objective: FEq | None
    constraints: tuple[FEq, ...]
    assumptions: tuple[str, ...] = field(default_factory=tuple)

    def to_model(self) -> Model:
        """The known structure in the parser's schema (ground truth)."""
        numbers = {v.symbol: i + 1 for i, v in enumerate(self.variables)}
        variables = [
            Variable(
                Number=numbers[v.symbol],
                Abbreviation=v.symbol,
                Name=v.name,
                Description=v.name,
                Domain=v.domain,
            )
            for v in self.variables
        ]
        objectives = (
            [
                ObjectiveFunction(
                    Name=self.objective.name,
                    Number=0,
                    equation=self.objective.latex,
                    description=self.objective.words,
                    VariablesIncluded=[numbers[s] for s in self.objective.variables],
                    Linear=self.objective.linear,
                )
            ]
            if self.objective
            else []
        )
        constraints = [
            Constraint(
                Name=c.name,
                Number=i + 1,
                equation=c.latex,
                description=c.words,
                VariablesIncluded=[numbers[s] for s in c.variables],
                Linear=c.linear,
            )
            for i, c in enumerate(self.constraints)
        ]
        return Model(
            ContainsFormulation=True,
            variablesInModel=variables,
            objective_functions=objectives,
            constraints=constraints,
        )


def _v(symbol: str, name: str, domain: str, declaration: str) -> FVar:
    return FVar(symbol, name, domain, declaration)


FIXTURES: tuple[Fixture, ...] = (
    Fixture(
        key="single_track_order",
        title="Ordering trains on a blocked single-track segment",
        problem="Trains in the set $T$ must pass a segment where only one track is available.",
        sets_params=r"$T$ trains; $\tau_i$ scheduled arrival; $r_i$ earliest arrival; $h$ headway; $w_i$ priority weight; $M$ a large constant.",
        variables=(
            _v("t_i", "actual arrival time of train i", "continuous", r"$t_i \ge 0$"),
            _v("x_{ij}", "1 if train i passes before train j", "binary", r"$x_{ij} \in \{0,1\}$"),
            _v("d_i", "delay of train i", "continuous", r"$d_i \ge 0$"),
        ),
        objective=FEq(
            "Weighted delay",
            r"\min \sum_{i \in T} w_i d_i",
            ("d_i",),
            "minimize the total weighted delay",
        ),
        constraints=(
            FEq(
                "Delay definition",
                r"d_i \ge t_i - \tau_i \quad \forall i \in T",
                ("d_i", "t_i"),
                "the delay is at least the difference between actual and scheduled arrival",
            ),
            FEq(
                "Headway",
                r"t_j \ge t_i + h - M (1 - x_{ij}) \quad \forall i, j \in T, i \neq j",
                ("t_i", "x_{ij}"),
                "a train follows the previous one by at least the headway",
            ),
            FEq(
                "Order",
                r"x_{ij} + x_{ji} = 1 \quad \forall i, j \in T, i < j",
                ("x_{ij}",),
                "of two trains exactly one passes first",
            ),
            FEq(
                "Earliest arrival",
                r"t_i \ge r_i \quad \forall i \in T",
                ("t_i",),
                "no train arrives before its earliest possible time",
            ),
        ),
        assumptions=("Running times on the segment are fixed.",),
    ),
    Fixture(
        key="delay_cancellation",
        title="Delay propagation with train cancellations in an event-activity network",
        problem="Events $E$ of trains $K$ are linked by activities $A$; trains may be cancelled.",
        sets_params=r"$E$ events; $A$ activities; $K$ trains; $\pi_e$ scheduled time; $L_{ef}$ minimum duration; $w_e$ event weight; $\gamma_k$ cancellation penalty; $C$ maximum number of cancellations; $M$ a large constant.",
        variables=(
            _v("a_e", "actual time of event e", "continuous", r"$a_e \ge 0$"),
            _v("c_k", "1 if train k is cancelled", "binary", r"$c_k \in \{0,1\}$"),
        ),
        objective=FEq(
            "Delay and cancellation cost",
            r"\min \sum_{e \in E} w_e (a_e - \pi_e) + \sum_{k \in K} \gamma_k c_k",
            ("a_e", "c_k"),
            "minimize weighted event delays plus cancellation penalties",
        ),
        constraints=(
            FEq(
                "Minimum durations",
                r"a_f - a_e \ge L_{ef} - M c_{k(e)} \quad \forall (e,f) \in A",
                ("a_e", "c_k"),
                "activities keep their minimum durations unless the train is cancelled",
            ),
            FEq(
                "No early events",
                r"a_e \ge \pi_e \quad \forall e \in E",
                ("a_e",),
                "no event takes place before its scheduled time",
            ),
            FEq(
                "Cancellation budget",
                r"\sum_{k \in K} c_k \le C",
                ("c_k",),
                "at most C trains are cancelled",
            ),
        ),
    ),
    Fixture(
        key="platform_assignment",
        title="Platform assignment in a station during a disruption",
        problem="Trains $T$ must be assigned to platforms $Q$; conflicting trains on one platform are separated.",
        sets_params=r"$T$ trains; $Q$ platforms; $P$ pairs of conflicting trains; $\kappa_{tq}$ assignment cost; $\sigma_t$ planned start; $\delta$ minimum separation; $M$ a large constant.",
        variables=(
            _v("p_{tq}", "1 if train t uses platform q", "binary", r"$p_{tq} \in \{0,1\}$"),
            _v("s_t", "start time of train t at the platform", "continuous", r"$s_t \ge 0$"),
        ),
        objective=FEq(
            "Assignment cost",
            r"\min \sum_{t \in T} \sum_{q \in Q} \kappa_{tq} p_{tq}",
            ("p_{tq}",),
            "minimize the cost of the platform assignment",
        ),
        constraints=(
            FEq(
                "One platform",
                r"\sum_{q \in Q} p_{tq} = 1 \quad \forall t \in T",
                ("p_{tq}",),
                "every train gets exactly one platform",
            ),
            FEq(
                "Planned start",
                r"s_t \ge \sigma_t \quad \forall t \in T",
                ("s_t",),
                "no train starts before its planned time",
            ),
            FEq(
                "Separation",
                r"s_{t'} \ge s_t + \delta - M (2 - p_{tq} - p_{t'q}) \quad \forall (t,t') \in P, q \in Q",
                ("s_t", "p_{tq}"),
                "two conflicting trains on the same platform are separated",
            ),
        ),
    ),
    Fixture(
        key="rolling_stock_flow",
        title="Rolling stock circulation after a disruption",
        problem="Units of rolling stock flow through a network $G=(V,A)$ of trips and depots $S$.",
        sets_params=r"$V$ nodes; $A$ arcs; $A^{trip} \subseteq A$ trip arcs; $S$ depots; $c_a$ arc cost; $n_a$ units required on trip arc $a$; $\rho_s$ cost per unit at depot $s$.",
        variables=(
            _v("f_a", "number of units on arc a", "integer", r"$f_a \in \mathbb{Z}_{\ge 0}$"),
            _v(
                "u_s",
                "number of units stationed at depot s",
                "integer",
                r"$u_s \in \mathbb{Z}_{\ge 0}$",
            ),
        ),
        objective=FEq(
            "Circulation cost",
            r"\min \sum_{a \in A} c_a f_a + \sum_{s \in S} \rho_s u_s",
            ("f_a", "u_s"),
            "minimize arc costs plus depot costs",
        ),
        constraints=(
            FEq(
                "Flow conservation",
                r"\sum_{a \in \delta^+(v)} f_a - \sum_{a \in \delta^-(v)} f_a = 0 \quad \forall v \in V",
                ("f_a",),
                "the flow of units is conserved at every node",
            ),
            FEq(
                "Trip demand",
                r"f_a \ge n_a \quad \forall a \in A^{trip}",
                ("f_a",),
                "every trip gets the units it needs",
            ),
            FEq(
                "Depot capacity",
                r"\sum_{a \in \delta^+(s)} f_a \le u_s \quad \forall s \in S",
                ("f_a", "u_s"),
                "a depot sends out no more units than are stationed there",
            ),
        ),
    ),
    Fixture(
        key="rerouting",
        title="Rerouting trains around a blocked line",
        problem=r"Each train $k \in K$ chooses one route $\rho \in R_k$; routes share capacity-limited sections.",
        sets_params=r"$K$ trains; $R$ routes; $T_{k\rho}$ running time of train $k$ on route $\rho$; $e_k$ entry time; $\tau_k$ scheduled arrival; $cap_\rho$ route capacity.",
        variables=(
            _v("r_{k\\rho}", "1 if train k takes route rho", "binary", r"$r_{k\rho} \in \{0,1\}$"),
            _v("t_k", "arrival time of train k", "continuous", r"$t_k \ge 0$"),
            _v("d_k", "delay of train k", "continuous", r"$d_k \ge 0$"),
        ),
        objective=FEq(
            "Total delay", r"\min \sum_{k \in K} d_k", ("d_k",), "minimize the total delay"
        ),
        constraints=(
            FEq(
                "One route",
                r"\sum_{\rho \in R} r_{k\rho} = 1 \quad \forall k \in K",
                ("r_{k\\rho}",),
                "every train takes exactly one route",
            ),
            FEq(
                "Arrival time",
                r"t_k = e_k + \sum_{\rho \in R} T_{k\rho} r_{k\rho} \quad \forall k \in K",
                ("t_k", "r_{k\\rho}"),
                "the arrival time follows from the chosen route",
            ),
            FEq(
                "Delay",
                r"d_k \ge t_k - \tau_k \quad \forall k \in K",
                ("d_k", "t_k"),
                "the delay is the lateness against the schedule",
            ),
            FEq(
                "Route capacity",
                r"\sum_{k \in K} r_{k\rho} \le cap_\rho \quad \forall \rho \in R",
                ("r_{k\\rho}",),
                "no route carries more trains than its capacity",
            ),
        ),
    ),
    Fixture(
        key="max_deviation",
        title="Timetable adjustment minimising the largest deviation",
        problem="Departures of trains $I$ on a line are shifted; trains keep headways.",
        sets_params=r"$I$ trains; $o_i$ original departure; $h$ headway; $M$ a large constant.",
        variables=(
            _v("x_i", "new departure time of train i", "continuous", r"$x_i \ge 0$"),
            _v("y_{ij}", "1 if train i departs before train j", "binary", r"$y_{ij} \in \{0,1\}$"),
            _v("D", "largest deviation from the timetable", "continuous", r"$D \ge 0$"),
        ),
        objective=FEq("Largest deviation", r"\min D", ("D",), "minimize the largest deviation"),
        constraints=(
            FEq(
                "Deviation above",
                r"D \ge x_i - o_i \quad \forall i \in I",
                ("D", "x_i"),
                "the deviation bound covers late departures",
            ),
            FEq(
                "Deviation below",
                r"D \ge o_i - x_i \quad \forall i \in I",
                ("D", "x_i"),
                "the deviation bound covers early departures",
            ),
            FEq(
                "Headway",
                r"x_j - x_i \ge h - M (1 - y_{ij}) \quad \forall i, j \in I, i \neq j",
                ("x_i", "y_{ij}"),
                "a following train keeps the headway",
            ),
            FEq(
                "Order",
                r"y_{ij} + y_{ji} = 1 \quad \forall i, j \in I, i < j",
                ("y_{ij}",),
                "of two trains exactly one departs first",
            ),
        ),
    ),
)


# ------------------------------------------------------------------ mutations


def _first_objective_var(f: Fixture) -> str:
    return f.objective.variables[0] if f.objective else f.variables[0].symbol


def mutate(f: Fixture, kind: str) -> Fixture:
    """Return ``f`` with one known defect (or unchanged for ``identity``)."""
    if kind == "identity":
        return f
    if kind == "drop_objective":
        return replace(f, objective=None)
    if kind == "single_use_variable":
        anchor = f.variables[0].symbol
        extra = _v("g_i", "auxiliary gap variable", "continuous", r"$g_i \ge 0$")
        con = FEq(
            "Gap",
            rf"g_i \ge {anchor} - 1 \quad \forall i",
            ("g_i", anchor),
            "the gap is bounded by the first decision",
        )
        return replace(f, variables=(*f.variables, extra), constraints=(*f.constraints, con))
    if kind == "disconnected_block":
        extra = _v("z_m", "1 if maintenance slot m is used", "binary", r"$z_m \in \{0,1\}$")
        cons = (
            FEq(
                "Maintenance budget",
                r"\sum_{m \in W} z_m \le B",
                ("z_m",),
                "at most B maintenance slots are used",
            ),
            FEq(
                "Maintenance window",
                r"z_m \le \zeta_m \quad \forall m \in W",
                ("z_m",),
                "a slot can only be used when it is available",
            ),
        )
        return replace(f, variables=(*f.variables, extra), constraints=(*f.constraints, *cons))
    if kind == "nonlinear_objective":
        assert f.objective is not None
        sym = _first_objective_var(f)
        obj = replace(
            f.objective,
            latex=f.objective.latex + rf" + \mu \sum \left| {sym} - \bar{{{sym}}} \right|",
            linear=False,
        )
        return replace(f, objective=obj)
    if kind == "words_constraint":
        return replace(f, constraints=f.constraints[:-1])
    raise ValueError(f"unknown mutation {kind!r}")


MUTATIONS: tuple[str, ...] = (
    "identity",
    "drop_objective",
    "single_use_variable",
    "disconnected_block",
    "nonlinear_objective",
    "words_constraint",
)
NEGATIVES: tuple[str, ...] = ("prose", "refusal")
#: Renderings of the unchanged base model that make the answer long and noisy, like real
#: answers (the pilot's ran to 13,000 characters): the expected structure is the base's.
LONG_VARIANTS: tuple[str, ...] = ("long",)


# ------------------------------------------------------------------ rendering


def render_formulation(f: Fixture, *, words_for: FEq | None = None) -> str:
    """A typical generated answer: sections in markdown, mathematics in LaTeX."""
    lines = [f"## {f.title}", "", f.problem, "", "### Sets and parameters", f.sets_params, ""]
    lines += ["### Decision variables"]
    lines += [f"- {v.declaration}: {v.name}" for v in f.variables]
    if f.objective:
        lines += ["", "### Objective function", f"$$ {f.objective.latex} $$"]
        lines += [f"We {f.objective.words}."]
    lines += ["", "### Constraints"]
    for i, c in enumerate(f.constraints, start=1):
        lines += [f"{i}. **{c.name}**: $$ {c.latex} $$"]
    if words_for is not None:
        lines += [
            f"{len(f.constraints) + 1}. **{words_for.name}**: in addition, {words_for.words}."
        ]
    if f.assumptions:
        lines += ["", "### Assumptions"] + [f"- {a}" for a in f.assumptions]
    return "\n".join(lines) + "\n"


def render_long(f: Fixture) -> str:
    """The base model inside a long answer: notation table, explanations, assumptions, code.

    Everything added is a trap for the parser: the notation table lists parameters next to
    variables, the explanations restate every constraint in words (they must not be counted
    twice), and the code block repeats the model in Python (it must not be parsed).
    """
    table = ["| Symbol | Meaning | Type |", "|---|---|---|"]
    table += [f"| ${v.symbol}$ | {v.name} | decision variable ({v.domain}) |" for v in f.variables]
    table += [f"| (see list) | {f.sets_params} | sets and parameters |"]
    explain = [
        f"**{c.name}.** This constraint makes sure that {c.words}. It is written for every "
        "relevant combination of indices and is essential for the operational feasibility of "
        "the timetable; without it, the model could return schedules that look optimal but "
        "violate the rules of railway operation."
        for c in f.constraints
    ]
    code = [
        "```python",
        "import pyomo.environ as pyo",
        "m = pyo.ConcreteModel()",
        *[f"# variable {v.symbol}: {v.name}" for v in f.variables],
        "m.obj = pyo.Objective(rule=lambda m: total_cost(m), sense=pyo.minimize)",
        *[
            f"m.c{i} = pyo.Constraint(rule=rule_{i})  # {c.name}"
            for i, c in enumerate(f.constraints)
        ],
        "pyo.SolverFactory('highs').solve(m)",
        "```",
    ]
    parts = [
        "Below is a complete mixed-integer linear programming model inspired by the provided "
        "input. I first introduce the notation, then state the model, explain each element and "
        "list my assumptions; a short implementation sketch closes the answer.",
        "### Notation",
        "\n".join(table),
        render_formulation(f),
        "### Explanation of the model",
        "\n\n".join(explain),
        "### Assumptions",
        "- Data on running times, dwell times and headways are deterministic and known.",
        "- The disruption duration is known at the time of rescheduling.",
        "- Trains that are not affected keep their planned schedule where possible.",
        "### Implementation sketch",
        "\n".join(code),
        "The model can be solved with any MILP solver; for large instances a rolling horizon "
        "or a decomposition approach is advisable.",
    ]
    return "\n\n".join(parts) + "\n"


def render_prose(f: Fixture) -> str:
    """The same model described in words only: no formulation in the text."""
    decisions = "; ".join(v.name for v in f.variables)
    rules = " ".join(f"It ensures that {c.words}." for c in f.constraints)
    goal = f"The model aims to {f.objective.words}." if f.objective else ""
    return (
        f"## {f.title}\n\nA suitable optimization model for this problem would decide the "
        f"following quantities: {decisions}. {goal} {rules} Such a model can be formulated "
        "as a mixed-integer linear program and solved with a standard solver.\n"
    )


def render_refusal(f: Fixture) -> str:
    """A refusal that outlines the task: the 2025 multi-step failure mode."""
    return (
        "Developing the complete optimization model for this problem requires details that "
        "are not given in the provided text, so I cannot write down the exact equations. "
        f"In general, a model for {f.title.lower()} would contain decision variables, an "
        "objective function and constraints describing the operational rules. If you provide "
        "the missing data, I can formulate the model.\n"
    )


# ------------------------------------------------------------------ cases


@dataclass(frozen=True)
class Case:
    case_id: str
    fixture: str
    variant: str
    text: str
    expected: GraphMetrics


def _empty_model() -> Model:
    return Model(
        ContainsFormulation=False, variablesInModel=[], objective_functions=[], constraints=[]
    )


def cases() -> Iterator[Case]:
    """All test cases in a fixed order."""
    for f in FIXTURES:
        for kind in MUTATIONS:
            mutated = mutate(f, kind)
            words = f.constraints[-1] if kind == "words_constraint" else None
            text = render_formulation(mutated, words_for=words)
            yield Case(f"{f.key}.{kind}", f.key, kind, text, graph_metrics(mutated.to_model()))
        for kind, renderer in (("prose", render_prose), ("refusal", render_refusal)):
            yield Case(f"{f.key}.{kind}", f.key, kind, renderer(f), graph_metrics(_empty_model()))
        yield Case(f"{f.key}.long", f.key, "long", render_long(f), graph_metrics(f.to_model()))


# ------------------------------------------------------------------ scoring

VERDICTS: tuple[str, ...] = (
    "contains_formulation",
    "complete_struct",
    "coherent",
    "linear",
    "integral",
)
COUNTS: tuple[str, ...] = ("n_objectives", "n_variables", "n_constraints")


def accepted(m: GraphMetrics) -> bool:
    """Paper 0's acceptance on the structure: a formulation, complete and coherent."""
    return m.contains_formulation and m.complete_struct and m.coherent


def score(expected: GraphMetrics, predicted: GraphMetrics | None) -> dict[str, Any]:
    """Per-field agreement of one prediction with the ground truth."""
    if predicted is None:
        return {"parsed": False}
    out: dict[str, Any] = {"parsed": True}
    for name in (*VERDICTS, *COUNTS):
        out[name] = getattr(expected, name) == getattr(predicted, name)
    out["accepted"] = accepted(expected) == accepted(predicted)
    return out
