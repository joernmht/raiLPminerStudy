"""The study specification: models, papers, experiments, pacing (one TOML file).

A study is fully described by ``studies/<id>/study.toml``. Nothing about the
design lives in code: which models run, which papers they read, which
workflows, temperatures and replicates make up each experiment, and how gently
the endpoint is used. The spec is loaded into frozen dataclasses and its
SHA-256 is stamped into every run record, so a record always names the design
that produced it.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKFLOWS: tuple[str, ...] = ("ZS", "CFC", "OE", "PS")


class SpecError(ValueError):
    """The study specification is incomplete or inconsistent."""


@dataclass(frozen=True)
class ModelSpec:
    """One generator model as the endpoint serves it."""

    key: str
    served_id: str
    family: str
    licence: str
    role: str
    max_tokens: int = 16000
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperSpec:
    """One input paper: its identity, licence and the input text the models read."""

    key: str
    doi: str
    title: str
    licence: str
    input_path: Path
    reference_path: Path | None = None

    def input_text(self) -> str:
        if not self.input_path.is_file():
            raise SpecError(f"paper {self.key}: input text missing at {self.input_path}")
        return self.input_path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class ExperimentSpec:
    """A factorial block: every combination is run ``replicates`` times."""

    name: str
    papers: tuple[str, ...]
    models: tuple[str, ...]
    workflows: tuple[str, ...]
    temperatures: tuple[float, ...]
    replicates: int


@dataclass(frozen=True)
class PacingSpec:
    """How gently the endpoint is used (ScaDS is a shared academic service)."""

    min_interval_s: float = 3.0
    max_requests_per_day: int = 1500
    request_timeout_s: float = 900.0
    max_tries: int = 6
    max_tool_rounds: int = 4
    max_subcalls: int = 10
    ps_count_min: int = 2
    ps_count_max: int = 5


@dataclass(frozen=True)
class GrapherSpec:
    """The model that turns a generated answer into a structure (validated separately)."""

    served_id: str
    temperature: float = 0.0
    seed: int = 7
    max_tokens: int = 8000


@dataclass(frozen=True)
class StudySpec:
    study_id: str
    root: Path
    base_url: str
    api_key_env: str
    seed: int
    models: Mapping[str, ModelSpec]
    papers: Mapping[str, PaperSpec]
    experiments: tuple[ExperimentSpec, ...]
    pacing: PacingSpec
    grapher: GrapherSpec | None
    sha256: str

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def experiment(self, name: str) -> ExperimentSpec:
        for exp in self.experiments:
            if exp.name == name:
                return exp
        raise SpecError(f"no experiment named {name!r}")


def load_study(path: str | Path) -> StudySpec:
    """Load and validate ``study.toml``; every inconsistency is a :class:`SpecError`."""
    path = Path(path)
    raw_bytes = path.read_bytes()
    raw = tomllib.loads(raw_bytes.decode("utf-8"))
    root = path.parent

    models = {
        key: ModelSpec(
            key=key,
            served_id=m["served_id"],
            family=m.get("family", ""),
            licence=m.get("licence", ""),
            role=m.get("role", ""),
            max_tokens=int(m.get("max_tokens", 16000)),
            extra=dict(m.get("extra", {})),
        )
        for key, m in raw.get("models", {}).items()
    }
    papers = {
        key: PaperSpec(
            key=key,
            doi=p["doi"],
            title=p.get("title", ""),
            licence=p["licence"],
            input_path=root / p["input"],
            reference_path=(root / p["reference"]) if p.get("reference") else None,
        )
        for key, p in raw.get("papers", {}).items()
    }
    experiments = tuple(
        ExperimentSpec(
            name=e["name"],
            papers=tuple(e["papers"]),
            models=tuple(e["models"]),
            workflows=tuple(e["workflows"]),
            temperatures=tuple(float(t) for t in e["temperatures"]),
            replicates=int(e["replicates"]),
        )
        for e in raw.get("experiments", [])
    )
    pacing = PacingSpec(**raw.get("pacing", {}))
    grapher = GrapherSpec(**raw["grapher"]) if "grapher" in raw else None

    spec = StudySpec(
        study_id=raw["study_id"],
        root=root,
        base_url=raw["base_url"].rstrip("/"),
        api_key_env=raw.get("api_key_env", "SCADS_API_KEY"),
        seed=int(raw["seed"]),
        models=models,
        papers=papers,
        experiments=experiments,
        pacing=pacing,
        grapher=grapher,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
    _validate(spec)
    return spec


def _validate(spec: StudySpec) -> None:
    names = [e.name for e in spec.experiments]
    if len(names) != len(set(names)):
        raise SpecError(f"duplicate experiment names: {names}")
    for exp in spec.experiments:
        for m in exp.models:
            if m not in spec.models:
                raise SpecError(f"{exp.name}: unknown model {m!r}")
        for p in exp.papers:
            if p not in spec.papers:
                raise SpecError(f"{exp.name}: unknown paper {p!r}")
        for w in exp.workflows:
            if w not in WORKFLOWS:
                raise SpecError(f"{exp.name}: unknown workflow {w!r}")
        if exp.replicates < 1:
            raise SpecError(f"{exp.name}: replicates must be >= 1")
        for t in exp.temperatures:
            if not 0.0 <= t <= 2.0:
                raise SpecError(f"{exp.name}: temperature {t} outside [0, 2]")
    if spec.pacing.ps_count_min < 2 or spec.pacing.ps_count_max < spec.pacing.ps_count_min:
        raise SpecError("pacing: need 2 <= ps_count_min <= ps_count_max")
