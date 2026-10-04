"""Command line: ``python -m genstudy <command> --study studies/<id>/study.toml``.

Commands (all resumable; every request is logged with the body that was sent):

* ``plan``              the design: cells and an estimate of requests per model
* ``probe``             does the endpoint honour temperature and seed? (4 requests per model)
* ``run``               one model's block of the design, in a fixed shuffled order
* ``status``            progress and the workflow notes per model
* ``validate-grapher``  score a parsing model on the instrument cases
* ``graph``             notation gate + parsing for one model's runs

The API key is read from the environment variable the spec names (default
``SCADS_API_KEY``); load it with ``set -a; . ~/.config/raiLP/secrets.env; set +a``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from genstudy import instrument
from genstudy.config import GrapherSpec, StudySpec, load_study
from genstudy.graphing import graph_answer, grapher_fingerprint
from genstudy.llm import ChatClient, EndpointError
from genstudy.metrics import graph_metrics
from genstudy.notation import notation
from genstudy.runner import execute, harness_provenance, plan, store_for
from genstudy.store import RunStore

REPO = Path(__file__).resolve().parent.parent

#: Requests per run, by workflow, for planning only (ZS 1; the others measured as
#: orchestrator turns plus sub-agent calls; PS assumes three factory instances).
_REQUESTS = {"ZS": 1, "CFC": 3, "OE": 5, "PS": 5}


def _log(msg: str) -> None:
    print(msg, flush=True)


def _client(spec: StudySpec) -> ChatClient:
    key = os.environ.get(spec.api_key_env)
    if not key:
        sys.exit(f"{spec.api_key_env} is not set (set -a; . ~/.config/raiLP/secrets.env; set +a)")
    return ChatClient(
        spec.base_url,
        key,
        pacing=spec.pacing,
        counter_path=spec.root / "state" / "requests_per_day.json",
        on_retry=lambda n, d, why: _log(f"  retry {n} in {d:.0f} s: {why}"),
    )


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", s)


def cmd_plan(spec: StudySpec, args: argparse.Namespace) -> int:
    total_runs = total_req = 0
    for model in spec.models:
        cells = plan(spec, model=model)
        req = sum(_REQUESTS[c.workflow] for c in cells)
        done = len(store_for(spec, model).done_ids() & {c.run_id for c in cells})
        _log(f"{model:10s} {len(cells):5d} runs  ~{req:5d} requests  done {done}")
        total_runs += len(cells)
        total_req += req
    _log(f"{'total':10s} {total_runs:5d} runs  ~{total_req:5d} requests")
    return 0


def cmd_probe(spec: StudySpec, args: argparse.Namespace) -> int:
    client = _client(spec)
    targets = [(k, m.served_id) for k, m in spec.models.items()]
    if spec.grapher:
        targets.append(("grapher", spec.grapher.served_id))
    if args.models:
        wanted = set(args.models.split(","))
        targets = [t for t in targets if t[0] in wanted]
    out = spec.root / "probe.jsonl"
    prompt = "Write one sentence about a train arriving at a station."
    for key, served in targets:
        bodies = [
            {"temperature": 0.0, "seed": 1},
            {"temperature": 0.0, "seed": 1},
            {"temperature": 1.0, "seed": 1},
            {"temperature": 1.0, "seed": 2},
        ]
        results = []
        for extra in bodies:
            body = {
                "model": served,
                "messages": [
                    {"role": "system", "content": "Answer with exactly one sentence."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 2048,
                **extra,
            }
            results.append(client.complete(body, describe=f"probe {key}"))
        texts = [r.content.strip() for r in results]
        verdict = {
            "model": key,
            "served_id": served,
            "same_at_t0_same_seed": texts[0] == texts[1],
            "t1_differs_from_t0": texts[2] != texts[0],
            "seed_changes_output_at_t1": texts[2] != texts[3],
            "calls": [r.to_record() for r in results],
        }
        with open(out, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(verdict, ensure_ascii=False, sort_keys=True) + "\n")
        _log(
            f"{key:10s} t0 repeat identical={verdict['same_at_t0_same_seed']}  "
            f"t1 differs from t0={verdict['t1_differs_from_t0']}  "
            f"seed changes t1 output={verdict['seed_changes_output_at_t1']}"
        )
    return 0


def cmd_run(spec: StudySpec, args: argparse.Namespace) -> int:
    prov = harness_provenance(REPO)
    if prov["git_dirty"] and not args.allow_dirty:
        sys.exit("the working tree has uncommitted changes; commit first (or --allow-dirty)")
    summary = execute(
        spec,
        model=args.model,
        client=_client(spec),
        experiment=args.experiment,
        limit=args.limit,
        provenance=prov,
        log=_log,
    )
    _log(json.dumps(asdict(summary)))
    return 0 if summary.stopped is None or summary.stopped.startswith("limit") else 3


def cmd_status(spec: StudySpec, args: argparse.Namespace) -> int:
    for model in spec.models:
        cells = {c.run_id for c in plan(spec, model=model)}
        records = [r for r in store_for(spec, model).records() if r["run_id"] in cells]
        notes: Counter[str] = Counter()
        for r in records:
            for n in r.get("notes", []):
                notes[re.sub(r"\d+", "#", n)] += 1
        errors = sum(1 for r in records if r.get("status") != "ok")
        _log(f"{model:10s} {len(records)}/{len(cells)} runs, {errors} request errors")
        for note, n in notes.most_common():
            _log(f"    {n:4d} x {note}")
    return 0


def _grapher(
    spec: StudySpec, served_id: str | None, mode: str | None = None, ws: str | None = None
) -> GrapherSpec:
    if served_id:
        base = spec.grapher or GrapherSpec(served_id=served_id)
        return GrapherSpec(
            served_id,
            base.temperature,
            base.seed,
            base.max_tokens,
            mode or base.mode,
            ws if ws is not None else base.whitespace_pattern,
        )
    if spec.grapher is None:
        sys.exit("no [grapher] in the study spec and no --served-id given")
    return spec.grapher


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_validate_grapher(spec: StudySpec, args: argparse.Namespace) -> int:
    grapher = _grapher(spec, args.served_id, args.mode, args.whitespace_pattern)
    client = _client(spec)
    config = f"{grapher.mode}{'-ws' if grapher.whitespace_pattern is not None else ''}"
    out = spec.root / "instrument" / f"{_slug(grapher.served_id)}.{config}.jsonl"
    done = {(r["case_id"], r["repeat"]) for r in RunStore(out).records()}
    cases = list(instrument.cases())[: args.limit] if args.limit else list(instrument.cases())
    for case in cases:
        for rep in range(args.repeats):
            if (case.case_id, rep) in done:
                continue
            error: str | None = None
            try:
                res = graph_answer(client, grapher, case.text, seed_offset=rep)
            except EndpointError as exc:
                if exc.transient:
                    _log(f"stopped: {exc}")
                    return 3
                res = None
                error = str(exc)[:300]
            predicted = graph_metrics(res.model) if res and res.model else None
            _append(
                out,
                {
                    "case_id": case.case_id,
                    "variant": case.variant,
                    "repeat": rep,
                    "grapher": grapher.served_id,
                    "grapher_mode": grapher.mode,
                    "grapher_whitespace_pattern": grapher.whitespace_pattern,
                    "grapher_prompts": grapher_fingerprint(),
                    "gate_passed": notation(case.text).passed,
                    "expected": asdict(case.expected),
                    "predicted": asdict(predicted) if predicted else None,
                    "parsed": res.model.model_dump() if res and res.model else None,
                    "error": (res.error if res else error),
                    "score": instrument.score(case.expected, predicted),
                    "call": res.call.to_record() if res else None,
                },
            )
            _log(f"{case.case_id} r{rep}: {instrument.score(case.expected, predicted)}")
    return 0


def cmd_graph(spec: StudySpec, args: argparse.Namespace) -> int:
    grapher = _grapher(spec, None)
    client = _client(spec)
    out = spec.root / "graphs" / f"{args.model}.jsonl"
    done = {r["run_id"] for r in RunStore(out).records()}
    for rec in store_for(spec, args.model).records():
        if rec["run_id"] in done or rec.get("status") != "ok":
            continue
        gate = notation(rec["final_answer"])
        row: dict[str, Any] = {
            "run_id": rec["run_id"],
            "notation_groups": list(gate.groups),
            "notation_coverage": gate.coverage,
            "gate_passed": gate.passed,
            "grapher": grapher.served_id,
            "grapher_prompts": grapher_fingerprint(),
        }
        if gate.passed:
            try:
                res = graph_answer(client, grapher, rec["final_answer"])
            except EndpointError as exc:
                if exc.transient:
                    _log(f"stopped: {exc}")
                    return 3
                row.update(error=str(exc)[:300], parsed=None, metrics=None, call=None)
            else:
                row.update(
                    error=res.error,
                    parsed=res.model.model_dump() if res.model else None,
                    metrics=asdict(graph_metrics(res.model)) if res.model else None,
                    call=res.call.to_record(),
                )
        else:
            row.update(error=None, parsed=None, metrics=None, call=None)
        _append(out, row)
        _log(f"{rec['run_id']}: gate={'pass' if gate.passed else 'fail'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="genstudy", description=__doc__.splitlines()[0])
    ap.add_argument("--study", default="studies/paper0_2026/study.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    p = sub.add_parser("probe")
    p.add_argument("--models", default="")
    p = sub.add_parser("run")
    p.add_argument("--model", required=True)
    p.add_argument("--experiment")
    p.add_argument("--limit", type=int)
    p.add_argument("--allow-dirty", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("validate-grapher")
    p.add_argument("--served-id")
    p.add_argument("--mode", choices=["schema", "prompt"])
    p.add_argument("--whitespace-pattern")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--limit", type=int)
    p = sub.add_parser("graph")
    p.add_argument("--model", required=True)
    args = ap.parse_args(argv)

    spec = load_study(args.study)
    commands = {
        "plan": cmd_plan,
        "probe": cmd_probe,
        "run": cmd_run,
        "status": cmd_status,
        "validate-grapher": cmd_validate_grapher,
        "graph": cmd_graph,
    }
    return commands[args.cmd](spec, args)
