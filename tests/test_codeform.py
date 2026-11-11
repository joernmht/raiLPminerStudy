"""The explicit-formulation and code levels of the benchmark validator (ADR-0010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from genstudy.codeform import code_blocks, code_library, explicit_formulation, read_code
from genstudy.notation import notation

KNAPSACK = r"""## Objective
$$\max \; Z = 15x_A + 40x_B + 30x_C + 50x_D$$
## Constraints
$$1600x_A + 2500x_B + 1800x_C + 3000x_D \le 6000$$
$$x_A + x_D \le 1$$
$$x_A, x_B, x_C, x_D \in \{0, 1\}$$
"""

PLAIN = """Minimize Z = 8100·x_A + 20000·x_B
1. x_A + x_B ≤ 3
2. x_A + x_B ≥ 2
"""


def test_explicit_formulation_admits_small_scalar_models_the_gate_rejects():
    assert not notation(KNAPSACK).passed
    assert explicit_formulation(KNAPSACK)
    assert explicit_formulation(PLAIN)


def test_explicit_formulation_rejects_prose_and_tool_calls():
    assert not explicit_formulation("The model is now correct. Let me produce the final version.")
    assert not explicit_formulation("We minimize cost; capacity must not be exceeded.")
    call = "<tool_call> <function=or_operator> Produce the MILP: minimize delay, x_i <= 1, y <= 2"
    assert not explicit_formulation(call)


def test_code_blocks_find_library_code_also_in_an_open_fence():
    text = "Model:\n```python\nimport pulp\nprob = pulp.LpProblem('a')\n```\n```bash\nls\n```"
    assert code_blocks(text) == ["import pulp\nprob = pulp.LpProblem('a')\n"]
    assert code_blocks("```python\nimport pulp\nx = 1\n") == ["import pulp\nx = 1\n"]
    assert code_library("import gurobipy as gp") == "gurobipy"
    assert code_blocks("no code here") == []


PYTHON = Path.home() / ".venvs" / "solvecheck" / "bin" / "python"
needs_pulp = pytest.mark.skipif(
    not PYTHON.exists(), reason="the solver sandbox venv with PuLP is not installed"
)


def _fence(code: str) -> str:
    return f"```python\n{code}\n```"


MODEL = """import pulp
p = pulp.LpProblem("k", pulp.LpMaximize)
x = pulp.LpVariable("x", cat="Binary")
y = pulp.LpVariable("y", lowBound=0)
p += 3 * x + 2 * y
p += x + y <= 4
p.solve()
print("after solve", undefined_name)
"""


@needs_pulp
@pytest.mark.parametrize(
    ("code", "stage"),
    [
        (MODEL, "usable"),
        (MODEL.replace('cat="Binary"', "lowBound=0"), "no_integer"),
        (MODEL.replace("p += x + y <= 4\n", ""), "no_core"),
        (MODEL.replace("p += 3 * x + 2 * y\n", ""), "objective_count"),
        (MODEL.replace("p += 3 * x + 2 * y", "p += x * y"), "nonlinear"),
        (
            MODEL.replace("p = pulp", "raise NotImplementedError('missing data')\np = pulp"),
            "code_error",
        ),
    ],
)
def test_read_code_reads_the_model_the_code_builds_without_solving(code, stage):
    res = read_code(_fence(code), PYTHON)
    assert res["stage"] == stage, res
    assert res["library"] == "pulp"


@needs_pulp
def test_read_code_other_library_and_no_code():
    assert read_code(_fence("import gurobipy as gp\nm = gp.Model()"), PYTHON)["stage"] == (
        "other_library"
    )
    assert read_code(KNAPSACK, PYTHON)["stage"] == "no_code"


def test_module_has_no_lp2graph_import():
    src = (Path(__file__).parents[1] / "genstudy" / "codeform.py").read_text(encoding="utf-8")
    assert "lp2graph" not in src.replace("LP2Graph", "")
