"""Command line: ``python -m genstudy <command> --study studies/<id>/study.toml``.

Commands (all resumable; every request is logged with the body that was sent):

* ``plan``              the design: cells and an estimate of requests per model
* ``probe``             does the endpoint honour temperature and seed? (4 requests per model)
* ``run``               one model's block of the design, in a fixed shuffled order
* ``status``            progress and the workflow notes per model
* ``validate-grapher``  score a parsing model on the instrument cases
* ``validate-references``  parse the papers' own formulations, compare with their annotation
* ``grapher-report``    re-score both from the stored replies with the current parser
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
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from genstudy import instrument
from genstudy.config import GrapherSpec, StudySpec, load_study
from genstudy.graphing import Model, graph_answer, grapher_fingerprint, parse_reply
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


def endpoint(spec: StudySpec, model: str | None = None) -> tuple[str, str, str]:
    """(base URL, API-key variable, request-counter file name) for a model, or the study's.

    A model with its own endpoint gets its own daily counter, so another service's
    requests never use up the ScaDS budget, and two such models running side by side
    never share one cap.
    """
    m = spec.models.get(model) if model else None
    if m is not None and m.base_url:
        host = re.sub(r"[^A-Za-z0-9.-]+", "_", m.base_url.split("//", 1)[-1].split("/", 1)[0])
        return (
            m.base_url,
            m.api_key_env or spec.api_key_env,
            f"requests_per_day.{host}.{model}.json",
        )
    return spec.base_url, spec.api_key_env, "requests_per_day.json"


def _client(spec: StudySpec, model: str | None = None) -> ChatClient:
    base_url, key_env, counter = endpoint(spec, model)
    key = os.environ.get(key_env)
    if not key:
        sys.exit(f"{key_env} is not set (set -a; . ~/.config/raiLP/secrets.env; set +a)")
    return ChatClient(
        base_url,
        key,
        pacing=spec.pacing,
        counter_path=spec.root / "state" / counter,
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
    targets = [(k, m.served_id) for k, m in spec.models.items()]
    if spec.grapher:
        targets.append(("grapher", spec.grapher.served_id))
    if args.models:
        wanted = set(args.models.split(","))
        targets = [t for t in targets if t[0] in wanted]
    out = spec.root / "probe.jsonl"
    prompt = "Write one sentence about a train arriving at a station."
    for key, served in targets:
        client = _client(spec, key if key in spec.models else None)
        settings = dict(spec.models[key].extra) if key in spec.models else {}
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
                **settings,
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
        client=_client(spec, args.model),
        experiment=args.experiment,
        limit=args.limit,
        provenance=prov,
        log=_log,
        shard=_shard(args.shard),
    )
    _log(json.dumps(asdict(summary)))
    return 0 if summary.stopped is None or summary.stopped.startswith("limit") else 3


def _shard(text: str | None) -> tuple[int, int] | None:
    """``"2/4"`` (1-based, as typed) -> ``(1, 4)``."""
    if not text:
        return None
    k, n = (int(x) for x in text.split("/"))
    return k - 1, n


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
    """The study's grapher with the served model, mode or whitespace pattern overridden."""
    base = spec.grapher or (GrapherSpec(served_id=served_id) if served_id else None)
    if base is None:
        sys.exit("no [grapher] in the study spec and no --served-id given")
    return replace(
        base,
        served_id=served_id or base.served_id,
        mode=mode or base.mode,
        whitespace_pattern=ws if ws is not None else base.whitespace_pattern,
    )


def _config(grapher: GrapherSpec) -> str:
    """File stem of a grapher configuration's validation records."""
    ws = "-ws" if grapher.whitespace_pattern is not None else ""
    return f"{_slug(grapher.served_id)}.{grapher.mode}{ws}"


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_validate_grapher(spec: StudySpec, args: argparse.Namespace) -> int:
    grapher = _grapher(spec, args.served_id, args.mode, args.whitespace_pattern)
    client = _client(spec)
    out = spec.root / "instrument" / f"{_config(grapher)}.jsonl"
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
                    "repairs": list(res.repairs) if res else [],
                    "score": instrument.score(case.expected, predicted),
                    "call": res.call.to_record() if res else None,
                },
            )
            _log(f"{case.case_id} r{rep}: {instrument.score(case.expected, predicted)}")
    return 0


def cmd_grapher_report(spec: StudySpec, args: argparse.Namespace) -> int:
    """Score every validated grapher configuration from its stored replies (no requests).

    Replies are re-parsed with the current parser, so a change to the parsing
    step is evaluated on the identical replies.
    """
    expected = {c.case_id: c.expected for c in instrument.cases()}
    report: dict[str, Any] = {}
    for path in sorted((spec.root / "instrument").glob("*.jsonl")):
        totals: Counter[str] = Counter()
        n = 0
        tokens = 0
        for row in RunStore(path).records():
            if row.get("call") is None or row["case_id"] not in expected:
                continue
            n += 1
            tokens += int(row["call"]["response"]["usage"].get("completion_tokens") or 0)
            try:
                model = parse_reply(row["call"]["response"]["content"])
            except ValueError:
                totals["unparsed"] += 1
                continue
            for k, v in instrument.score(expected[row["case_id"]], graph_metrics(model)).items():
                totals[k] += int(bool(v))
        if not n:
            continue
        report[path.stem] = {
            "cases": n,
            "unparsed": totals["unparsed"],
            "mean_completion_tokens": round(tokens / n),
            **{k: round(totals[k] / n, 3) for k in ("accepted", *instrument.VERDICTS)},
            "counts_exact": round(
                sum(totals[k] for k in instrument.COUNTS) / (len(instrument.COUNTS) * n), 3
            ),
        }
        r = report[path.stem]
        _log(
            f"{path.stem:55s} n={n:3d} unparsed={r['unparsed']:3d} accepted={r['accepted']:.2f} "
            f"formulation={r['contains_formulation']:.2f} complete={r['complete_struct']:.2f} "
            f"coherent={r['coherent']:.2f} linear={r['linear']:.2f} counts={r['counts_exact']:.2f}"
        )
    out = spec.root / "instrument" / "report.json"
    out.write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    _reference_report(spec)
    return 0


def _reference_report(spec: StudySpec) -> None:
    """Score the stored replies on the reference formulations (``references/report.json``)."""
    truth = {
        p.stem: graph_metrics(Model.model_validate_json(p.read_text(encoding="utf-8")))
        for p in sorted((spec.root / "references").glob("P*.json"))
    }
    report: dict[str, Any] = {}
    for path in sorted((spec.root / "references").glob("validation.*.jsonl")):
        per_ref: dict[str, list[dict[str, Any]]] = {}
        for row in RunStore(path).records():
            if row.get("call") is None or row["reference"] not in truth:
                continue
            expected = truth[row["reference"]]
            repairs: list[str] = []
            try:
                got = graph_metrics(parse_reply(row["call"]["response"]["content"], repairs))
            except ValueError as exc:
                per_ref.setdefault(row["reference"], []).append({"error": str(exc)})
                continue
            score = instrument.score(expected, got)
            per_ref.setdefault(row["reference"], []).append(
                {
                    "score": score,
                    "repairs": repairs,
                    "edges": f"{got.n_edges}/{expected.n_edges}",
                    "variables": f"{got.n_variables}/{expected.n_variables}",
                    "constraints": f"{got.n_constraints}/{expected.n_constraints}",
                }
            )
        replies = [r for rs in per_ref.values() for r in rs]
        if not replies:
            continue
        parsed = [r for r in replies if "score" in r]
        right = sum(all(r["score"].values()) for r in parsed)
        config = path.stem.removeprefix("validation.")
        report[config] = {
            "replies": len(replies),
            "parsed": len(parsed),
            "all_verdicts_right": right,
            "per_reference": per_ref,
        }
        _log(
            f"references {config:45s} replies={len(replies):3d} parsed={len(parsed):3d} "
            f"all verdicts right={right:3d}"
        )
    out = spec.root / "references" / "report.json"
    out.write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def cmd_validate_references(spec: StudySpec, args: argparse.Namespace) -> int:
    """Parse each reference formulation and compare with its hand annotation.

    ``references/Pn.md`` is the formulation section of a paper, ``references/Pn.json``
    its annotated structure (the ground truth). The parser's result is compared on
    counts, structural verdicts and the number of variable-equation edges.
    """
    grapher = _grapher(spec, args.served_id, args.mode)
    client = _client(spec)
    out = spec.root / "references" / f"validation.{_config(grapher)}.jsonl"
    done = {(r["reference"], r["repeat"]) for r in RunStore(out).records()}
    for truth_path in sorted((spec.root / "references").glob("P*.json")):
        text_path = truth_path.with_suffix(".md")
        if not text_path.is_file():
            continue
        truth = Model.model_validate_json(truth_path.read_text(encoding="utf-8"))
        expected = graph_metrics(truth)
        for rep in range(args.repeats):
            if (truth_path.stem, rep) in done:
                continue
            try:
                res = graph_answer(
                    client, grapher, text_path.read_text(encoding="utf-8"), seed_offset=rep
                )
            except EndpointError as exc:
                if exc.transient:
                    _log(f"stopped: {exc}")
                    return 3
                raise
            predicted = graph_metrics(res.model) if res.model else None
            row = {
                "reference": truth_path.stem,
                "repeat": rep,
                "grapher": grapher.served_id,
                "grapher_mode": grapher.mode,
                "grapher_prompts": grapher_fingerprint(),
                "expected": asdict(expected),
                "predicted": asdict(predicted) if predicted else None,
                "parsed": res.model.model_dump() if res.model else None,
                "repairs": list(res.repairs),
                "error": res.error,
                "score": instrument.score(expected, predicted),
                "call": res.call.to_record(),
            }
            _append(out, row)
            if predicted:
                _log(
                    f"{truth_path.stem} r{rep}: objectives {predicted.n_objectives}/"
                    f"{expected.n_objectives}, variables {predicted.n_variables}/"
                    f"{expected.n_variables}, constraints {predicted.n_constraints}/"
                    f"{expected.n_constraints}, edges {predicted.n_edges}/{expected.n_edges}, "
                    f"verdicts {instrument.score(expected, predicted)}"
                )
            else:
                _log(f"{truth_path.stem} r{rep}: unparsed ({res.error})")
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
                    repairs=list(res.repairs),
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
    p.add_argument("--shard", help="k/n: run every n-th cell of the order, from position k")
    p.add_argument("--allow-dirty", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("validate-grapher")
    p.add_argument("--served-id")
    p.add_argument("--mode", choices=["schema", "prompt", "template"])
    p.add_argument("--whitespace-pattern")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--limit", type=int)
    sub.add_parser("grapher-report")
    p = sub.add_parser("validate-references")
    p.add_argument("--served-id")
    p.add_argument("--mode", choices=["schema", "prompt", "template"])
    p.add_argument("--repeats", type=int, default=2)
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
        "grapher-report": cmd_grapher_report,
        "validate-references": cmd_validate_references,
        "graph": cmd_graph,
    }
    return commands[args.cmd](spec, args)
