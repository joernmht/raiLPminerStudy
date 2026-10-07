"""Domain relevance, diversity and size of the usable MILPs, from the names in their graphs.

    ~/.venvs/genstudy-analysis/bin/python scripts/domain_vectors.py [studies/paper0_2026/study.toml]

Every usable MILP (its coherent core) and every input paper's own formulation becomes a
TF-IDF vector of the words in its variable, objective and constraint names
(``genstudy.domain.names``; lower-cased words of three or more letters, English stop
words removed, sublinear term frequency), docs/adr/0006. From the cosine similarities:

* **domain relevance**: the mean similarity of the models generated from each paper to
  each paper's own formulation, and the share of models whose most similar reference is
  their own paper's (chance: one in five);
* **diversity**: one minus the mean pairwise similarity of the models within a cell of
  Experiment 1 (one model, workflow and temperature, 15 replicates), and its dependence
  on temperature, workflow and model (OLS over the cells, HC3);
* **size**: variable and constraint families of the generated models against the
  paper's own formulation.

Needs scikit-learn, statsmodels and matplotlib (analysis environment). Writes
``analysis/domain.json``, ``analysis/domain_macros.tex`` and ``analysis/domain.png``.
Deterministic.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import figstyle as fs  # scripts/figstyle.py: the paper's font, palette and width

from genstudy.config import load_study
from genstudy.domain import names
from genstudy.graphing import Model, parse_reply
from genstudy.metrics import core_model, graph_metrics
from genstudy.store import RunStore

fs.apply()
AUTHORS = {"P1": "Shi", "P2": "Versluis", "P3": "Zhu", "P4": "Liu", "P5": "Lövétei"}
WORKFLOWS = ("ZS", "CFC", "OE", "PS")


def main() -> int:
    spec = load_study(sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml")
    out = spec.root / "analysis"
    rows = json.loads((out / "summary.json").read_text(encoding="utf-8"))["rows"]
    usable = {r["run_id"]: r for r in rows if r["stage"] == "usable"}

    meta, docs, sizes = [], [], defaultdict(list)
    for model in spec.models:
        for g in RunStore(spec.root / "graphs" / f"{model}.jsonl").records():
            r = usable.get(g["run_id"])
            if r is None:
                continue
            core = core_model(parse_reply(g["call"]["response"]["content"]))
            meta.append(r)
            docs.append(" ; ".join(names(core)))
            m = graph_metrics(core)
            sizes[r["paper"]].append((m.n_variables, m.n_constraints))
    order = np.argsort([r["run_id"] for r in meta], kind="stable")
    meta = [meta[i] for i in order]
    docs = [docs[i] for i in order]

    ref_names, ref_size = defaultdict(list), defaultdict(lambda: [0, 0])
    for path in sorted((spec.root / "references").glob("P*.json")):
        paper = re.match(r"P\d+", path.stem).group(0)
        model = Model.model_validate_json(path.read_text(encoding="utf-8"))
        ref_names[paper] += names(model)
        gm = graph_metrics(model)
        ref_size[paper][0] += gm.n_variables
        ref_size[paper][1] += gm.n_constraints
    papers = sorted(ref_names)

    vec = TfidfVectorizer(lowercase=True, token_pattern=r"[a-z]{3,}", stop_words="english",
                          sublinear_tf=True)  # fmt: skip
    X = vec.fit_transform(docs + [" ; ".join(ref_names[p]) for p in papers])
    G, R = X[: len(docs)], X[len(docs) :]
    S = cosine_similarity(G, R)
    own = np.array([papers.index(r["paper"]) for r in meta])
    nearest = S.argmax(axis=1)
    matrix = {
        p: {q: round(float(S[own == i, j].mean()), 3) for j, q in enumerate(papers)}
        for i, p in enumerate(papers)
    }
    nearest_own = {
        p: round(float((nearest[own == i] == i).mean()), 3) for i, p in enumerate(papers)
    }
    llm = np.array([r["model"] for r in meta])
    nearest_own_by_model = {
        m: round(float((nearest[llm == m] == own[llm == m]).mean()), 3) for m in spec.models
    }

    cells = defaultdict(list)
    for k, r in enumerate(meta):
        if r["experiment"] == "exp1":
            cells[(r["model"], r["workflow"], r["temperature"])].append(k)
    cell_rows = []
    for (model, wf, t), idx in sorted(cells.items()):
        if len(idx) < 3:
            continue
        sim = cosine_similarity(G[idx])
        iu = np.triu_indices(len(idx), 1)
        cell_rows.append({"model": model, "workflow": wf, "temperature": f"{t:.1f}",
                          "n": len(idx), "diversity": float(1 - sim[iu].mean())})  # fmt: skip
    cdf = pd.DataFrame(cell_rows)
    ols = smf.ols("diversity ~ C(temperature) + C(workflow) + C(model)", data=cdf).fit(
        cov_type="HC3"
    )
    wald = ols.wald_test_terms(skip_single=False, scalar=True).table
    by_t = cdf.groupby("temperature")["diversity"].mean().round(3).to_dict()
    by_wf = cdf.groupby("workflow")["diversity"].mean().round(3).to_dict()
    by_model = cdf.groupby("model")["diversity"].mean().round(3).to_dict()

    gen_v = [v for p in sizes for v, _ in sizes[p]]
    gen_c = [c for p in sizes for _, c in sizes[p]]
    as_large = sum(v >= ref_size[p][0] for p in sizes for v, _ in sizes[p])
    result = {
        "n_models": len(meta),
        "vocabulary": len(vec.vocabulary_),
        "similarity_generated_vs_reference": matrix,
        "nearest_reference_is_own": {
            "overall": round(float((nearest == own).mean()), 3),
            **nearest_own,
        },
        "nearest_reference_is_own_by_model": nearest_own_by_model,
        "diversity_cells": len(cdf),
        "diversity_by_temperature": by_t,
        "diversity_by_workflow": by_wf,
        "diversity_by_model": by_model,
        "diversity_wald_hc3": {
            term: {
                "chi2": round(float(wald.loc[f"C({term})", "statistic"]), 2),
                "df": int(wald.loc[f"C({term})", "df_constraint"]),
                "p": float(wald.loc[f"C({term})", "pvalue"]),
            }
            for term in ("temperature", "workflow", "model")
        },
        "size": {
            "generated_median_variables": median(gen_v),
            "generated_median_constraints": median(gen_c),
            "reference": {
                p: {"variables": v, "constraints": c} for p, (v, c) in sorted(ref_size.items())
            },
            "generated_at_least_reference_variables": as_large,
        },
    }
    (out / "domain.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")  # fmt: skip

    def mac(name: str, value: str) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}"

    def pct(x: float) -> str:
        return f"{100 * x:.0f}\\,\\%"

    def ptex(p: float) -> str:
        return "<0.001" if p < 0.001 else f"={p:.3f}"

    nr = result["nearest_reference_is_own"]
    rv = [ref_size[p][0] for p in papers]
    rc = [ref_size[p][1] for p in papers]
    dt = result["diversity_wald_hc3"]["temperature"]
    dm = result["diversity_wald_hc3"]["model"]
    dw = result["diversity_wald_hc3"]["workflow"]
    macros = [
        "%% Generated by scripts/domain_vectors.py; do not edit.",
        mac("domModels", str(len(meta))),
        mac("domNearestOwn", pct(nr["overall"])),
        mac("domNearestOwnMin", pct(min(v for k, v in nr.items() if k != "overall"))),
        mac("domNearestOwnMax", pct(max(v for k, v in nr.items() if k != "overall"))),
        mac("divTLow", f"{by_t['0.2']:.2f}"),
        mac("divTMid", f"{by_t['0.6']:.2f}"),
        mac("divTHigh", f"{by_t['1.0']:.2f}"),
        mac("divTempTest", f"$\\chi^2_{{{dt['df']}}}={dt['chi2']:.1f}$, $p{ptex(dt['p'])}$"),
        mac("divModelTest", f"$\\chi^2_{{{dm['df']}}}={dm['chi2']:.1f}$, $p{ptex(dm['p'])}$"),
        mac("divWorkflowTest", f"$\\chi^2_{{{dw['df']}}}={dw['chi2']:.1f}$, $p{ptex(dw['p'])}$"),
        mac("divCells", str(len(cdf))),
        mac("sizeGenVariables", f"{median(gen_v):g}"),
        mac("sizeGenConstraints", f"{median(gen_c):g}"),
        mac("sizeRefVariables", f"{min(rv)}--{max(rv)}"),
        mac("sizeRefConstraints", f"{min(rc)}--{max(rc)}"),
        mac("sizeAsLarge", str(as_large)),
    ]
    (out / "domain_macros.tex").write_text("\n".join(macros) + "\n", encoding="utf-8", newline="\n")

    fig, (a, b) = plt.subplots(1, 2, figsize=(fs.WIDTH, 2.75),
                               gridspec_kw={"width_ratios": [1.0, 1.0], "wspace": 0.42})  # fmt: skip
    M = np.array([[matrix[p][q] for q in papers] for p in papers])
    vmax = max(0.3, float(M.max()))
    im = a.imshow(M, cmap=fs.BLUES, vmin=0, vmax=vmax)
    labels = [AUTHORS.get(p, p) for p in papers]
    a.set_xticks(range(len(papers)), labels, rotation=30, ha="right")
    a.set_yticks(range(len(papers)), labels)
    a.tick_params(length=0)
    a.set_xlabel("published formulation of")
    a.set_ylabel("generated from")
    for i in range(len(papers)):
        for j in range(len(papers)):
            a.text(j, i, f"{M[i, j]:.2f}", ha="center", va="center", fontsize=6.8,
                   color="white" if M[i, j] > 0.45 * vmax else "black",
                   fontweight="bold" if i == j else "normal")  # fmt: skip
    a.set_title("A  Similarity of the names (mean cosine)")
    cb = fig.colorbar(im, ax=a, fraction=0.046, pad=0.03)
    cb.outline.set_linewidth(0.5)
    cb.ax.tick_params(labelsize=6.5, width=0.5, length=2)
    temps = ["0.2", "0.6", "1.0"]
    styles = {
        "ZS": (fs.MIDBLUE, "o"),
        "CFC": (fs.ORANGE, "s"),
        "OE": (fs.TUERKIS, "^"),
        "PS": (fs.VIOLETT, "D"),
    }
    for wf in WORKFLOWS:
        col, marker = styles[wf]
        sub = cdf[cdf["workflow"] == wf].groupby("temperature")["diversity"].mean()
        b.plot(temps, [sub.get(t, np.nan) for t in temps], marker=marker, ms=3.5, label=wf, lw=1.0,
               color=col)  # fmt: skip
    b.plot(temps, [by_t[t] for t in temps], color=fs.DUNKELBLAU, lw=2.0, label="mean")
    b.set_xlabel("temperature")
    b.set_ylabel("diversity (1 \N{MINUS SIGN} mean pairwise cosine)")
    b.spines[["top", "right"]].set_visible(False)
    b.legend(ncol=5, loc="upper left", handlelength=1.4, columnspacing=0.9, handletextpad=0.4)
    b.set_ylim(min(0.68, float(cdf.groupby(["workflow", "temperature"])["diversity"].mean().min()) - 0.01),
               max(0.84, float(cdf.groupby(["workflow", "temperature"])["diversity"].mean().max()) + 0.03))  # fmt: skip
    b.set_title("B  Diversity of the replicates of a cell")
    fig.subplots_adjust(left=0.1, right=0.98, top=0.9, bottom=0.2)
    fs.save(fig, out / "domain.png")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "similarity_generated_vs_reference"}, indent=1
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
