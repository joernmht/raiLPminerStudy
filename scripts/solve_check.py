"""Can the generated MILPs be solved? An execution check on a sample (exploratory).

    set -a; . ~/.config/raiLP/secrets.env; set +a
    python3 scripts/solve_check.py draw     # the sample (seeded)
    python3 scripts/solve_check.py solve    # translate, run with PuLP/CBC, repair (on the record)
    python3 scripts/solve_check.py report

A formulation without data is a family of instances; "solvable" needs an instance. A
translator, an LLM that is none of the five generators, implements each sampled formulation
in PuLP exactly as written and invents the smallest plausible instance, and CBC solves it
under a time limit. Outcomes: the translator refuses a construct that PuLP cannot express as
written (``NotImplementedError`` by instruction, or PuLP's own refusal of a product of variables
or a strict inequality), the code fails, or CBC reports a status. A script that fails is sent
back with its error, at most twice, with the instruction to correct the code or the invented
data and not the model (repair rounds, as in execution-feedback loops); pilot v1 had none and
is kept in ``solvecheck/v1/``.
The six published formulations calibrate the check: if they do not solve, the check measures
the translation rather than the models. Controls are answers that the structural checks
reduce or reject (a graph that is not connected; a nonlinear core), translated as a whole.

The translation is an LLM step and can repair or break a model, an invented instance can make
a sound model infeasible, and "optimal" means that the code runs, not that the model is right:
the check is descriptive. The translator names variable and constraint families, so that the
families of the built PuLP model can be compared with the graph of the same text. Every
round (request, response and the execution's result) is stored in ``solvecheck/rounds.jsonl``. Decided after the runs (Joern, 2026-10-07: "pilot option 2").
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import PacingSpec, load_study
from genstudy.graphing import Model
from genstudy.llm import ChatClient
from genstudy.store import RunStore

STUDY = "studies/paper0_2026/study.toml"
SEED = 2026
PROMPT_VERSION = "2026.10.7b"
#: Pilot sample: usable MILPs per generating model, and controls of each kind.
USABLE_PER_MODEL = 2
CONTROLS = {"disconnected": 2, "nonlinear": 2}
TRANSLATOR = "mistralai/devstral-2512"
PROVIDER = {"order": ["mistral/eu"], "allow_fallbacks": False}
VENV_PYTHON = Path.home() / ".venvs" / "solvecheck" / "bin" / "python"
RUN_TIMEOUT_S = 240
MAX_REPAIRS = 2

SYSTEM = (
    "You implement optimization models as Python code with PuLP. You receive a text that "
    "states a mathematical optimization model. Implement exactly the model that the text "
    "states: the same decision variables with the same domains, the same objective function "
    "and the same constraints. Do not add, drop, merge, correct, relax or linearize anything, "
    "and use no library other than PuLP and the Python standard library.\n\n"
    "The text gives no data. Invent the smallest plausible instance that the model can work "
    "with, for example two or three trains, three or four stations or segments and a short "
    "time horizon, and choose the values so that the instance is feasible if the model "
    "allows that. Put all data at the top of the script.\n\n"
    "Make the invented data complete: every set, and every parameter for every combination "
    "of indices that the model uses.\n\n"
    "If the text states a constraint or an objective function that PuLP cannot express as "
    "written, such as a product of two variables, a strict inequality, an absolute value or "
    'a maximum of variables, do not reformulate it: raise NotImplementedError("<name of the '
    'equation>: <reason>") at that point.\n\n'
    "Name the problem `prob`. Name every variable '<family>__<indices>' and every constraint "
    "'<name>__<indices>', where <family> is a short identifier of the variable family as the "
    "text writes it (one per family), <name> a short identifier of the constraint family (one "
    "per numbered or named constraint of the text) and <indices> all indices of the variable "
    "or constraint, so that every name is unique; use only letters, digits and "
    "underscores.\n\n"
    "Solve with prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=60)) and print exactly one "
    "line: STATUS=<pulp.LpStatus[prob.status]> OBJECTIVE=<pulp.value(prob.objective)>.\n\n"
    "Answer with one Python code block and nothing else."
)
CALL = "Implement this model:\n\n"
REPAIR = (
    "The script fails with the error below. Correct the error in the code or in the invented "
    "data, and do not change the model: the same variables, objective function and "
    "constraints. If the error comes from a construct that PuLP cannot express as written, "
    "raise NotImplementedError as instructed. Answer with the complete corrected script in "
    "one Python code block.\n\nError:\n"
)
#: PuLP's own refusals of what a MILP cannot state (besides NotImplementedError by instruction).
NOT_EXPRESSIBLE = (
    "NotImplementedError",
    "Non-constant expressions cannot be multiplied",
    "not supported between instances of 'LpVariable'",
    "not supported between instances of 'LpAffineExpression'",
)
EPILOGUE = """

# ---- appended by scripts/solve_check.py: the families of the built model ----
import json as _sc_json
import pulp as _sc_pulp
_sc_prob = globals().get("prob")
if isinstance(_sc_prob, _sc_pulp.LpProblem):
    print("FAMILIES=" + _sc_json.dumps({
        "variables": sorted({v.name.split("__")[0] for v in _sc_prob.variables()}),
        "constraints": sorted({str(n).split("__")[0] for n in _sc_prob.constraints}),
        "n_variables": len(_sc_prob.variables()),
        "n_constraints": len(_sc_prob.constraints),
        "objective_terms": len(_sc_prob.objective or {}),
        "sol_status": _sc_pulp.LpSolution.get(_sc_prob.sol_status, str(_sc_prob.sol_status)),
    }))
"""


def _out(root: Path) -> Path:
    path = root / "solvecheck"
    path.mkdir(exist_ok=True)
    return path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def draw(spec) -> None:
    rows = json.loads((spec.root / "analysis" / "summary.json").read_text(encoding="utf-8"))["rows"]
    answers = {}
    for model in spec.models:
        for r in RunStore(spec.root / "runs" / f"{model}.jsonl").records():
            answers[r["run_id"]] = r.get("final_answer") or ""
    rng = random.Random(SEED)
    items, taken = [], set()
    for model in spec.models:
        pool = sorted(r["run_id"] for r in rows if r["model"] == model and r["stage"] == "usable"
                      and r["coherent_whole"])  # fmt: skip
        for run_id in rng.sample(pool, USABLE_PER_MODEL):
            items.append({"id": run_id, "kind": "usable", "model": model})
            taken.add(run_id)
    pools = {
        "disconnected": sorted(r["run_id"] for r in rows
                               if r["stage"] == "usable" and not r["coherent_whole"]),
        "nonlinear": sorted(r["run_id"] for r in rows if r["stage"] == "nonlinear"),
    }  # fmt: skip
    for kind, n in CONTROLS.items():
        pool = [x for x in pools[kind] if x not in taken]
        for run_id in rng.sample(pool, n):
            items.append({"id": run_id, "kind": kind, "model": run_id.split(".")[2]})
            taken.add(run_id)
    for item in items:
        item["text"] = answers[item["id"]]
    for path in sorted((spec.root / "references").glob("P*.md")):
        if re.fullmatch(r"P\d+b?", path.stem):
            items.append({"id": f"ref:{path.stem}", "kind": "reference", "model": "published",
                          "text": path.read_text(encoding="utf-8")})  # fmt: skip
    for item in items:
        item["text_sha256"] = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
    doc = {"seed": SEED, "prompt_version": PROMPT_VERSION, "items": items}
    (_out(spec.root) / "sample.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                                 encoding="utf-8", newline="\n")  # fmt: skip
    print(Counter(i["kind"] for i in items))


def _code(content: str) -> str | None:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, flags=re.S)
    if blocks:
        return max(blocks, key=len)
    return content if "import pulp" in content else None


def _run(code: str) -> dict:
    """Run one script in a fresh directory of the solvecheck environment."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "model.py"
        script.write_text(code + EPILOGUE, encoding="utf-8", newline="\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
        start = time.monotonic()
        try:
            proc = subprocess.run([str(VENV_PYTHON), str(script)], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=RUN_TIMEOUT_S)  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"outcome": "timeout"}
    stdout, stderr = proc.stdout, proc.stderr
    status = re.search(r"STATUS=(\S+(?: \S+)?) OBJECTIVE=(\S+)", stdout)
    families = re.search(r"FAMILIES=(\{.*\})", stdout)
    if proc.returncode != 0:
        refused = any(p in stderr for p in NOT_EXPRESSIBLE)
        outcome = "not_expressible" if refused else "code_error"
    elif status is None:
        outcome = "no_status"
    else:
        outcome = status.group(1).lower().replace(" ", "_")
    return {
        "outcome": outcome,
        "returncode": proc.returncode,
        "status_line": status.group(0) if status else None,
        "families": json.loads(families.group(1)) if families else None,
        "stderr_tail": stderr[-1500:],
        "runtime_s": round(time.monotonic() - start, 1),
    }


def solve(spec) -> None:
    """Translate, run and, after a failure of the code, repair; one record per round."""
    out = _out(spec.root)
    sample = json.loads((out / "sample.json").read_text(encoding="utf-8"))
    done = {r["id"] for r in _read_jsonl(out / "rounds.jsonl") if r["final"]}
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set (set -a; . ~/.config/raiLP/secrets.env; set +a)")
    pacing = PacingSpec(min_interval_s=2.0, max_requests_per_day=300, request_timeout_s=600.0,
                        max_tries=4)  # fmt: skip
    client = ChatClient("https://openrouter.ai/api/v1", key, pacing=pacing,
                        counter_path=out / "requests_per_day.json")  # fmt: skip
    for item in sample["items"]:
        if item["id"] in done:
            continue
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": CALL + item["text"]}]  # fmt: skip
        for rnd in range(MAX_REPAIRS + 1):
            body = {"model": TRANSLATOR, "messages": list(messages), "temperature": 0.0,
                    "seed": SEED, "max_tokens": 16000, "provider": PROVIDER,
                    "usage": {"include": True}}  # fmt: skip
            call = client.complete(body, describe=f"translator {item['id']} round {rnd}")
            code = _code(call.content)
            result = _run(code) if code else {"outcome": "no_code"}
            final = result["outcome"] != "code_error" or rnd == MAX_REPAIRS
            _append(out / "rounds.jsonl", {"id": item["id"], "kind": item["kind"], "round": rnd,
                                           "prompt_version": PROMPT_VERSION,
                                           "text_sha256": item["text_sha256"],
                                           "call": call.to_record(), "result": result,
                                           "final": final})  # fmt: skip
            print(f"{item['id']} round {rnd}: {result['outcome']}", flush=True)
            if final:
                break
            error = "\n".join((result.get("stderr_tail") or "").strip().splitlines()[-25:])
            messages += [{"role": "assistant", "content": call.content},
                         {"role": "user", "content": REPAIR + error}]  # fmt: skip


def report(spec) -> None:
    out = _out(spec.root)
    results = {}
    for r in _read_jsonl(out / "rounds.jsonl"):
        if r["final"]:
            results[r["id"]] = {"kind": r["kind"], "round": r["round"], **r["result"]}
    graphs = {}
    for model in spec.models:
        for g in RunStore(spec.root / "graphs" / f"{model}.jsonl").records():
            graphs[g["run_id"]] = g
    table = defaultdict(Counter)
    lines = ["# Solvability check (pilot)", "",
             "| item | kind | outcome | repairs | code: variable / constraint families | text graph: variables / constraints | note |",
             "|---|---|---|---|---|---|---|"]  # fmt: skip
    for run_id, r in sorted(results.items(), key=lambda kv: (kv[1]["kind"], kv[0])):
        table[r["kind"]][r["outcome"]] += 1
        fam = r.get("families") or {}
        code_counts = (
            f"{len(fam.get('variables', []))} / {len(fam.get('constraints', []))}" if fam else "--"
        )
        if run_id.startswith("ref:"):
            ref = Model.model_validate_json(
                (spec.root / "references" / f"{run_id[4:]}.json").read_text(encoding="utf-8")
            )
            text_counts = f"{len(ref.variablesInModel)} / {len(ref.constraints)}"
        else:
            m = (graphs.get(run_id) or {}).get("metrics") or {}
            text_counts = f"{m.get('n_variables', '--')} / {m.get('n_constraints', '--')}"
        note = (
            (r.get("stderr_tail") or "").strip().splitlines()[-1:]
            if r["outcome"] in ("code_error", "not_expressible")
            else []
        )
        lines.append(f"| {run_id} | {r['kind']} | {r['outcome']} | {r['round']} | {code_counts} | {text_counts} | "
                     f"{(note[0] if note else '')[:160].replace('|', '/')} |")  # fmt: skip
    summary = {kind: dict(c) for kind, c in sorted(table.items())}
    (out / "report.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")  # fmt: skip
    (out / "report.md").write_text("\n".join(lines) + "\n\n" + json.dumps(summary, indent=1) + "\n",
                                   encoding="utf-8", newline="\n")  # fmt: skip
    print("\n".join(lines))
    print(json.dumps(summary, indent=1))


def main() -> int:
    steps = {"draw": draw, "solve": solve, "report": report}
    if len(sys.argv) < 2 or sys.argv[1] not in steps:
        sys.exit(__doc__)
    steps[sys.argv[1]](load_study(sys.argv[2] if len(sys.argv) > 2 else STUDY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
