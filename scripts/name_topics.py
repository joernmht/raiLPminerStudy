"""Types of variables, constraints and objectives, found in their names (NMF topics).

    ~/.venvs/genstudy-analysis/bin/python scripts/name_topics.py [studies/paper0_2026/study.toml]

Every variable, constraint and objective of every usable MILP (its coherent core) and of
the input papers' own formulations is a short name. For each kind of element, the names
become TF-IDF vectors (words and word pairs, English stop words removed, words in fewer
than three names dropped, numbering such as "c2" or "1" removed) and a non-negative
matrix factorisation with a fixed number of topics groups them; each name belongs to its
strongest topic, names without a known word stay unassigned. A topic is described by its
top terms; the profile of a model is the set of topics among its elements (ADR-0006).

``topics(texts, k)`` is the reusable part: it works on any list of names (e.g. Paper 1's
corpus of published formulations). Deterministic (``init="nndsvd"``, no random start).
Writes ``analysis/topics.json``, ``analysis/topics.md`` and ``analysis/topics.png``.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study
from genstudy.graphing import Model, parse_reply
from genstudy.metrics import core_model
from genstudy.store import RunStore

#: Topics per kind of element, chosen so that topics are distinct railway or modelling
#: types (inspected for k = 8 ... 20 on the constraints; fixed before writing the paper).
K = {"constraint": 16, "variable": 12, "objective": 6}
#: Generic modelling words that would otherwise form topics of their own (a catch-all
#: "indicator" topic, objectives grouped by "minimize total" instead of by content).
GENERIC = {
    "constraint": set(),
    "variable": {"indicator", "variable", "variables", "decision", "binary", "actual",
                 "continuous", "integer", "auxiliary", "aux"},
    "objective": {"minimize", "minimise", "minimization", "minimisation", "min", "maximize",
                  "max", "total", "weighted", "sum", "objective", "obj", "function", "overall",
                  "combined", "integrated", "trsmp"},
}  # fmt: skip
_LABEL = re.compile(r"^\(\w+\)\s*(line \d+:)?\s*")
_NUMBERING = re.compile(r"\b(c\d+|\d+[a-z]?)\b")


def clean(name: str) -> str:
    """Equation labels, numbering and separators removed; lower case."""
    text = _LABEL.sub("", name).replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", _NUMBERING.sub(" ", text)).strip().lower()


def topics(texts: list[str], k: int, generic: set[str] = frozenset()) -> dict:
    """NMF topics of ``texts``: assignment per text (-1 = unassigned) and top terms per topic."""
    stop = sorted(ENGLISH_STOP_WORDS | set(generic))
    vec = TfidfVectorizer(token_pattern=r"[a-z]{3,}", stop_words=stop, ngram_range=(1, 2),
                          min_df=3, sublinear_tf=True)  # fmt: skip
    X = vec.fit_transform(texts)
    model = NMF(n_components=k, init="nndsvd", random_state=0, max_iter=800)
    W = model.fit_transform(X)
    H = model.components_
    terms = np.array(vec.get_feature_names_out())
    assign = W.argmax(axis=1)
    assign[W.max(axis=1) == 0] = -1
    return {
        "assign": assign.tolist(),
        "top_terms": [terms[np.argsort(-H[t])[:6]].tolist() for t in range(k)],
    }


def main() -> int:
    spec = load_study(sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml")
    out = spec.root / "analysis"
    rows = json.loads((out / "summary.json").read_text(encoding="utf-8"))["rows"]
    usable = {r["run_id"]: r for r in rows if r["stage"] == "usable"}
    elements: dict[str, list[tuple[str, str, str, str]]] = defaultdict(
        list
    )  # kind -> (owner, paper, llm, name)

    def add(owner: str, paper: str, llm: str, m: Model) -> None:
        for v in m.variablesInModel:
            elements["variable"].append((owner, paper, llm, clean(v.Name)))
        for e in m.constraints:
            elements["constraint"].append((owner, paper, llm, clean(e.Name)))
        for e in m.objective_functions:
            elements["objective"].append((owner, paper, llm, clean(e.Name)))

    for llm in spec.models:
        for g in RunStore(spec.root / "graphs" / f"{llm}.jsonl").records():
            r = usable.get(g["run_id"])
            if r is not None:
                add(
                    r["run_id"],
                    r["paper"],
                    llm,
                    core_model(parse_reply(g["call"]["response"]["content"])),
                )
    for path in sorted((spec.root / "references").glob("P*.json")):
        paper = re.match(r"P\d+", path.stem).group(0)
        add(
            f"ref:{paper}",
            paper,
            "reference",
            Model.model_validate_json(path.read_text(encoding="utf-8")),
        )

    result: dict = {}
    md = ["# Types of model elements (NMF topics over names)", ""]
    llms = list(spec.models)
    papers = sorted({p for kind in elements.values() for _, p, _, _ in kind})
    for kind, k in K.items():
        items = elements[kind]
        found = topics([name for *_, name in items], k, GENERIC[kind])
        assign = found["assign"]
        owners_with = defaultdict(set)  # topic -> owners that contain it
        for (owner, _, _, _), t in zip(items, assign, strict=True):
            if t >= 0:
                owners_with[t].add(owner)
        gen_owners = defaultdict(set)
        for owner, paper, llm, _ in items:
            if llm != "reference":
                gen_owners[("llm", llm)].add(owner)
                gen_owners[("paper", paper)].add(owner)
        table = []
        for t in sorted(range(k), key=lambda t: -sum(1 for a in assign if a == t)):
            names_t = [items[i][3] for i, a in enumerate(assign) if a == t]
            table.append({
                "topic": t,
                "n": len(names_t),
                "top_terms": found["top_terms"][t],
                "examples": [n for n, _ in Counter(names_t).most_common(4)],
                "references": sorted(p for p in papers if f"ref:{p}" in owners_with[t]),
                "share_by_llm": {m: round(len(owners_with[t] & gen_owners[("llm", m)]) / max(1, len(gen_owners[("llm", m)])), 3) for m in llms},
                "share_by_paper": {p: round(len(owners_with[t] & gen_owners[("paper", p)]) / max(1, len(gen_owners[("paper", p)])), 3) for p in papers},
            })  # fmt: skip
        unassigned = sum(1 for a in assign if a < 0)
        result[kind] = {"k": k, "elements": len(items), "unassigned": unassigned, "topics": table}
        md += [f"## {kind}s: {len(items)} names, k = {k}, unassigned {unassigned}", "",
               "| topic | names | top terms | examples | in references |", "|---|---|---|---|---|"]  # fmt: skip
        md += [f"| {r['topic']} | {r['n']} | {', '.join(r['top_terms'])} | {'; '.join(r['examples'])} | "
               f"{', '.join(r['references']) or '-'} |" for r in table]  # fmt: skip
        md.append("")
    (out / "topics.json").write_text(json.dumps(result, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                     encoding="utf-8", newline="\n")  # fmt: skip
    (out / "topics.md").write_text("\n".join(md), encoding="utf-8", newline="\n")

    # figure: constraint types x paper, share of generated models containing the type;
    # a frame marks the types present in the paper's own formulation
    cons = result["constraint"]["topics"]
    labels = [" / ".join(r["top_terms"][:2]) for r in cons]
    M = np.array([[r["share_by_paper"][p] for p in papers] for r in cons])
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(cons) + 1.6))
    ax.imshow(M, cmap="Greens", vmin=0, vmax=1, aspect="auto")
    for i, r in enumerate(cons):
        for j, p in enumerate(papers):
            ax.text(
                j,
                i,
                f"{100 * M[i, j]:.0f}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if M[i, j] > 0.6 else "black",
            )
            if p in r["references"]:
                ax.add_patch(
                    plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec="#c0392b", lw=1.6)
                )
    ax.set_xticks(range(len(papers)), papers)
    ax.set_yticks(range(len(cons)), labels, fontsize=8.5)
    ax.set_title("Constraint types in the usable MILPs (% of models per paper);\nframed: the type occurs in the paper's own formulation",
                 fontsize=10, loc="left")  # fmt: skip
    fig.tight_layout()
    fig.savefig(out / "topics.png", dpi=160)
    print((out / "topics.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
