"""Report of scripts/benchmark_workflows.py: the validator against solved, scored answers.

Per run: the validator's stage at three levels (ADR-0010):

* ``gate``: Paper 0's instrument as frozen (notation gate, LP2Graph parser, structural checks;
  ``genstudy.analyze.yield_stage``);
* ``explicit``: an answer the gate turns away but that states an explicit formulation
  (``genstudy.codeform.explicit_formulation``) is parsed the same way;
* ``code``: an answer still without a written formulation whose solver code builds a model is
  read directly (``genstudy.codeform.read_code``).

The verdict is "accepted" when the stage is ``usable`` (Paper 0's definition). The pre-registered
benchmark rule (2026-11-07) also accepted ``no_integer``, since many benchmark problems are LPs;
it is reported too. Ground truth: the translator's solved objective against the original and
the cleaned label. Writes report.json, benchmark_macros.tex and tab_benchmark.tex (Paper 0).
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict

import benchmark_check as bc
import benchmark_workflows as bw

from genstudy.analyze import reparsed, yield_stage

PREREG = ("usable", "no_integer")
NO_WRITTEN = ("no_formulation", "unparsed")
WF_NAMES = {"ZS": "Zero-Shot", "CFC": "Code-First-Chain", "OE": "Operator-Expert",
            "PS": "Parallelization-Selection"}  # fmt: skip
#: Rows of the paper's table: (label, stages) in the order of the checks.
TABLE_ROWS = (
    ("Empty answer", ("empty_answer",)),
    ("No formulation found", ("no_formulation", "unparsed", "no_code", "other_library")),
    ("Code does not run", ("code_error",)),
    ("Nonlinear", ("nonlinear",)),
    ("Not one objective", ("objective_count",)),
    ("No constraints", ("no_core",)),
    ("No integer variables", ("no_integer",)),
    ("Usable", ("usable",)),
)


def _stages(rec: dict, g: dict | None, cf: dict | None) -> dict:
    """The stage of Paper 0's validator as frozen, and with the explicit and code levels."""
    frozen = yield_stage(rec, g)
    if g and g.get("level") == "explicit":
        written = yield_stage(rec, {**g, "gate_passed": True})
        level = "explicit"
    else:
        written, level = frozen, ("gate" if g and g.get("gate_passed") else None)
    full = written
    if written in NO_WRITTEN and cf and cf["stage"] != "no_code":
        full, level = cf["stage"], "code"
    return {"stage_frozen": frozen, "stage_written": written, "stage": full, "level": level}


def _rows(spec) -> list[dict]:
    sample = {i["id"]: i for i in bw._sample()}
    rows = []
    for model in spec.models:
        graphs = {g["run_id"]: g for g in bw._read(bw.OUT / "graphs" / f"{model}.jsonl")}
        codes = {c["run_id"]: c for c in bw._read(bw.OUT / "codeform" / f"{model}.jsonl")}
        trans = {t["run_id"]: t for t in bw._read(bw.OUT / "translations" / f"{model}.jsonl")
                 if t["final"]}  # fmt: skip
        for rec in bw._read(bw.OUT / "runs" / f"{model}.jsonl"):
            item = sample[rec["item"]]
            st = _stages(rec, graphs.get(rec["run_id"]), codes.get(rec["run_id"]))
            t = trans.get(rec["run_id"])
            outcome = t["result"]["outcome"] if t else ("no_answer" if st["stage"] in (
                "request_error", "empty_answer") else "pending")  # fmt: skip
            obj = t["result"].get("objective") if t and outcome == "optimal" else None
            rows.append({
                "run_id": rec["run_id"], "model": model, "workflow": rec["workflow"],
                "item": item["id"], "benchmark": item["benchmark"], "audit": item["audit"],
                **st, "code_pending": rec.get("status") == "ok" and rec["run_id"] not in codes,
                "accepted": st["stage"] == "usable",
                "accepted_frozen": st["stage_frozen"] == "usable",
                "accepted_prereg": st["stage_frozen"] in PREREG,
                "translation": outcome, "objective": obj,
                "ok_original": bc._match(obj, item["label_original"], bc.TOL),
                "ok_clean": (bc._match(obj, item["label_clean"], bc.TOL)
                             if item["label_clean"] is not None else None),
            })  # fmt: skip
    return rows


def _thousands(x: float) -> str:
    """An integer with the paper's thousands separator (1{,}200)."""
    return f"{x:,.0f}".replace(",", "{,}")


def _pct(k: float, n: float) -> str:
    return f"{100 * k / n:.0f}" if n else "--"


def _confusion(rows: list[dict], key: str) -> dict:
    """Precision and recall of a validator variant: accepted vs correct (cleaned label)."""
    acc = [r for r in rows if r[key]]
    rej = [r for r in rows if not r[key]]
    right = [r for r in rows if r["ok_clean"]]
    return {"accepted": len(acc), "accepted_correct": sum(r["ok_clean"] for r in acc),
            "rejected": len(rej), "rejected_correct": sum(r["ok_clean"] for r in rej),
            "correct": len(right), "correct_accepted": sum(r[key] for r in right)}  # fmt: skip


def report(spec) -> None:
    rows = _rows(spec)
    done = [r for r in rows if r["stage"] not in ("pending", "request_error")
            and r["translation"] != "pending" and not r["code_pending"]]  # fmt: skip
    clean = [r for r in done if r["ok_clean"] is not None]  # problems with a cleaned label
    summary: dict = {"n_runs": len(rows), "n_complete": len(done), "n_clean": len(clean)}
    summary["stages"] = dict(Counter(r["stage"] for r in done))
    summary["levels"] = dict(Counter(str(r["level"]) for r in done))
    summary["translations"] = dict(Counter(r["translation"] for r in done))
    summary["stage_x_correct"] = {
        f"{s}|{c}": n
        for (s, c), n in sorted(Counter((r["stage"], r["ok_clean"]) for r in clean).items())
    }
    summary["level_stage_x_correct"] = {
        f"{lv}|{s}|{c}": n
        for (lv, s, c), n in sorted(Counter((str(r["level"]), r["stage"], r["ok_clean"])
                                            for r in clean).items())
    }  # fmt: skip
    summary["validator"] = {k: _confusion(clean, k)
                            for k in ("accepted_frozen", "accepted_prereg", "accepted")}  # fmt: skip
    per = defaultdict(Counter)
    for r in done:
        for key in (("workflow", r["workflow"]), ("model", r["model"])):
            c = per[key]
            c["n"] += 1
            c["accepted"] += r["accepted"]
            c["accepted_frozen"] += r["accepted_frozen"]
            c["solved"] += r["translation"] == "optimal"
            c["missing_data"] += r["translation"] == "missing_data"
            c["ok_original"] += r["ok_original"]
            if r["ok_clean"] is not None:
                c["n_clean"] += 1
                c["ok_clean"] += r["ok_clean"]
                c["acc_n"] += r["accepted"]
                c["acc_ok"] += r["accepted"] and r["ok_clean"]
    summary["per_workflow"] = {k: dict(v) for (t, k), v in per.items() if t == "workflow"}
    summary["per_model"] = {k: dict(v) for (t, k), v in per.items() if t == "model"}
    bw._write_json(bw.OUT / "report.json", summary)
    _macros(summary, done, clean)
    print(json.dumps(summary, indent=1, sort_keys=True))


def _macros(summary: dict, done: list[dict], clean: list[dict]) -> None:
    n = len(done)
    items = Counter((i["benchmark"], i["audit"]) for i in bw._sample())
    m: dict[str, object] = {
        "bwProblems": len(bw._sample()), "bwRuns": n, "bwRunsClean": len(clean),
        "bwWorkflows": len(bw.WORKFLOWS), "bwModels": len({r["model"] for r in done}),
        "bwIORkept": items[("IndustryOR", "kept")], "bwIORremoved": items[("IndustryOR", "removed")],
        "bwNLkept": items[("NL4Opt", "kept")], "bwNLcorrected": items[("NL4Opt", "corrected")],
        "bwTolerance": f"10^{{{round(math.log10(bc.TOL))}}}",
        "bwSolved": _pct(sum(r["translation"] == "optimal" for r in done), n),
        "bwMissingDataN": sum(r["translation"] == "missing_data" for r in done),
        "bwMissingDataAcceptedN": sum(r["accepted"] for r in done if r["translation"] == "missing_data"),
        "bwOkClean": _pct(sum(r["ok_clean"] for r in clean), len(clean)),
        "bwOkOriginal": _pct(sum(r["ok_original"] for r in done), n),
    }  # fmt: skip
    # Levels: how many answers each level decides, and the gate's rejections it recovers.
    frozen_rej = [r for r in done if r["stage_frozen"] in NO_WRITTEN]
    m["bwGateRejectedN"] = len(frozen_rej)
    m["bwExplicitN"] = sum(r["level"] == "explicit" for r in done)
    m["bwCodeN"] = sum(r["level"] == "code" for r in done)
    m["bwEmptyN"] = sum(r["stage"] == "empty_answer" for r in done)
    m["bwEmptyMinimaxN"] = sum(
        r["stage"] == "empty_answer" and r["model"] == "minimax" for r in done
    )
    m["bwStillNoFormN"] = sum(r["stage"] in (*NO_WRITTEN, "no_code") for r in done)
    # The validator variants (truth: cleaned label).
    for key, tag in (
        ("accepted_frozen", "Frozen"),
        ("accepted_prereg", "Prereg"),
        ("accepted", "Full"),
    ):
        c = summary["validator"][key]
        m[f"bwAcc{tag}"] = _pct(c["accepted"], len(clean))
        m[f"bwPrec{tag}"] = _pct(c["accepted_correct"], c["accepted"])
        m[f"bwRejOk{tag}"] = _pct(c["rejected_correct"], c["rejected"])
        m[f"bwRecall{tag}"] = _pct(c["correct_accepted"], c["correct"])
    # Flags: answers with a model that a structural check stops (nonlinear .. no_integer).
    flags = [r for r in clean if r["stage"] in ("code_error", "nonlinear", "objective_count",
                                                "no_core", "no_integer")]  # fmt: skip
    m["bwFlaggedN"] = len(flags)
    m["bwFlaggedOkN"] = sum(r["ok_clean"] for r in flags)
    usable = [r for r in clean if r["stage"] == "usable"]
    m["bwUsableN"] = len(usable)
    m["bwUsableWrongN"] = sum(not r["ok_clean"] for r in usable)
    noint = [r for r in clean if r["stage"] == "no_integer"]
    m["bwNoIntN"], m["bwNoIntOkN"] = len(noint), sum(r["ok_clean"] for r in noint)
    struct = [r for r in flags if r["stage"] != "no_integer"]
    m["bwStructFlagN"], m["bwStructFlagOkN"] = len(struct), sum(r["ok_clean"] for r in struct)
    # Label sensitivity.
    ior = [r for r in done if r["benchmark"] == "IndustryOR"]
    m["bwIOROkOriginal"] = _pct(sum(r["ok_original"] for r in ior), len(ior))
    for audit, tag in (("kept", "Kept"), ("removed", "Removed")):
        g = [r for r in ior if r["audit"] == audit]
        m[f"bwIOROk{tag}"] = _pct(sum(r["ok_original"] for r in g), len(g))
    nlk = [r for r in done if r["benchmark"] == "NL4Opt" and r["audit"] == "kept"]
    m["bwNLkeptOk"] = _pct(sum(r["ok_original"] for r in nlk), len(nlk))
    nlc = [r for r in done if r["audit"] == "corrected"]
    m["bwNLcorrOkOriginal"] = _pct(sum(r["ok_original"] for r in nlc), len(nlc))
    m["bwNLcorrOkClean"] = _pct(sum(bool(r["ok_clean"]) for r in nlc), len(nlc))
    for wf, c in summary["per_workflow"].items():
        m[f"bwAcc{wf}"] = _pct(c["accepted"], c["n"])
        m[f"bwAccFrozen{wf}"] = _pct(c["accepted_frozen"], c["n"])
        m[f"bwOk{wf}"] = _pct(c.get("ok_clean", 0), c.get("n_clean", 0))
    oks = [100 * c["ok_clean"] / c["n_clean"] for c in summary["per_model"].values()
           if c.get("n_clean")]  # fmt: skip
    if oks:
        m["bwModelOkMin"], m["bwModelOkMax"] = f"{min(oks):.0f}", f"{max(oks):.0f}"
    m.update(_code_validation())
    m.update(_main_study_gate())
    m.update(_inputs_comparison(done))
    m.update(_leakage(done))
    lines = ["% Generated by raiLPminerStudy scripts/benchmark_workflows.py report; do not edit."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(m.items())]
    (bw.OUT / "benchmark_macros.tex").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                                 newline="\n")  # fmt: skip
    _table(clean)


def _table(clean: list[dict]) -> None:
    """Outcome by validator stage and level: how often answers there match the cleaned label."""
    # A level column (and a stage row) is shown only when it decides an answer.
    levels = tuple((k, lab) for k, lab in (("gate", "Gate"), ("explicit", "Explicit"), ("code", "Code"))
                   if k == "gate" or any(r["level"] == k for r in clean))  # fmt: skip
    head = " & ".join(f"\\multicolumn{{2}}{{c}}{{{lab}}}" for _k, lab in levels)
    rule = "".join(f"\\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(levels) + 1))
    table = ["\\begin{tabular}{l" + "rr" * (len(levels) + 1) + "}", "\\toprule",
             f"Validator stage & {head} & \\multicolumn{{2}}{{c}}{{All}} \\\\", rule,
             "& " + " & ".join(["$n$ & correct"] * (len(levels) + 1)) + " \\\\",
             "\\midrule"]  # fmt: skip
    for label, stages in TABLE_ROWS:
        cells = []
        for key, _lab in (*levels, (None, "All")):
            g = [r for r in clean if r["stage"] in stages and (key is None or r["level"] == key
                 or (key == "gate" and r["level"] is None))]  # fmt: skip
            if key is None and not g:
                break
            cells += [
                str(len(g)) if g else "",
                _pct(sum(r["ok_clean"] for r in g), len(g)) if g else "",
            ]
        if len(cells) == 2 * (len(levels) + 1):
            table.append(f"{label} & " + " & ".join(cells) + " \\\\")
    table += ["\\bottomrule", "\\end{tabular}"]
    (bw.OUT / "tab_benchmark.tex").write_text("\n".join(table) + "\n", encoding="utf-8",
                                              newline="\n")  # fmt: skip


def _code_validation() -> dict:
    """The code level on the model-only check (PuLP answers that were executed and scored)."""
    rows = bw._read(bw.OUT / "codeform_modelonly.jsonl")
    if not rows:
        return {}
    items = {i["id"]: i for i in bc._items()}
    code = [r for r in rows if r["stage"] != "no_code"]
    built = [r for r in code if r["stage"] != "code_error"]
    # Agreement with execution: the reader finds a model iff the script ran up to solve().
    ran = [r for r in code if r["executed"] not in ("code_error", "timeout")]
    agree = sum((r["stage"] != "code_error") == (r["executed"] not in ("code_error", "timeout"))
                for r in code)  # fmt: skip

    def ok(r: dict) -> bool:
        lab = items[r["id"]]["label_clean"]
        obj = r["objective"] if r["executed"] == "optimal" else None
        return bool(bc._match(obj, lab, bc.TOL))

    scored = [r for r in rows if items[r["id"]]["label_clean"] is not None]
    usable = [r for r in scored if r["stage"] == "usable"]
    noint = [r for r in scored if r["stage"] == "no_integer"]
    degenerate = [r for r in code if r["stage"] in ("objective_count", "no_core")]
    return {
        "bwCodeAnswers": len(rows), "bwCodeWithCode": len(code), "bwCodeBuilt": len(built),
        "bwCodeRan": len(ran), "bwCodeAgree": agree,
        "bwCodeUsableOk": _pct(sum(ok(r) for r in usable), len(usable)),
        "bwCodeNoIntOk": _pct(sum(ok(r) for r in noint), len(noint)),
        "bwCodeDegenerateN": len(degenerate),
        "bwCodeDegenerateSolvedN": sum(r["executed"] == "optimal" for r in degenerate),
    }  # fmt: skip


def _main_study_gate() -> dict:
    """How often the gate and the explicit level apply to the main study's railway answers."""
    from genstudy.codeform import explicit_formulation
    from genstudy.notation import notation

    root = bw.OUT.parent / "paper0_2026" / "runs"
    n = rej = expl = 0
    for path in sorted(root.glob("*.jsonl")):
        for rec in bw._read(path):
            ans = rec.get("final_answer") or ""
            if rec.get("status", "ok") != "ok" or not ans.strip():
                continue
            n += 1
            if not notation(ans).passed:
                rej += 1
                expl += explicit_formulation(ans)
    return {"bwMainAnswers": _thousands(n), "bwMainGateRejected": rej, "bwMainExplicit": expl}


# A stated optimum: an objective value computed in the answer. "global optimum" names a
# concept of the railway input papers and is excluded. Checked on samples (2026-11-12): every
# sampled benchmark match computes the optimum; on the paper answers the pattern matched only
# that concept, so it is reported for the benchmark alone, as a lower bound.
_SOLVED = re.compile(r"(?<!global )(optimal (?:objective )?(?:value|solution|profit|cost)|optimum"
                     r"|LP relaxation|by enumeration)[^.\n]{0,80}?\d", re.IGNORECASE)  # fmt: skip


def _words(text: str) -> int:
    return len(text.split())


def _frozen_rows(root, models, keep) -> list[dict]:
    """Runs of a study with the stage of Paper 0's validator as frozen (the analysis's reparse)."""
    out = []
    for model in models:
        graphs = {g["run_id"]: g for g in bw._read(root / "graphs" / f"{model}.jsonl")
                  if g.get("level") != "explicit"}  # fmt: skip
        for rec in bw._read(root / "runs" / f"{model}.jsonl"):
            if not keep(rec):
                continue
            g = reparsed(graphs.get(rec["run_id"]))
            if (
                g is None
                and rec.get("status", "ok") == "ok"
                and (rec.get("final_answer") or "").strip()
            ):
                g = {
                    "gate_passed": False
                }  # turned away by the gate, parsed only at the explicit level
            core = (g or {}).get("core") or {}
            out.append({"model": model, "workflow": rec["workflow"], "stage": yield_stage(rec, g),
                        "words": _words(rec.get("final_answer") or ""),
                        "gate": bool(g and g.get("gate_passed")),
                        "core_v": core.get("core_variables"), "core_c": core.get("core_constraints"),
                        "solved": bool(_SOLVED.search(rec.get("final_answer") or ""))})  # fmt: skip
    return out


MODEL_NAMES = {"glmflash": "GLM-5.3-Flash", "deepseek": "DeepSeek-V4.1-Flash",
               "gptoss": "gpt-oss-120b", "qwen": "Qwen3.8-27B", "minimax": "MiniMax-M3"}  # fmt: skip


def _inputs_comparison(done: list[dict]) -> dict:
    """The same validator, models, workflows and temperature on paper introductions and on
    benchmark problems: the main study's runs at temperature 0.6 against this check's runs."""
    models = list(MODEL_NAMES)
    papers = _frozen_rows(bw.OUT.parent / "paper0_2026", models,
                          lambda r: r.get("temperature") == bw.TEMPERATURE)  # fmt: skip
    bench = _frozen_rows(bw.OUT, models, lambda r: True)
    cols = {"Papers": papers, "Bench": bench}
    m: dict[str, object] = {}

    def answered(rows):
        return [r for r in rows if r["stage"] not in ("request_error", "empty_answer")]

    def core_rows(rows):
        return [r for r in rows if r["stage"] == "usable"]

    lines = []
    for tag, rows in cols.items():
        a = answered(rows)
        m[f"bcmp{tag}Runs"] = len(rows)
        m[f"bcmp{tag}Words"] = _thousands(statistics.median(r["words"] for r in a))
        m[f"bcmp{tag}Gate"] = _pct(sum(r["gate"] for r in a), len(a))
        for stage, name in (("nonlinear", "Nonlin"), ("no_integer", "NoInt"), ("usable", "Usable")):
            m[f"bcmp{tag}{name}"] = _pct(sum(r["stage"] == stage for r in rows), len(rows))
        cr = core_rows(rows)
        m[f"bcmp{tag}CoreV"] = f"{statistics.median(r['core_v'] for r in cr):.0f}"
        m[f"bcmp{tag}CoreC"] = f"{statistics.median(r['core_c'] for r in cr):.0f}"
        for wf in bw.WORKFLOWS:
            g = [r for r in rows if r["workflow"] == wf]
            m[f"bcmp{tag}Use{wf}"] = _pct(sum(r["stage"] == "usable" for r in g), len(g))
            m[f"bcmp{tag}NoForm{wf}"] = _pct(sum(r["stage"] == "no_formulation" for r in g), len(g))
        for model in models:
            g = [r for r in rows if r["model"] == model]
            m[f"bcmp{tag}Use{model}"] = _pct(sum(r["stage"] == "usable" for r in g), len(g))
    a = answered(bench)
    m["bcmpBenchSolved"] = _pct(sum(r["solved"] for r in a), len(a))

    def row(label: str, key: str, unit: str = "") -> str:
        return f"{label} & {m['bcmpPapers' + key]}{unit} & {m['bcmpBench' + key]}{unit} \\\\"

    lines = ["\\begin{tabular}{lrr}", "\\toprule",
             "& Paper introductions & Benchmark problems \\\\", "\\midrule",
             row("Runs", "Runs"), row("Answer length, median words", "Words"),
             row("Passes the notation gate", "Gate", "\\,\\%"),
             f"Core of a usable MILP, median variables & {m['bcmpPapersCoreV']} & {m['bcmpBenchCoreV']} \\\\",
             f"\\quad and constraints & {m['bcmpPapersCoreC']} & {m['bcmpBenchCoreC']} \\\\",
             row("Nonlinear", "Nonlin", "\\,\\%"), row("No integer variables", "NoInt", "\\,\\%"),
             row("Usable MILP (yield)", "Usable", "\\,\\%"),
             "\\midrule", "\\multicolumn{3}{l}{Yield by workflow} \\\\"]  # fmt: skip
    for wf in bw.WORKFLOWS:
        lines.append(row(f"\\quad {WF_NAMES[wf]}", f"Use{wf}", "\\,\\%"))
    lines += ["\\midrule", "\\multicolumn{3}{l}{Yield by model} \\\\"]
    for model in models:
        lines.append(row(f"\\quad {MODEL_NAMES[model]}", f"Use{model}", "\\,\\%"))
    lines += ["\\bottomrule", "\\end{tabular}"]
    (bw.OUT / "tab_benchmark_inputs.tex").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                                     newline="\n")  # fmt: skip
    return m


def _mentions(text: str, value: float | None) -> bool:
    """Does the answer write the number ``value`` (relative tolerance of the scoring)?"""
    if value is None or value == 0:
        return False
    for tok in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try:
            x = float(tok.replace(",", ""))
        except ValueError:
            continue
        if abs(x - value) <= bc.TOL * max(1.0, abs(value)):
            return True
    return False


def _leakage(done: list[dict]) -> dict:
    """Do answers reproduce labels the audit found wrong? A model can state a wrong label only by
    chance, by an alternative reading, or from memory; the matches are read by hand (ADR-0010)."""
    sample = {i["id"]: i for i in bw._sample()}
    answers = {}
    for model in MODEL_NAMES:
        for rec in bw._read(bw.OUT / "runs" / f"{model}.jsonl"):
            answers[rec["run_id"]] = rec.get("final_answer") or ""
    removed = [r for r in done if r["audit"] == "removed" and answers[r["run_id"]].strip()]
    corrected = [r for r in done if r["audit"] == "corrected" and answers[r["run_id"]].strip()]

    def says_original(r: dict) -> bool:
        return _mentions(answers[r["run_id"]], sample[r["item"]]["label_original"])

    return {
        "bwLeakRemovedN": len(removed),
        "bwLeakRemovedHits": sum(says_original(r) for r in removed),
        "bwLeakCorrN": len(corrected),
        # states the original label although its own model solves to another value
        "bwLeakCorrHits": sum(says_original(r) and not r["ok_original"] for r in corrected),
    }
