"""Paper 0's workflows and its LP2Graph validator on public benchmark problems.

    set -a; . ~/.config/raiLP/secrets.env; set +a
    python3 scripts/benchmark_check.py fetch                # the benchmark texts (once)
    python3 scripts/benchmark_workflows.py draw             # 30 problems (seeded)
    python3 scripts/benchmark_workflows.py generate <model> # 4 workflows x 30 problems
    python3 scripts/benchmark_workflows.py graph <model>    # gate/explicit level + LP2Graph parser
    python3 scripts/benchmark_workflows.py codeform <model> # code level (PuLP read, not solved)
    python3 scripts/benchmark_workflows.py codecheck -      # code level on the model-only answers
    python3 scripts/benchmark_workflows.py scrub -          # redact quoted benchmark text (before git)
    python3 scripts/benchmark_workflows.py translate <model># formulation -> PuLP -> CBC
    python3 scripts/benchmark_workflows.py report

The study's instrument, unchanged, on a task with a known answer. Each of the five models runs
each of the four workflows (prompts verbatim, temperature 0.6 as in Experiment 2) on 30 word
problems from IndustryOR and NL4Opt. The answer goes through the study's validator (notation
gate, LP2Graph parser, structural checks; ``genstudy.analyze.yield_stage``). Independently, a
translator that is none of the five generators implements the written formulation in PuLP, as
written and with the numbers the text states (it never sees the problem), and CBC solves it.
The objective is compared with the benchmark's original label and with the cleaned label of
Xiao et al. (2025). That gives, per answer, the validator's verdict and a ground truth, so the
check measures how well the validator separates right from wrong formulations, and how far the
"ground truth" itself depends on the label version.

The study's yield requires integer variables (stage ``no_integer``); many benchmark problems
are LPs, so the validator's acceptance here is "passes every check up to linearity" and the
integrality verdict is reported on its own. Decided 2026-11-07 (Joern: 4 workflows x 5 models
x 30 problems, prompts verbatim; replaces the model-only check of benchmark_check.py in the
paper). Texts stay out of git, as in ADR-0009.

Two levels were added on 2026-11-11 (ADR-0010; Joern: rejecting good formulations for their
form "seems very academic"): an answer the gate turns away is still parsed when it is an
explicit formulation, and solver code in an answer is read directly. The report gives the
validator with and without them.
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
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_check as bc

from genstudy.analyze import yield_stage
from genstudy.codeform import explicit_formulation, read_code
from genstudy.config import PacingSpec, load_study
from genstudy.graphing import graph_answer, grapher_fingerprint
from genstudy.llm import ChatClient, EndpointError
from genstudy.metrics import core_metrics, graph_metrics
from genstudy.notation import notation
from genstudy.prompts import PROMPT_VERSION as STUDY_PROMPTS
from genstudy.workflows import run_workflow

OUT = bc.OUT.parent / "benchmark_workflows_2026"
SEED = 20261108
WORKFLOWS = ("ZS", "CFC", "OE", "PS")
TEMPERATURE = 0.6
PER_GROUP = {("IndustryOR", "kept"): 8, ("IndustryOR", "removed"): 7,
             ("NL4Opt", "kept"): 8, ("NL4Opt", "corrected"): 7}  # fmt: skip
TRANSLATOR = "mistralai/devstral-2512"
TRANSLATOR_PROVIDER = {"order": ["mistral/eu"], "allow_fallbacks": False}
TRANSLATOR_VERSION = "2026.11.7"
MAX_REPAIRS = 2
RUN_TIMEOUT_S = 120

TRANSLATOR_SYSTEM = (
    "You implement optimization models as Python code with PuLP. You receive a text that "
    "states a mathematical optimization model of a concrete problem. Implement exactly the "
    "model that the text states: the same decision variables with the same domains, the same "
    "objective function and the same constraints. Do not add, drop, merge, correct, relax or "
    "linearize anything, and use no library other than PuLP and the Python standard library."
    "\n\nTake every number from the text. Do not invent data: if a value that the model needs "
    'is not stated in the text, raise NotImplementedError("missing data: <parameter>") at the '
    "top of the script.\n\n"
    "If the text states a constraint or an objective function that PuLP cannot express as "
    "written, such as a product of two variables, a strict inequality, an absolute value or "
    'a maximum of variables, do not reformulate it: raise NotImplementedError("<name of the '
    'equation>: <reason>") at that point.\n\n'
    "Name the problem `prob`. Solve with prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=60)) "
    "and print exactly one line: STATUS=<pulp.LpStatus[prob.status]> "
    "OBJECTIVE=<pulp.value(prob.objective)>.\n\nAnswer with one Python code block and nothing else."
)
CALL = "Implement this model:\n\n"
REPAIR = (
    "The script fails with the error below. Correct the error in the code, and do not change "
    "the model or its numbers. If the error comes from a construct that PuLP cannot express as "
    "written, or from a value the text does not state, raise NotImplementedError as instructed. "
    "Answer with the complete corrected script in one Python code block.\n\nError:\n"
)
NOT_EXPRESSIBLE = (
    "Non-constant expressions cannot be multiplied",
    "not supported between instances of 'LpVariable'",
    "not supported between instances of 'LpAffineExpression'",
)


def _read(path: Path) -> list[dict]:
    return bc._read_jsonl(path)


def _write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def draw(_spec) -> None:
    """30 problems from the model-only check's sample, stratified by benchmark and audit."""
    pool = json.loads((bc.OUT / "sample.json").read_text(encoding="utf-8"))["items"]
    rng = random.Random(SEED)
    items = []
    for (bench, audit), n in PER_GROUP.items():
        group = sorted((i for i in pool if i["benchmark"] == bench and i["audit"] == audit),
                       key=lambda i: i["id"])  # fmt: skip
        items += rng.sample(group, n)
    _write_json(OUT / "sample.json", {"seed": SEED, "temperature": TEMPERATURE,
                                      "workflows": list(WORKFLOWS), "items": items})  # fmt: skip
    print(Counter((i["benchmark"], i["audit"]) for i in items))


def _sample() -> list[dict]:
    return json.loads((OUT / "sample.json").read_text(encoding="utf-8"))["items"]


def _texts() -> dict[str, str]:
    return {i["question_sha256"]: i["question"] for i in bc._items_with_text()}


def _client(base_url: str, key_env: str, counter: str, cap: int = 1700) -> ChatClient:
    key = os.environ.get(key_env)
    if not key:
        sys.exit(f"{key_env} is not set (set -a; . ~/.config/raiLP/secrets.env; set +a)")
    pacing = PacingSpec(min_interval_s=3.0, max_requests_per_day=cap, request_timeout_s=900.0,
                        max_tries=6)  # fmt: skip
    return ChatClient(base_url, key, pacing=pacing,
                      counter_path=OUT / f"requests_per_day.{counter}.json")  # fmt: skip


def _endpoint(spec, model) -> tuple[str, str, str]:
    base = model.base_url or spec.base_url
    counter = "scads" if "scads" in base else f"openrouter.{model.key}"
    return base, model.api_key_env or spec.api_key_env, counter


def generate(spec, model_key: str) -> None:
    model = bc._model(spec, model_key)
    base, key_env, counter = _endpoint(spec, model)
    client = _client(base, key_env, counter)
    texts = _texts()
    path = OUT / "runs" / f"{model_key}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _read(path)
    # A credit stop (HTTP 402) says nothing about the model: drop those records and retry them.
    kept = [r for r in records if "HTTP 402" not in (r.get("error") or "")]
    if len(kept) < len(records):
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in kept),
                        encoding="utf-8", newline="\n")  # fmt: skip
    done = {r["run_id"] for r in kept}
    for item in _sample():
        for wf in WORKFLOWS:
            run_id = f"bench.{item['id']}.{model_key}.{wf}"
            if run_id in done:
                continue
            seed = int(_sha(f"{SEED}:{run_id}")[:8], 16) % 2**31
            started = time.time()
            try:
                trace = run_workflow(wf, client=client, model=model, temperature=TEMPERATURE,
                                     seed=seed, paper_text=texts[item["question_sha256"]],
                                     pacing=spec.pacing)  # fmt: skip
            except EndpointError as exc:
                if exc.transient or "HTTP 402" in str(exc):
                    print(f"stopped (transient, resume later): {exc}", flush=True)
                    return
                record = {"status": "request_error", "error": str(exc)[:300], "final_answer": ""}
            else:
                record = {"status": "ok", **asdict(trace)}
            for call in record.get("calls", []):
                # The benchmark text stays out of the record (it is in the first user message).
                call["request"]["messages"] = [m if m.get("role") != "user" or i > 1 else
                                               {"role": "user", "content": "<benchmark text>"}
                                               for i, m in enumerate(call["request"]["messages"])]  # fmt: skip
            record.update(run_id=run_id, item=item["id"], model=model_key, workflow=wf,
                          seed=seed, temperature=TEMPERATURE, study_prompts=STUDY_PROMPTS,
                          question_sha256=item["question_sha256"],
                          wall_s=round(time.time() - started, 1))  # fmt: skip
            bc._append(path, record)
            print(f"{run_id}: {record['status']} {len(record.get('final_answer') or '')} chars",
                  flush=True)  # fmt: skip


def graph(spec, model_key: str) -> None:
    grapher = spec.grapher
    client = _client(spec.base_url, spec.api_key_env, "scads")
    out = OUT / "graphs" / f"{model_key}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    # The last row of a run counts; a run turned away by the gate gets a second row when its
    # answer is an explicit formulation (genstudy.codeform, ADR-0010).
    last = {r["run_id"]: r for r in _read(out)}
    for rec in _read(OUT / "runs" / f"{model_key}.jsonl"):
        if rec.get("status") != "ok":
            continue
        prev = last.get(rec["run_id"])
        explicit = explicit_formulation(rec["final_answer"])
        if prev and (prev["gate_passed"] or prev.get("level") == "explicit" or not explicit):
            continue
        gate = notation(rec["final_answer"])
        level = "gate" if gate.passed else ("explicit" if explicit else None)
        row = {"run_id": rec["run_id"], "gate_passed": gate.passed, "level": level,
               "grapher": grapher.served_id, "grapher_prompts": grapher_fingerprint(),
               "metrics": None, "core": None, "call": None, "error": None}  # fmt: skip
        if level:
            try:
                res = graph_answer(client, grapher, rec["final_answer"])
            except EndpointError as exc:
                if exc.transient or "HTTP 402" in str(exc):
                    print(f"stopped (transient, resume later): {exc}", flush=True)
                    return
                row["error"] = str(exc)[:300]
            else:
                row["call"] = res.call.to_record()
                row["error"] = res.error
                if res.model:
                    row["metrics"] = asdict(graph_metrics(res.model))
                    row["core"] = asdict(core_metrics(res.model))
        bc._append(out, row)
        print(f"{rec['run_id']}: {level} {yield_stage(rec, {**row, 'gate_passed': bool(level)})}",
              flush=True)  # fmt: skip


def _sentences(text: str) -> list[str]:
    """The benchmark text's sentences long enough to identify it (longest first)."""
    parts = re.split(r"(?<=[.!?:;])\s+|\n+", text)
    return sorted({p.strip() for p in parts if len(p.strip()) >= 40}, key=len, reverse=True)


def _redact(obj, sentences: list[str]):
    """Replace every quoted sentence of a benchmark text (also JSON-escaped) by a placeholder."""
    if isinstance(obj, dict):
        return {k: _redact(v, sentences) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v, sentences) for v in obj]
    if isinstance(obj, str):
        for sent in sentences:
            for form in (sent, json.dumps(sent, ensure_ascii=False)[1:-1]):
                if form in obj:
                    obj = obj.replace(form, "<benchmark text>")
    return obj


def scrub(_spec, _arg: str = "") -> None:
    """Models quote the problem (sub-agent requests, reasoning): redact it in every record."""
    sentences = [s for i in _sample() for s in _sentences(_texts()[i["question_sha256"]])]
    for path in sorted(OUT.glob("*/*.jsonl")) + sorted(OUT.glob("*.jsonl")):
        if path.parent.name == "logs":
            continue
        rows = [_redact(r, sentences) for r in _read(path)]
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                for r in rows), encoding="utf-8", newline="\n")  # fmt: skip
        print(f"{path.relative_to(OUT)}: {len(rows)} records", flush=True)


def codecheck(spec, _arg: str = "") -> None:
    """Validate the code level on the model-only check: 750 PuLP answers that were executed."""
    out = OUT / "codeform_modelonly.jsonl"
    done = {(r["model"], r["id"]) for r in _read(out)}
    for model in spec.models:
        for rec in _read(bc.OUT / "runs" / f"{model}.jsonl"):
            if (model, rec["id"]) in done:
                continue
            code = rec.get("code") or ""
            text = code if code.lstrip().startswith("```") else f"```python\n{code}\n```"
            res = read_code(text, bc.VENV_PYTHON, RUN_TIMEOUT_S) if code else {"stage": "no_code"}
            bc._append(out, {"model": model, "id": rec["id"], **res,
                             "executed": (rec.get("result") or {}).get("outcome"),
                             "objective": (rec.get("result") or {}).get("objective")})  # fmt: skip


def codeform(_spec, model_key: str) -> None:
    """The code level: read the model an answer's solver code builds (no language model)."""
    out = OUT / "codeform" / f"{model_key}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["run_id"] for r in _read(out)}
    for rec in _read(OUT / "runs" / f"{model_key}.jsonl"):
        if rec["run_id"] in done or rec.get("status") != "ok":
            continue
        res = read_code(rec["final_answer"], bc.VENV_PYTHON, RUN_TIMEOUT_S)
        bc._append(out, {"run_id": rec["run_id"], **res})
        print(f"{rec['run_id']}: {res['stage']}", flush=True)


def _execute(code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "model.py"
        script.write_text(code, encoding="utf-8", newline="\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
        try:
            proc = subprocess.run([str(bc.VENV_PYTHON), "-I", str(script)], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=RUN_TIMEOUT_S)  # fmt: skip
        except subprocess.TimeoutExpired:
            return {"outcome": "timeout", "objective": None}
    found = re.findall(r"STATUS=(\S+(?: \S+)?) OBJECTIVE=(\S+)", proc.stdout)
    err = proc.stderr
    if proc.returncode != 0:
        if "missing data" in err:
            outcome = "missing_data"
        elif "NotImplementedError" in err or any(p in err for p in NOT_EXPRESSIBLE):
            outcome = "not_expressible"
        else:
            outcome = "code_error"
    elif not found:
        outcome = "no_status"
    else:
        outcome = found[-1][0].lower().replace(" ", "_")
    return {"outcome": outcome, "objective": bc._num(found[-1][1]) if found else None,
            "stderr_tail": err[-800:]}  # fmt: skip


def translate(_spec, model_key: str) -> None:
    client = _client(
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", f"translator.{model_key}", 1500
    )
    out = OUT / "translations" / f"{model_key}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["run_id"] for r in _read(out) if r["final"]}
    for rec in _read(OUT / "runs" / f"{model_key}.jsonl"):
        answer = (rec.get("final_answer") or "").strip()
        if rec["run_id"] in done or rec.get("status") != "ok" or not answer:
            continue
        messages = [{"role": "system", "content": TRANSLATOR_SYSTEM},
                    {"role": "user", "content": CALL + answer}]  # fmt: skip
        for rnd in range(MAX_REPAIRS + 1):
            body = {"model": TRANSLATOR, "messages": list(messages), "temperature": 0.0,
                    "seed": SEED, "max_tokens": 16000, "provider": TRANSLATOR_PROVIDER,
                    "usage": {"include": True}}  # fmt: skip
            call = client.complete(body, describe=f"translator {rec['run_id']} round {rnd}")
            code = bc._code(call.content)
            result = _execute(code) if code else {"outcome": "no_code", "objective": None}
            final = result["outcome"] != "code_error" or rnd == MAX_REPAIRS
            record = call.to_record()
            record["request"].pop("messages", None)
            bc._append(out, {"run_id": rec["run_id"], "round": rnd, "final": final,
                             "translator_version": TRANSLATOR_VERSION,
                             "answer_sha256": _sha(answer), "code": code, "call": record,
                             "result": result})  # fmt: skip
            print(f"{rec['run_id']} round {rnd}: {result['outcome']} {result.get('objective')}",
                  flush=True)  # fmt: skip
            if final:
                break
            error = "\n".join((result.get("stderr_tail") or "").strip().splitlines()[-25:])
            messages += [{"role": "assistant", "content": call.content},
                         {"role": "user", "content": REPAIR + error}]  # fmt: skip


def main() -> int:
    steps = {"draw": draw, "generate": generate, "graph": graph, "translate": translate,
             "codeform": codeform, "codecheck": codecheck, "scrub": scrub}  # fmt: skip
    if len(sys.argv) < 2 or sys.argv[1] not in [*steps, "report"]:
        sys.exit(__doc__)
    spec = load_study(bc.STUDY)
    if sys.argv[1] == "report":
        import benchmark_workflows_report as rep

        rep.report(spec)
    elif sys.argv[1] == "draw":
        draw(spec)
    else:
        steps[sys.argv[1]](spec, sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
