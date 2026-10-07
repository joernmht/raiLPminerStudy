"""The yield of usable MILPs as a Sankey (with per-model shares) and as a flow diagram.

    python3 scripts/yield_figures.py [studies/paper0_2026/study.toml]

Reads ``analysis/summary.json`` (written by ``python -m genstudy analyze``) and writes
``analysis/yield_sankey.png`` and ``analysis/yield_flow.png``. Every run leaves the stream
at the first check it fails (``genstudy.analyze.STAGES``); answers that are not connected
are reduced to their coherent core instead of being rejected (docs/adr/0005).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import figstyle as fs  # scripts/figstyle.py: the paper's font, palette and width

from genstudy.config import load_study

fs.apply()

#: Model names as the paper writes them (its Table of models).
NAMES = {"glmflash": "GLM-5.3-Flash", "deepseek": "DeepSeek-V4.1-Flash",
         "gptoss": "gpt-oss-120b", "qwen": "Qwen3.8-27B", "minimax": "MiniMax-M3"}  # fmt: skip
# (check shown above the stream, stage a run leaves at, label of the exit, colour)
CHECKS = [
    ("answer\nnot empty", "empty_answer", "empty\nanswer", fs.MIDGREY),
    ("notation\ngate", "no_formulation", "no\nformulation", fs.MIDGREY),
    ("parser", "unparsed", "parser\nfailure", fs.LIGHTGREY),
    ("one\nobjective", "objective_count", "several\nobjectives", fs.GELB),
    ("coherent core\nnot empty", "no_core", "empty\ncore", fs.ORANGE),
    ("linear", "nonlinear", "nonlinear\n(products, abs)", fs.ROT),
    ("integer\nvariables", "no_integer", "no integer\nvariable", fs.ROT),
]


def _load(spec_path: str) -> tuple[dict, Path, dict[str, str]]:
    spec = load_study(spec_path)
    out = spec.root / "analysis"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    names = {k: NAMES.get(k, m.served_id.split("/")[-1]) for k, m in spec.models.items()}
    return summary, out, names


def sankey(summary: dict, out: Path, names: dict[str, str]) -> Path:
    """Panel A: the stream of runs through the checks; panel B: the same per model."""
    stages = Counter(summary["stages"])
    rows = summary["rows"]
    n = sum(v for k, v in stages.items() if k != "pending")
    kept = [r for r in rows if r["stage"] in ("nonlinear", "no_integer", "usable")
            and r["coherent_whole"] is False]  # fmt: skip
    cut = sorted(r["cut_variables"] for r in kept)
    fig = plt.figure(figsize=(fs.WIDTH, 4.45))
    ax = fig.add_axes([0.0, 0.37, 1.0, 0.6])
    ax.set_xlim(-0.55, 10.75), ax.set_ylim(-0.3, 6.0), ax.axis("off")
    s, top = 2.6 / n, 5.2
    xs = [1.25 + 1.2 * i for i in range(len(CHECKS))]
    smooth = lambda t: 3 * t**2 - 2 * t**3  # noqa: E731
    ax.add_patch(plt.Rectangle((0.15, top - n * s), 0.16, n * s, color=fs.DUNKELBLAU, lw=0))
    ax.text(0.05, top - n * s / 2, f"{n:,}\nruns", ha="right", va="center", fontsize=8,
            fontweight="bold")  # fmt: skip
    remaining, x_prev = n, 0.31
    for i, ((check, stage, why, col), x) in enumerate(zip(CHECKS, xs, strict=True)):
        lost = stages.get(stage, 0)
        ax.fill_between([x_prev, x], top, top - remaining * s, color=fs.MIDBLUE, alpha=0.9, lw=0)
        ax.text(x, top + 0.14, check, ha="center", va="bottom", fontsize=7, linespacing=1.15)
        ax.plot([x, x], [top + 0.08, top - remaining * s], color="white", lw=0.9)
        if lost:
            # every exit falls to the same level; its label stands under its end
            y0_top, y0_bot = top - (remaining - lost) * s, top - remaining * s
            y1, dx = 1.0, 0.55
            th = max(lost * s, 0.015)
            tt = np.linspace(0, 1, 60)
            ax.fill_between(x + dx * tt, y0_bot + (y1 - y0_bot) * smooth(tt),
                            y0_top + (y1 + th - y0_top) * smooth(tt), color=col, lw=0)  # fmt: skip
            ax.text(x + dx, y1 - 0.1, f"{lost}\n{why}", ha="center", va="top", fontsize=6.8,
                    linespacing=1.1)  # fmt: skip
        remaining -= lost
        x_prev = x
        if stage == "no_core" and kept:
            ax.text((x + xs[i + 1]) / 2, top - remaining * s / 2,
                    f"{len(kept)} answers\nnot connected:\ncore kept,\nmedian {cut[len(cut) // 2]}\nvariable cut",
                    ha="center", va="center", fontsize=6.8, color="white", fontweight="semibold",
                    linespacing=1.15)  # fmt: skip
    xe = xs[-1] + 1.0
    ax.fill_between([x_prev, xe], top, top - remaining * s, color=fs.TUERKIS, lw=0)
    ax.add_patch(plt.Rectangle((xe, top - remaining * s), 0.16, remaining * s, color=fs.DUNKELBLAU,
                               lw=0))  # fmt: skip
    ax.text(xe + 0.26, top - remaining * s / 2, f"{remaining}\nusable\nMILPs\n{100 * remaining / n:.0f}%",
            ha="left", va="center", fontsize=8, fontweight="bold", color=fs.TUERKIS)  # fmt: skip
    bx = fig.add_axes([0.175, 0.105, 0.8, 0.19])
    cats = [("no answer / no formulation", ("empty_answer", "no_formulation"), fs.MIDGREY),
            ("parser failure", ("unparsed",), fs.LIGHTGREY),
            ("objective count", ("objective_count",), fs.GELB),
            ("empty core", ("no_core",), fs.ORANGE),
            ("nonlinear / LP", ("nonlinear", "no_integer"), fs.ROT),
            ("usable MILP", ("usable",), fs.TUERKIS)]  # fmt: skip
    # a model whose runs are mostly not graphed yet would show only its empty answers
    models = [m for m, st in summary["stages_by_model"].items()
              if st.get("pending", 0) <= sum(st.values()) / 2]  # fmt: skip
    for row, model in enumerate(models):
        st = summary["stages_by_model"][model]
        total = sum(v for k, v in st.items() if k != "pending")
        left = 0.0
        for cname, keys, col in cats:
            v = 100 * sum(st.get(k, 0) for k in keys) / total if total else 0
            bx.barh(row, v, left=left, color=col, edgecolor="white", linewidth=0.5, height=0.66,
                    label=cname if row == 0 else None)  # fmt: skip
            if v >= 7:
                bx.text(left + v / 2, row, f"{v:.0f}%", ha="center", va="center", fontsize=6.5,
                        color="white" if col in (fs.TUERKIS, fs.ROT, fs.ORANGE) else "black")  # fmt: skip
            left += v
    labels = [names.get(m, m) + (" (partly graphed)" if summary["stages_by_model"][m].get("pending")
                                 else "") for m in models]  # fmt: skip
    bx.set_yticks(range(len(models)), labels)
    bx.invert_yaxis()
    bx.set_xlim(0, 100)
    bx.set_xlabel("share of the model's runs (%), by the check at which a run leaves")
    bx.spines[["top", "right"]].set_visible(False)
    bx.tick_params(axis="y", length=0)
    bx.legend(ncol=6, loc="lower center", bbox_to_anchor=(0.42, 1.02), handlelength=1.1,
              columnspacing=1.0, handletextpad=0.4, borderaxespad=0)  # fmt: skip
    fig.text(0.008, 0.985, "A  Every run leaves at the first check it fails", fontsize=7.5,
             fontweight="bold", va="top")  # fmt: skip
    fig.text(0.008, 0.345, "B  Per model", fontsize=7.5, fontweight="bold", va="top")
    path = out / "yield_sankey.png"
    fs.save(fig, path)
    return path


def flow(summary: dict, out: Path) -> Path:
    stages = Counter(summary["stages"])
    rows = summary["rows"]
    n = sum(v for k, v in stages.items() if k != "pending")
    extracted = sum(
        1
        for r in rows
        if r["stage"] in ("nonlinear", "no_integer", "usable") and r["coherent_whole"] is False
    )
    accepted = sum(1 for r in rows if r["outcome"] == "accepted")
    fig = plt.figure(figsize=(10.5, 9.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.axis("off")
    ax.text(
        0.5,
        0.985,
        "Yield of the generation pipeline",
        ha="center",
        va="top",
        fontsize=13,
        fontweight="bold",
    )
    ax.text(0.5, 0.957, f"{n:,} runs with a result; every run leaves at the first check it fails",
            ha="center", va="top", fontsize=9.3, color="#55606e")  # fmt: skip

    def box(x, y, w, h, text, fc, bold=False, fs=9.5):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.005,rounding_size=0.008",
                                    fc=fc, ec="#33415c", lw=1.0))  # fmt: skip
        ax.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=fs,
            fontweight="bold" if bold else "normal",
        )

    steps = [
        (f"{n:,} runs", None, None),
        (
            "non-empty answer",
            "empty_answer",
            "empty answer (mostly reasoning\ncut off at the token limit)",
        ),
        (
            "formulation in the answer",
            "no_formulation",
            "no formulation (notation gate,\nor the parser found none)",
        ),
        ("parsed into a graph", "unparsed", "parser failure (instrument error)"),
        ("exactly one objective function", "objective_count", "no objective or several"),
        ("coherent core", "no_core", "objective linked to no constraint"),
        ("linear core", "nonlinear", "nonlinear as written\n(products, max, absolute values)"),
        ("USABLE MILPs", "no_integer", "no integer variable (an LP)"),
    ]
    ys = [0.885 - i * 0.112 for i in range(len(steps))]
    xm, xe, w, h = 0.33, 0.775, 0.42, 0.065
    remaining = n
    for i, (label, stage, why) in enumerate(steps):
        if stage:
            lost = stages.get(stage, 0)
            remaining -= lost
            ax.annotate("", xy=(xm, ys[i] + h / 2), xytext=(xm, ys[i - 1] - h / 2),
                        arrowprops=dict(arrowstyle="-|>", lw=1.0, color="#33415c"))  # fmt: skip
            ymid = (ys[i - 1] + ys[i]) / 2
            ax.plot([xm, xe - 0.19], [ymid, ymid], color="#33415c", lw=0.8)
            box(
                xe,
                ymid,
                0.37,
                0.06,
                f"{lost}  {why}",
                "#eceff3" if stage == "unparsed" else "#fbe9e1",
                fs=8.6,
            )
        if i == 0:
            box(xm, ys[i], w, h, label, "#e8eef7", bold=True)
        elif label == "USABLE MILPs":
            box(xm, ys[i], w, h, f"USABLE MILPs: {remaining} ({100 * remaining / n:.0f}%)\nlinear, with integer variables",
                "#a9d18e", bold=True)  # fmt: skip
        elif label == "coherent core":
            box(
                xm,
                ys[i],
                w,
                h,
                f"coherent core: {remaining}\n({extracted} cut out of answers not connected)",
                "#e8eef7",
            )
        else:
            box(xm, ys[i], w, h, f"{label}: {remaining}", "#e8eef7")
    ax.text(0.5, 0.012, f"For comparison, the acceptance rule fixed before the runs (complete and coherent, every variable in "
                       f"at least two equations) accepts {accepted} = {100 * accepted / n:.0f}%.",
            ha="center", va="bottom", fontsize=8.8, color="#55606e")  # fmt: skip
    path = out / "yield_flow.png"
    fig.savefig(path, dpi=150)
    return path


def main() -> int:
    summary, out, names = _load(
        sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml"
    )
    print(sankey(summary, out, names))
    print(flow(summary, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
