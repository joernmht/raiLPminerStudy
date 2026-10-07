"""One look for the figures of Paper 0: the paper's own font and the TU Dresden colours.

Text is typeset by pdflatex with the paper's font set-up (T1 Computer Modern, the sans-serif
family of the captions and headings), through matplotlib's pgf backend, so the figures carry
the paper's fonts (SFSS/SFSX) and not a look-alike. Each figure is drawn at the paper's text
width (OUP contemporary, one column: 526.4 pt = 7.28 in) and included at that width, so that
a size here is the size on the page. Colours are the TU Dresden brand palette (2025 corporate
design, as in the chair's slide master: Türkis, Brillantblau, mid blue, Dunkelblau, Orange,
Rot, Gelb for diagrams). PDFs are byte-stable (no dates, no trailer ID); the PNG next to each
PDF is a rendering of it for review.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
from matplotlib.colors import LinearSegmentedColormap

#: \textwidth of Main_v2.tex in inches (526.376 pt / 72.27).
WIDTH = 7.28
#: TU Dresden brand palette (hex as in the chair's master, tud-deck skill).
TUERKIS, LIGHTTUERKIS = "#0A777F", "#8CE6D7"
BRILLANTBLAU, MIDBLUE, LIGHTBLUE, DUNKELBLAU = "#00008C", "#2F57B2", "#97C6FF", "#001450"
ORANGE, ROT, GELB, VIOLETT = "#C85000", "#D20F41", "#FFC700", "#7369BE"
#: Neutral greys for what is not a result of a model (no answer, instrument errors).
GREY, MIDGREY, LIGHTGREY = "#5A5A5A", "#A6A6A6", "#D9D9D9"
#: Sequential maps from white over the light to the full brand colour and Dunkelblau.
BLUES = LinearSegmentedColormap.from_list("tud_blues", ["#FFFFFF", LIGHTBLUE, MIDBLUE, DUNKELBLAU])
TUERKISES = LinearSegmentedColormap.from_list(
    "tud_tuerkis", ["#FFFFFF", LIGHTTUERKIS, TUERKIS, DUNKELBLAU]
)
PREAMBLE = "\n".join([
    r"\usepackage[T1]{fontenc}",
    r"\usepackage[utf8]{inputenc}",
    r"\usepackage{anyfontsize}",
    r"\renewcommand{\familydefault}{\sfdefault}",
    r"\pdfinfoomitdate=1",
    r"\pdftrailerid{}",
])  # fmt: skip


def apply() -> None:
    """Set matplotlib's defaults for the paper's figures."""
    os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
    matplotlib.rcParams.update({
        "pgf.texsystem": "pdflatex",
        "pgf.rcfonts": False,
        "pgf.preamble": PREAMBLE,
        "font.family": "sans-serif",
        "font.size": 7.5,
        "axes.titlesize": 7.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 5,
        "axes.labelsize": 7.5,
        "axes.edgecolor": GREY,
        "axes.linewidth": 0.6,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "xtick.labelcolor": "black",
        "ytick.labelcolor": "black",
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "axes.unicode_minus": True,
    })  # fmt: skip


def save(fig, path: Path) -> None:
    """The PDF for the paper (typeset by pdflatex) and a PNG rendering of it for review."""
    import pymupdf

    pdf = path.with_suffix(".pdf")
    fig.savefig(pdf, backend="pgf")
    with pymupdf.open(pdf) as doc:
        doc[0].get_pixmap(dpi=200).save(path.with_suffix(".png"))
