"""Plan the design, then run it one model at a time, resumably.

The plan is the full factorial of every experiment in the spec. A cell's
``run_id`` names it completely (experiment, paper, model, workflow,
temperature, replicate), and its seed is a hash of the study seed and the
``run_id``, so a cell sends the same seeds however often it is attempted.

Runs execute **model by model** (the endpoint is a shared service; one model's
block finishes before the next starts). Within a model the cells are shuffled
with a fixed seed: in 2025 the runs were ordered by temperature label, so
drift, outages and restarts piled onto one factor (ADR-0001). A shuffled order
spreads them over all factors, and the order is reproducible.

Failure policy:

* a **transient** endpoint failure (overload, rate limit, network, the daily
  cap) stops the block *without* writing the run; resuming re-runs it;
* a **permanent** refusal (a non-retryable HTTP status) is written as a
  ``request_error`` record, because it is an answer about the request; three in
  a row stop the block, since that pattern means the request itself is wrong;
* whatever the model answers (empty, truncated, a refusal in prose) is a result
  and is written as such.
"""

from __future__ import annotations

import hashlib
import platform
import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genstudy import __version__, prompts
from genstudy.config import StudySpec
from genstudy.llm import ChatClient, EndpointError
from genstudy.store import RunStore
from genstudy.workflows import run_workflow

RECORD_SCHEMA = "genstudy.run/1"


@dataclass(frozen=True)
class RunCell:
    experiment: str
    paper: str
    model: str
    workflow: str
    temperature: float
    replicate: int

    @property
    def run_id(self) -> str:
        t = round(self.temperature * 10)
        return (
            f"{self.experiment}.{self.paper}.{self.model}.{self.workflow}"
            f".t{t:02d}.r{self.replicate:02d}"
        )


def plan(
    spec: StudySpec, *, model: str | None = None, experiment: str | None = None
) -> list[RunCell]:
    """Every cell of the design (optionally one model / one experiment), in a fixed order."""
    cells = [
        RunCell(exp.name, p, m, w, t, r)
        for exp in spec.experiments
        if experiment is None or exp.name == experiment
        for p in exp.papers
        for m in exp.models
        if model is None or m == model
        for w in exp.workflows
        for t in exp.temperatures
        for r in range(1, exp.replicates + 1)
    ]
    return sorted(cells, key=lambda c: c.run_id)


def schedule(spec: StudySpec, cells: list[RunCell], model: str) -> list[RunCell]:
    """The model's cells in a reproducible random order."""
    salt = int(hashlib.sha256(f"{spec.seed}:{model}".encode()).hexdigest()[:16], 16)
    out = sorted(cells, key=lambda c: c.run_id)
    random.Random(salt).shuffle(out)
    return out


def run_seed(spec: StudySpec, run_id: str) -> int:
    return int(hashlib.sha256(f"{spec.seed}:{run_id}".encode()).hexdigest()[:8], 16) % 2**31


def harness_provenance(repo: Path) -> dict[str, Any]:
    """The code that produces the records (ADR-0017): commit, dirty flag, versions."""

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {
        "genstudy": __version__,
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": platform.python_version(),
    }


def store_for(spec: StudySpec, model: str) -> RunStore:
    return RunStore(spec.runs_dir / f"{model}.jsonl")


@dataclass
class BlockSummary:
    model: str
    planned: int = 0
    already_done: int = 0
    written: int = 0
    request_errors: int = 0
    stopped: str | None = None


def execute(
    spec: StudySpec,
    *,
    model: str,
    client: ChatClient,
    experiment: str | None = None,
    limit: int | None = None,
    provenance: dict[str, Any] | None = None,
    log: Callable[[str], None] = print,
    wall: Callable[[], float] = time.time,
) -> BlockSummary:
    """Run the model's remaining cells; returns what happened."""
    if model not in spec.models:
        raise KeyError(f"unknown model {model!r}")
    mspec = spec.models[model]
    store = store_for(spec, model)
    done = store.done_ids()
    cells = schedule(spec, plan(spec, model=model, experiment=experiment), model)
    summary = BlockSummary(model=model, planned=len(cells))
    summary.already_done = sum(1 for c in cells if c.run_id in done)
    provenance = provenance or {}
    texts = {key: spec.papers[key].input_text() for key in {c.paper for c in cells}}
    consecutive_refusals = 0

    for cell in cells:
        if cell.run_id in done:
            continue
        if limit is not None and summary.written >= limit:
            summary.stopped = f"limit of {limit} runs reached"
            break
        seed = run_seed(spec, cell.run_id)
        started = wall()
        record: dict[str, Any] = {
            "schema": RECORD_SCHEMA,
            "run_id": cell.run_id,
            "study_id": spec.study_id,
            "spec_sha256": spec.sha256,
            "experiment": cell.experiment,
            "paper": cell.paper,
            "paper_doi": spec.papers[cell.paper].doi,
            "input_sha256": hashlib.sha256(texts[cell.paper].encode("utf-8")).hexdigest(),
            "model": model,
            "served_id": mspec.served_id,
            "workflow": cell.workflow,
            "temperature": cell.temperature,
            "replicate": cell.replicate,
            "seed": seed,
            "prompts": prompts.prompt_fingerprint(),
            "harness": provenance,
        }
        try:
            trace = run_workflow(
                cell.workflow,
                client=client,
                model=mspec,
                temperature=cell.temperature,
                seed=seed,
                paper_text=texts[cell.paper],
                pacing=spec.pacing,
            )
        except EndpointError as exc:
            if exc.transient:
                summary.stopped = f"transient endpoint failure: {exc}"
                log(f"[{model}] stopped at {cell.run_id}: {exc}")
                break
            consecutive_refusals += 1
            summary.request_errors += 1
            record.update(status="request_error", error=str(exc)[:500], calls=[])
            _stamp(record, started, wall())
            store.append(record)
            summary.written += 1
            log(f"[{model}] {cell.run_id}: request refused ({exc.status})")
            if consecutive_refusals >= 3:
                summary.stopped = "three refused requests in a row"
                break
            continue

        consecutive_refusals = 0
        record.update(
            status="ok",
            error=None,
            calls=trace.calls,
            tool_calls_requested=trace.tool_calls_requested,
            tool_calls_executed=trace.tool_calls_executed,
            subcalls=trace.subcalls,
            rounds=trace.rounds,
            notes=trace.notes,
            final_answer=trace.final_answer,
            final_finish_reason=trace.final_finish_reason,
        )
        _stamp(record, started, wall())
        store.append(record)
        summary.written += 1
        log(
            f"[{model}] {summary.already_done + summary.written}/{summary.planned} "
            f"{cell.run_id} ({len(trace.calls)} requests, {record['wall_s']:.0f} s)"
        )
    return summary


def _stamp(record: dict[str, Any], started: float, finished: float) -> None:
    record["started_utc"] = datetime.fromtimestamp(started, tz=UTC).isoformat()
    record["finished_utc"] = datetime.fromtimestamp(finished, tz=UTC).isoformat()
    record["wall_s"] = round(finished - started, 3)
