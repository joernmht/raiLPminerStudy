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
from genstudy.config import load_study

GREY, LGREY, ORANGE, LORANGE, BLUE, GREEN, DGREEN, MAINC = (
    "#b9bec6", "#d9dce1", "#ef9a59", "#f6c79f", "#8fb3d9", "#4f8a3c", "#2f6b2f", "#4a6fa5",
)  # fmt: skip
# (check shown above the stream, stage a run leaves at, label of the exit, colour)
CHECKS = [
    ("answer\nnot empty", "empty_answer", "empty answer\n(reasoning cut off)", GREY),
    ("notation\ngate", "no_formulation", "no formulation\nin the answer", GREY),
    ("parser", "unparsed", "parser failure\n(instrument error)", LGREY),
    ("one\nobjective", "objective_count", "no objective\nor several", LORANGE),
    ("coherent core\nnot empty", "no_core", "objective linked\nto no constraint", ORANGE),
    ("linear", "nonlinear", "nonlinear as written\n(products, max, abs)", BLUE),
    ("integer\nvariables", "no_integer", "no integer\nvariable (LP)", BLUE),
]


def _load(spec_path: str) -> tuple[dict, Path, dict[str, str]]:
    spec = load_study(spec_path)
    out = spec.root / "analysis"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    names = {k: m.served_id.split("/")[-1] for k, m in spec.models.items()}
    return summary, out, names


def sankey(summary: dict, out: Path, names: dict[str, str]) -> Path:
    stages = Counter(summary["stages"])
    rows = summary["rows"]
    n = sum(v for k, v in stages.items() if k != "pending")
    extracted = sum(
        1
        for r in rows
        if r["stage"] in ("nonlinear", "no_integer", "usable") and r["coherent_whole"] is False
    )
    cut = sorted(
        r["cut_variables"]
        for r in rows
        if r["stage"] in ("nonlinear", "no_integer", "usable") and r["coherent_whole"] is False
    )
    accepted = sum(1 for r in rows if r["outcome"] == "accepted")
    fig = plt.figure(figsize=(12.5, 9.4))
    ax = fig.add_axes([0.02, 0.33, 0.96, 0.62])
    ax.set_xlim(-0.3, 10.6), ax.set_ylim(-0.5, 6.4), ax.axis("off")
    s, top = 2.6 / n, 5.2
    xs = [1.25 + 1.2 * i for i in range(len(CHECKS))]
    smooth = lambda t: 3 * t**2 - 2 * t**3  # noqa: E731
    ax.add_patch(plt.Rectangle((0.15, top - n * s), 0.18, n * s, color="#33415c"))
    ax.text(
        0.06,
        top - n * s / 2,
        f"{n:,}\nruns",
        ha="right",
        va="center",
        fontsize=10,
        fontweight="bold",
    )
    remaining, x_prev = n, 0.33
    for i, ((check, stage, why, col), x) in enumerate(zip(CHECKS, xs, strict=True)):
        lost = stages.get(stage, 0)
        ax.fill_between([x_prev, x], top, top - remaining * s, color=MAINC, alpha=0.85, lw=0)
        ax.text(x, top + 0.18, check, ha="center", va="bottom", fontsize=8.6, color="#33415c")
        ax.plot([x, x], [top + 0.12, top - remaining * s - 0.02], color="white", lw=1.2, alpha=0.9)
        if lost:
            y0_top, y0_bot = top - (remaining - lost) * s, top - remaining * s
            y1 = (0.55 if i % 2 == 0 else -0.15) + 0.75
            th = max(lost * s, 0.012)
            tt = np.linspace(0, 1, 60)
            ax.fill_between(x + 0.8 * tt, y0_bot + (y1 - y0_bot) * smooth(tt),
                            y0_top + (y1 + th - y0_top) * smooth(tt), color=col, alpha=0.95, lw=0)  # fmt: skip
            ax.add_patch(plt.Rectangle((x + 0.8, y1), 0.06, th, color=col))
            ax.text(x + 0.9, y1 + th / 2, f"{lost}  {why}", ha="left", va="center", fontsize=8.2)
        remaining -= lost
        x_prev = x
        if stage == "no_core" and extracted:
            ax.text((x + xs[i + 1]) / 2, top - remaining * s / 2,
                    f"{extracted} answers\nnot connected:\ncore kept,\nmedian {cut[len(cut) // 2]}\nvariable cut",
                    ha="center", va="center", fontsize=8, color="white", fontweight="bold")  # fmt: skip
    xe = xs[-1] + 1.0
    ax.fill_between([x_prev, xe], top, top - remaining * s, color=GREEN, alpha=0.95, lw=0)
    ax.add_patch(plt.Rectangle((xe, top - remaining * s), 0.18, remaining * s, color=DGREEN))
    ax.text(xe + 0.25, top - remaining * s / 2, f"{remaining}\nusable\nMILPs\n{100 * remaining / n:.0f}%",
            ha="left", va="center", fontsize=10, fontweight="bold", color=DGREEN)  # fmt: skip
    ax.text(5.1, 6.4, "From answer to usable MILP: every run leaves the stream at the first check it fails",
            ha="center", va="top", fontsize=12.5, fontweight="bold")  # fmt: skip
    pending = stages.get("pending", 0)
    sub = f"{n:,} runs with a result" + (f" ({pending} not yet graphed)" if pending else "")
    sub += f"; the rule fixed before the runs (complete and coherent) accepts {accepted} = {100 * accepted / n:.0f}%"
    ax.text(5.1, 6.12, sub, ha="center", va="top", fontsize=9.3, color="#55606e")
    bx = fig.add_axes([0.22, 0.06, 0.73, 0.2])
    cats = [("no answer / no formulation", ("empty_answer", "no_formulation"), GREY),
            ("parser failure", ("unparsed",), LGREY), ("objective count", ("objective_count",), LORANGE),
            ("empty core", ("no_core",), ORANGE), ("nonlinear / LP", ("nonlinear", "no_integer"), BLUE),
            ("usable MILP", ("usable",), GREEN)]  # fmt: skip
    # a model whose runs are mostly not graphed yet would show only its empty answers
    models = [
        m
        for m, st in summary["stages_by_model"].items()
        if st.get("pending", 0) <= sum(st.values()) / 2
    ]
    for row, model in enumerate(models):
        st = summary["stages_by_model"][model]
        total = sum(v for k, v in st.items() if k != "pending")
        left = 0.0
        for cname, keys, col in cats:
            v = 100 * sum(st.get(k, 0) for k in keys) / total if total else 0
            bx.barh(
                row,
                v,
                left=left,
                color=col,
                edgecolor="white",
                height=0.62,
                label=cname if row == 0 else None,
            )
            if v >= 6:
                bx.text(left + v / 2, row, f"{v:.0f}%", ha="center", va="center", fontsize=8.2,
                        color="white" if col == GREEN else "black")  # fmt: skip
            left += v
    labels = [
        names.get(m, m)
        + (" (partly graphed)" if summary["stages_by_model"][m].get("pending") else "")
        for m in models
    ]
    bx.set_yticks(range(len(models)), labels, fontsize=9.5)
    bx.invert_yaxis()
    bx.set_xlim(0, 100)
    bx.set_xlabel(
        "share of each model's runs with a result, by the check at which the run leaves", fontsize=9
    )
    bx.spines[["top", "right"]].set_visible(False)
    bx.legend(ncol=3, fontsize=8.2, frameon=False, loc="upper center", bbox_to_anchor=(0.45, 1.42))
    path = out / "yield_sankey.png"
    fig.savefig(path, dpi=150)
    fig.savefig(path.with_suffix(".pdf"), metadata={"CreationDate": None})  # byte-stable
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
            "empty answer (reasoning cut off\nat the token limit)",
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
