"""Two further readings of an answer the notation gate turns away (benchmark check, ADR-0010).

The notation gate (:mod:`genstudy.notation`) wants three of five operator groups, which an
indexed railway model shows (sums, "for all", "subject to") but a small explicit model such as
``max 15 x_A + 40 x_B  s.t.  1600 x_A + 2500 x_B <= 6000`` does not. And an answer may state its
model as solver code rather than as equations, as practitioners often do. Two levels, used
after the gate fails:

* :func:`explicit_formulation`: an objective keyword and at least two (in)equalities, each with a
  symbol on one side. Such an answer goes to the parsing model like a gated one.
* :func:`read_code`: solver code is found and, for PuLP, executed with ``solve`` stopped, so the
  model the code builds is read directly (objective, constraints, variable types). Nothing is
  solved and nothing is parsed by a language model. Other libraries are detected, not read.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

_OBJECTIVE = re.compile(
    r"\\(?:max|min)(?:imize|imise)?(?![A-Za-z])|\b(?:max|min)(?:imize|imise)?\b|"
    r"\bobjective\b", re.IGNORECASE)  # fmt: skip
_RELATION = re.compile(r"<=|>=|≤|≥|⩽|⩾|\\le(?:q|qslant)?(?![A-Za-z])|\\ge(?:q|qslant)?(?![A-Za-z])")
_SYMBOL = re.compile(r"[A-Za-z](?:_\{?[A-Za-z0-9,]+\}?)?")

# An unfinished agent turn (a request to a tool) describes a model; it does not state one.
_TOOL_CALL = re.compile(r"<tool_call>|<invoke\b|<function=")

#: A formulation needs this many (in)equalities with a symbol on the left of the relation.
MIN_RELATIONS = 2


def explicit_formulation(text: str) -> bool:
    """An objective keyword and at least :data:`MIN_RELATIONS` symbolic inequality lines."""
    if _TOOL_CALL.search(text) or not _OBJECTIVE.search(text):
        return False
    n = 0
    for line in text.splitlines():
        m = _RELATION.search(line)
        if m and _SYMBOL.search(line[: m.start()]) and re.search(r"\d|[A-Za-z]", line[m.end() :]):
            n += 1
    return n >= MIN_RELATIONS


_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.DOTALL)
LIBRARIES = {
    "pulp": r"\bimport\s+pulp\b|\bfrom\s+pulp\s+import\b",
    "gurobipy": r"\bgurobipy\b",
    "pyomo": r"\bpyomo\b",
    "ortools": r"\bortools\b",
    "scipy": r"\bscipy\.optimize\b|\bfrom\s+scipy\b",
    "cvxpy": r"\bcvxpy\b",
    "jump": r"\busing\s+JuMP\b",
    "ampl": r"^\s*(?:var|param|set)\s+\w+.*;\s*$",
}


def code_blocks(text: str) -> list[str]:
    """Fenced code blocks that use an optimization library (in order)."""
    bodies = [body for _lang, body in _FENCE.findall(text)]
    if text.count("```") % 2:  # a last fence left open (a truncated answer)
        bodies.append(text[text.rindex("```") :].partition("\n")[2])
    return [b for b in bodies if code_library(b)]


def code_library(code: str) -> str | None:
    for name, pat in LIBRARIES.items():
        if re.search(pat, code, re.MULTILINE):
            return name
    return None


# Runs before the answer's code: every LpProblem is recorded, solve() stops the script, and at
# exit the recorded models are written as JSON. PuLP refuses a product of two variables
# (TypeError), so a script that builds a nonlinear model fails before it reaches solve().
_PRELUDE = r"""
import atexit, json, sys
import pulp
_P = []
_init = pulp.LpProblem.__init__
def _rec(self, *a, **k):
    _init(self, *a, **k)
    _P.append(self)
pulp.LpProblem.__init__ = _rec
class _Stop(BaseException):
    pass
def _stop(self, *a, **k):
    raise _Stop()
pulp.LpProblem.solve = _stop
def _dump():
    out = []
    for p in _P:
        vs = p.variables()
        obj = p.objective
        out.append({"objective_terms": len(obj) if obj is not None else 0,
                    "constraints": len(p.constraints), "variables": len(vs),
                    "integer": sum(v.cat in ("Integer", "Binary") for v in vs)})
    sys.__stdout__.write("\nCODEFORM=" + json.dumps(out) + "\n")
atexit.register(_dump)
def _hook(t, e, tb, _old=sys.excepthook):
    if t is _Stop:
        return
    _old(t, e, tb)
sys.excepthook = _hook
"""

#: Stages of a code answer, ordered like :data:`genstudy.analyze.STAGES`.
CODE_STAGES = ("no_code", "other_library", "code_error", "nonlinear", "objective_count",
               "no_core", "no_integer", "usable")  # fmt: skip


def read_code(text: str, python: str | Path, timeout_s: int = 60) -> dict:
    """The structure of the model the answer's PuLP code builds, as a stage and counts."""
    blocks = code_blocks(text)
    if not blocks:
        return {"stage": "no_code", "library": None}
    library = code_library(blocks[-1])
    code = "\n\n".join(b for b in blocks if code_library(b) == library)
    if library != "pulp":
        return {"stage": "other_library", "library": library}
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "model.py"
        script.write_text(_PRELUDE + "\n" + code, encoding="utf-8", newline="\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
        try:
            proc = subprocess.run([str(python), "-I", str(script)], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=timeout_s)  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"stage": "code_error", "library": library, "error": "timeout"}
    found = re.findall(r"^CODEFORM=(.*)$", proc.stdout, re.MULTILINE)
    models = json.loads(found[-1]) if found else []
    # The stop at solve() exits silently; an uncaught error leaves a traceback (warnings do not).
    failed = "Traceback (most recent call last)" in proc.stderr
    err = proc.stderr.strip().splitlines()[-1][:200] if failed else None
    res = {"library": library, "models": models, "error": err}
    if re.search(r"Non-constant(?:s| expressions) cannot be multiplied", proc.stderr):
        return {**res, "stage": "nonlinear"}
    if not models or failed:
        return {**res, "stage": "code_error"}
    m = max(models, key=lambda x: (x["constraints"], x["variables"]))
    if m["objective_terms"] == 0:
        return {**res, "stage": "objective_count"}
    if m["constraints"] == 0:
        return {**res, "stage": "no_core"}
    if m["integer"] == 0:
        return {**res, "stage": "no_integer"}
    return {**res, "stage": "usable"}
