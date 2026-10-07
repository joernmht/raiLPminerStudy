"""The analysis plan's regressions, from analysis/summary.json (Paper 0, Section 5).

    ~/.venvs/genstudy-analysis/bin/python scripts/regression.py [studies/paper0_2026/study.toml]

Needs statsmodels and pandas (kept out of the harness's dependencies). Writes
``analysis/regression.json``, ``analysis/regression.md`` and
``analysis/regression_macros.tex``.

* **Yield (Experiment 1, anchor paper).** Logistic regression of a usable MILP
  (docs/adr/0005) on model, workflow, their interaction and temperature, all
  categorical. Each term is tested with a likelihood-ratio test (main effects in the
  additive model, the interaction against it). The same for the pre-registered
  acceptance. Parser failures are instrument errors and leave the sample.
* **Complexity (usable cores, Experiment 1).** Ordinary least squares of the logarithm
  of the minimal size, the logarithm of the constraint-variable ratio and the diameter
  on the same terms, with heteroskedasticity-robust (HC3) standard errors and robust
  Wald tests per term.
* **Input papers (Experiment 2 with the anchor paper's matching cell).** Logistic
  regression of a usable MILP on model and paper, Zero-Shot at temperature 0.6; the
  paper term is tested with a likelihood-ratio test.

Deterministic: the same records give the same files.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study

TERMS = ("model", "workflow", "model:workflow", "temperature")


def _logit(formula: str, df: pd.DataFrame):
    """Maximum likelihood; BFGS when Newton stops early. A cell with only successes (or
    only failures) has no finite coefficient, but the likelihood still has a finite
    supremum, so likelihood-ratio tests stay valid (the cell is listed in the output)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = smf.logit(formula, data=df).fit(disp=0, maxiter=200)
        if not res.mle_retvals["converged"]:
            res = smf.logit(formula, data=df).fit(disp=0, method="bfgs", maxiter=20000, gtol=1e-10)
    return res


def separated(df: pd.DataFrame, y: str) -> list[str]:
    cells = df.groupby(["model", "workflow"], observed=True)[y].agg(["sum", "count"])
    return [f"{m}x{w} {int(r['sum'])}/{int(r['count'])}" for (m, w), r in cells.iterrows()
            if r["sum"] in (0, r["count"])]  # fmt: skip


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def lr(full, reduced) -> dict[str, float]:
    chi2 = 2 * (full.llf - reduced.llf)
    df = round(full.df_model - reduced.df_model)
    return {"chi2": round(chi2, 2), "df": df, "p": float(stats.chi2.sf(chi2, df))}


def logit_terms(df: pd.DataFrame, y: str) -> dict:
    fit = lambda f: _logit(f"{y} ~ {f}", df)  # noqa: E731
    full = fit("C(model) * C(workflow) + C(temperature)")
    add = fit("C(model) + C(workflow) + C(temperature)")
    tests = {
        "model": lr(add, fit("C(workflow) + C(temperature)")),
        "workflow": lr(add, fit("C(model) + C(temperature)")),
        "model:workflow": lr(full, add),
        "temperature": lr(add, fit("C(model) + C(workflow)")),
    }
    params = add.params
    odds = {
        name: round(math.exp(params[name]), 2)
        for name in params.index
        if name.startswith(("C(workflow)", "C(temperature)"))
    }
    return {
        "n": int(full.nobs),
        "events": int(df[y].sum()),
        "pseudo_r2_full": round(full.prsquared, 3),
        "separated_cells": separated(df, y),
        "lr_tests": tests,
        "odds_ratios_additive": odds,
    }


def ols_terms(df: pd.DataFrame, y: str) -> dict:
    res = smf.ols(f"{y} ~ C(model) * C(workflow) + C(temperature)", data=df).fit(cov_type="HC3")
    wald = res.wald_test_terms(skip_single=False, scalar=True)
    table = wald.table
    tests = {}
    for term in TERMS:
        key = {
            "model": "C(model)",
            "workflow": "C(workflow)",
            "model:workflow": "C(model):C(workflow)",
            "temperature": "C(temperature)",
        }[term]
        row = table.loc[key]
        tests[term] = {
            "chi2": round(float(row["statistic"]), 2),
            "df": int(row["df_constraint"]),
            "p": float(row["pvalue"]),
        }
    return {"n": int(res.nobs), "r2": round(res.rsquared, 3), "wald_tests_hc3": tests}


def main() -> int:
    spec = load_study(sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml")
    out = spec.root / "analysis"
    rows = pd.DataFrame(json.loads((out / "summary.json").read_text(encoding="utf-8"))["rows"])
    rows = rows[~rows["stage"].isin(["unparsed", "request_error", "pending"])].copy()
    rows["usable"] = (rows["stage"] == "usable").astype(int)
    rows["accepted"] = (rows["outcome"] == "accepted").astype(int)
    rows["temperature"] = rows["temperature"].map(lambda t: f"{t:.1f}")
    rows["workflow"] = pd.Categorical(rows["workflow"], ["ZS", "CFC", "OE", "PS"])

    e1 = rows[rows["experiment"] == "exp1"]
    result = {
        "yield_exp1": logit_terms(e1, "usable"),
        "accepted_exp1": logit_terms(e1, "accepted"),
    }
    cores = e1[e1["stage"] == "usable"].copy()
    cores["log_size"] = np.log(cores["core_minimal_size"].astype(float))
    cores["log_cv"] = np.log(cores["core_cv_ratio"].astype(float))
    cores["diameter"] = cores["core_diameter"].astype(float)
    result["complexity_exp1"] = {
        y: ols_terms(cores.dropna(subset=[y]), y) for y in ("log_size", "log_cv", "diameter")
    }
    zs = rows[(rows["workflow"] == "ZS") & (rows["temperature"] == "0.6")]
    m_full = _logit("usable ~ C(model) + C(paper)", zs)
    m_red = _logit("usable ~ C(model)", zs)
    result["papers_zs06"] = {"n": int(m_full.nobs), "paper": lr(m_full, m_red)}

    (out / "regression.json").write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    lines = ["# Regressions (analysis plan, Paper 0 Section 5)", ""]
    for key in ("yield_exp1", "accepted_exp1"):
        r = result[key]
        lines += [f"## {key}: logistic, n = {r['n']}, events = {r['events']}, "
                  f"McFadden R2 (full) = {r['pseudo_r2_full']}, separated cells: "
                  f"{', '.join(r['separated_cells']) or 'none'}", "",
                  "| term | LR chi2 | df | p |", "|---|---|---|---|"]  # fmt: skip
        lines += [
            f"| {t} | {v['chi2']} | {v['df']} | {_p(v['p'])} |" for t, v in r["lr_tests"].items()
        ]
        lines += ["", "odds ratios (additive model): " + ", ".join(
            f"{k} {v}" for k, v in r["odds_ratios_additive"].items()), ""]  # fmt: skip
    for y, r in result["complexity_exp1"].items():
        lines += [f"## complexity {y}: OLS (HC3), n = {r['n']}, R2 = {r['r2']}", "",
                  "| term | Wald chi2 | df | p |", "|---|---|---|---|"]  # fmt: skip
        lines += [
            f"| {t} | {v['chi2']} | {v['df']} | {_p(v['p'])} |"
            for t, v in r["wald_tests_hc3"].items()
        ]
        lines.append("")
    pp = result["papers_zs06"]
    lines += [f"## input papers (ZS, T = 0.6): n = {pp['n']}, paper LR chi2 = "
              f"{pp['paper']['chi2']}, df = {pp['paper']['df']}, p = {_p(pp['paper']['p'])}", ""]  # fmt: skip
    (out / "regression.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    def mac(name: str, value: str) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}"

    def ptex(p: float) -> str:
        return "<0.001" if p < 0.001 else f"={p:.3f}"

    y = result["yield_exp1"]["lr_tests"]
    a = result["accepted_exp1"]["lr_tests"]
    macros = ["%% Generated by scripts/regression.py; do not edit."]
    for prefix, tests in (("regYield", y), ("regAccept", a)):
        for term, short in (("model", "Model"), ("workflow", "Workflow"),
                            ("model:workflow", "Interaction"), ("temperature", "Temperature")):  # fmt: skip
            t = tests[term]
            macros.append(
                mac(
                    f"{prefix}{short}",
                    f"$\\chi^2_{{{t['df']}}}={t['chi2']:.1f}$, $p{ptex(t['p'])}$",
                )
            )
    macros.append(mac("regYieldN", str(result["yield_exp1"]["n"])))
    macros.append(
        mac(
            "regPapers",
            f"$\\chi^2_{{{pp['paper']['df']}}}={pp['paper']['chi2']:.1f}$, $p{ptex(pp['paper']['p'])}$",
        )
    )
    for y_name, short in (("log_size", "Size"), ("log_cv", "Ratio"), ("diameter", "Diameter")):
        r = result["complexity_exp1"][y_name]
        macros.append(mac(f"regCx{short}RSq", f"{r['r2']:.2f}"))
        for term, tshort in (("model", "Model"), ("workflow", "Workflow"),
                             ("model:workflow", "Interaction"), ("temperature", "Temperature")):  # fmt: skip
            t = r["wald_tests_hc3"][term]
            macros.append(mac(f"regCx{short}{tshort}", f"$p{ptex(t['p'])}$"))
    (out / "regression_macros.tex").write_text(
        "\n".join(macros) + "\n", encoding="utf-8", newline="\n"
    )
    print((out / "regression.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
