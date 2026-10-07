"""Audit forms for a reMarkable tablet: the parser's verdicts against the printed answers.

    ~/.venvs/genstudy-analysis/bin/python scripts/audit_forms.py draw  [study.toml]
    ~/.venvs/genstudy-analysis/bin/python scripts/audit_forms.py build [study.toml] [batch ...]
    ~/.venvs/genstudy-analysis/bin/python scripts/audit_forms.py send  [study.toml] [batch ...]
    ~/.venvs/genstudy-analysis/bin/python scripts/audit_forms.py read  [study.toml]

The yield rests on the verdicts of the parser, an LLM, and the parser can be wrong in both
directions. It can call a usable MILP nonlinear (a false rejection; scripts/audit_nonlinear.py
audits these), and it can pass an answer that is not usable, miss variables or constraints,
or lose the link that connects a block of constraints to the objective (a false acceptance,
not audited before). One person labels a seeded random sample by hand, from the answers as
printed, without seeing the model, workflow, temperature or paper behind an answer:

* ``written``: 40 usable MILPs as written, ``warning``: 20 usable MILPs with a warning
  (ADR-0007). Is the answer a usable MILP (one objective function, linear, an integer
  variable, no detached block), and what do the parser's lists miss? For a warning: is the
  block that the core cut detached in the answer, or did the parser lose its link?
* ``nonlinear``: the 40 runs of the linearity audit, labelled again without the classes
  proposed there. Are the equations that the parser marked nonlinear nonlinear as printed,
  and of which kind (the classes of scripts/audit_nonlinear.py)?

``draw`` shuffles the 100 items into batches of 20 with blind codes (``audit/forms/key.json``;
it refuses to draw again). ``build`` writes one PDF per batch for the page of a reMarkable 2
(157 x 209 mm) through pandoc and LuaLaTeX: an instruction page, then per item the answer as
printed and a check page whose questions and boxes stand at the same place on every check
page; the position of every box goes to ``audit/forms/build/boxes.json``. An answer that
does not typeset is shown as its source. ``send`` puts the batches on the tablet with rmapi
(never overwriting); ``read`` fetches the annotated copies and decides every box by the ink
inside it (``audit/forms/marks.json``), and writes crops of the notes and of every doubtful
question for a look by eye (``audit/forms/returned/``). Deterministic except for the tablet.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study
from genstudy.graphing import parse_reply
from genstudy.metrics import core_model
from genstudy.store import RunStore

SEED = 2026
N_WRITTEN, N_WARNING = 40, 20
BATCH = 20
RMAPI = str(Path.home() / ".local" / "bin" / "rmapi")
REMOTE = "/Papers/Audit P0"
#: Inner side of a box (mm), the share of its inner area that new ink must cover to count
#: as a tick, and the share below which it counts as empty (in between: doubtful).
BOX_MM, TICK, EMPTY = 4.6, 0.04, 0.01
#: Any new ink in the note field counts as a note (a short word covers little of it).
NOTE_INK = 0.002
NOTE_MM = (140.0, 13.0)
SP_PER_BP = 65781.76
MM = 72 / 25.4

KINDS = [
    ("binary", r"bin\,×\,var"),
    ("logic", "if-then"),
    ("piecewise", r"\textbar{}·\textbar{}, max, min"),
    ("continuous", r"cont\,×\,cont, ÷, power"),
]
YESNO = [("yes", "yes"), ("no", "no")]
MISS = [("none", "none"), ("few", "1–2"), ("more", "more")]
#: (key, question, options, strata); an option is (value, label). One stratum's questions
#: always stand in the same order, so its boxes stand at the same place on every page.
QUESTIONS = [
    ("obj", "Exactly one objective function", YESNO, {"written", "warning"}),
    ("lin", "Every equation linear in the decision variables, as printed", YESNO,
     {"written", "warning"}),
    ("kind", "If not linear: the kind (tick all that apply)", [*KINDS, ("other", "other")],
     {"written", "warning"}),
    ("int", "At least one binary or integer decision variable", YESNO, {"written", "warning"}),
    ("conn", "No block of constraints detached from the variables of the objective", YESNO,
     {"written"}),
    ("cut", "The constraints marked CUT are, in the answer,",
     [("detached", "detached in the answer"), ("linked", "linked in the answer")],
     {"warning"}),
    ("varmiss", "Decision variables of the answer missing from the parser's list", MISS,
     {"written", "warning"}),
    ("conmiss", "Constraints (written as math) missing from the parser's list", MISS,
     {"written", "warning"}),
    ("nl", "The equations marked NONLINEAR are, as printed,",
     [("linear", "linear (a parser error)"), ("nonlinear", "nonlinear")], {"nonlinear"}),
    ("kind", "If nonlinear: the kind (tick all that apply)", KINDS, {"nonlinear"}),
    ("unsure", "Unsure about this item", [("yes", "unsure")],
     {"written", "warning", "nonlinear"}),
]  # fmt: skip
#: Questions with more than one tick allowed.
MULTI = {"kind"}
LETTER = {"written": "U", "warning": "U", "nonlinear": "N"}
DOMAIN = {"binary": "bin", "integer": "int", "continuous": "cont", "unknown": "?"}
TEX = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
       "^": r"\textasciicircum{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}"}  # fmt: skip

PREAMBLE = r"""\documentclass[9pt]{extarticle}
\usepackage[paperwidth=157mm,paperheight=209mm,left=7mm,right=7mm,top=12mm,bottom=8mm,
  headheight=5mm,headsep=3mm]{geometry}
\usepackage{amsmath,mathtools}
\usepackage{fontspec}
\directlua{luaotfload.add_fallback("fb", {"latinmodern-math.otf:mode=node;", "FreeSerif.otf:mode=node;"})}
\setmainfont{lmroman10-regular.otf}[RawFeature={fallback=fb}, BoldFont=lmroman10-bold.otf,
  ItalicFont=lmroman10-italic.otf, BoldItalicFont=lmroman10-bolditalic.otf]
\setsansfont{lmsans10-regular.otf}[RawFeature={fallback=fb}, BoldFont=lmsans10-bold.otf]
\setmonofont{lmmono10-regular.otf}[RawFeature={fallback=fb}]
\usepackage{unicode-math}
\setmathfont{latinmodern-math.otf}
\usepackage{longtable,booktabs,array,calc,xcolor,fancyhdr,fvextra}
\usepackage[hidelinks]{hyperref}
\newcounter{none}
\usepackage{newunicodechar}
SUBSCRIPTS\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\providecommand{\bm}[1]{\symbf{#1}}
\providecommand{\R}{\mathbb{R}}\providecommand{\N}{\mathbb{N}}\providecommand{\Z}{\mathbb{Z}}
\providecommand{\mathds}[1]{\mathbb{#1}}\providecommand{\mathbbm}[1]{\mathbb{#1}}
\providecommand{\argmin}{\operatorname*{arg\,min}}\providecommand{\argmax}{\operatorname*{arg\,max}}
\providecommand{\cancel}[1]{#1}\providecommand{\st}[1]{#1}
\setlength{\parindent}{0pt}\setlength{\parskip}{2.5pt plus 1pt}
\setcounter{secnumdepth}{0}
\makeatletter
\renewcommand\section{\@startsection{section}{1}{\z@}{1.6ex plus .4ex}{.6ex}{\normalfont\large\bfseries}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}{1.3ex plus .3ex}{.4ex}{\normalfont\normalsize\bfseries}}
\renewcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}{1ex plus .2ex}{.3ex}{\normalfont\normalsize\bfseries\itshape}}
\makeatother
\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines,breakanywhere,fontsize=\scriptsize}
\newwrite\boxfile\immediate\openout\boxfile=\jobname.pos
\newcommand{\mk}[1]{\savepos\write\boxfile{#1 \thepage\space\the\lastxpos\space\the\lastypos}}
\newlength{\cbs}\setlength{\cbs}{BOXMMmm}
\newcommand{\cb}[1]{\raisebox{-1.1mm}{\setlength{\fboxsep}{0pt}\mk{#1}\fbox{\rule{0pt}{\cbs}\rule{\cbs}{0pt}}}}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0.3pt}
""".replace("BOXMM", f"{BOX_MM}").replace(
    # subscript letters that no font here has: typeset as subscripts
    "SUBSCRIPTS",
    "".join(
        rf"\newunicodechar{{{c}}}{{\textsubscript{{{t}}}}}"
        for c, t in zip("ₐₑₒₓₕₖₗₘₙₚₛₜ", "aeoxhklmnpst", strict=True)
    )
    + "\n",
)

INSTRUCTIONS = r"""\fancyhead[L]{\small\sffamily Paper 0 audit}\fancyhead[R]{\small\sffamily batch BATCH of NBATCH}
\begin{document}
{\sffamily\bfseries\Large Paper 0 audit, batch BATCH of NBATCH}\par
{\sffamily items FIRST to LAST}\par\bigskip
\textbf{What this is.} The study's parser, an LLM, turned every answer into a list of variables
and equations, and the yield rests on its verdicts. This batch checks those verdicts against
the answers as printed. You see neither the model nor the workflow, temperature or paper
behind an answer.

\textbf{For each item} read the answer (one to four pages), then fill in the check page that
follows it. The questions stand at the same place on every check page. Tick with one clear
stroke inside a box; an empty box counts as not ticked. To change an answer, fill the wrong
box completely and write the right answer in the note field. The note field is optional. About
two to three minutes per item.

\textbf{U items:} the parser says the answer is a usable MILP. Check whether it is: exactly one
objective function, every equation linear in the decision variables (a parameter times a
variable is linear), at least one binary or integer variable, and no block of constraints that
shares no variable with the part that reaches the objective. Then say what the parser's lists
miss. Some U items show constraints marked CUT: the parser found them not connected to the
objective; say whether they are detached in the answer too.

\textbf{N items} start with the check page: the parser marked equations NONLINEAR, and the
check page names them. Find them in the answer that follows, and say whether they are
nonlinear as printed, and of which kind. You need not read the rest of the answer.

\textbf{Kinds of nonlinearity.} \emph{bin × var}: a product in which every factor but one is a
binary or integer variable. \emph{if-then}: an indicator, implication or case distinction on
variables, written as such. \emph{|·|, max, min}: an absolute value, maximum, minimum or
positive part of an expression in the variables. \emph{cont × cont, ÷, power}: a product,
quotient or power of continuous variables, or a continuous variable inside a nonlinear
function. \emph{other}: anything else (say what in the note).

\textbf{The parser's lists} on each check page give its numbers and names, a mark for each
equation it read as linear (✓) or not (\textbf{×}), and the symbols of the variables it linked to it.
Its symbols and equations are typeset as the parser wrote them; one that cannot be typeset
is shown as written, in typewriter type. A formula of an answer that does not typeset is shown
as written too, marked [as written].
\end{document}
"""


#: JSON escapes that the parser wrote for LaTeX commands (``\\beta`` became a backspace and
#: "eta"); shown as the command again.
CTRL = str.maketrans({"\b": "\\b", "\f": "\\f", "\t": "\\t", "\r": "\\r", "\n": "\\n"})


def esc(s: str) -> str:
    s = re.sub(r"[\x00-\x1f]", "", str(s).translate(CTRL))
    return "".join(TEX.get(c, c) for c in s)


def load(root: Path, models: list[str]) -> tuple[list[dict], dict, dict]:
    rows = json.loads((root / "analysis" / "summary.json").read_text(encoding="utf-8"))["rows"]
    graphs, runs = {}, {}
    for m in models:
        for g in RunStore(root / "graphs" / f"{m}.jsonl").records():
            graphs[g["run_id"]] = g
        for r in RunStore(root / "runs" / f"{m}.jsonl").records():
            runs[r["run_id"]] = r
    return rows, graphs, runs


def draw(root: Path, rows: list[dict]) -> None:
    path = root / "audit" / "forms" / "key.json"
    if path.is_file():
        print(f"{path} exists: the sample is drawn once (delete the file to draw again)")
        return
    usable = [r for r in rows if r["stage"] == "usable"]
    written = sorted(r["run_id"] for r in usable if not r["cut_constraints"])
    warned = sorted(r["run_id"] for r in usable if r["cut_constraints"])
    labels = json.loads((root / "audit" / "nonlinear_labels.json").read_text(encoding="utf-8"))
    nonlinear = sorted(labels["runs"])
    rng = random.Random(SEED)
    items = (
        [("written", r) for r in rng.sample(written, N_WRITTEN)]
        + [("warning", r) for r in rng.sample(warned, N_WARNING)]
        + [("nonlinear", r) for r in nonlinear]
    )
    rng.shuffle(items)
    key = {
        "seed": SEED,
        "drawn_from": {"written": len(written), "warning": len(warned),
                       "nonlinear": "the sample of audit/nonlinear_labels.json"},
        "items": {f"{i + 1:03d}": {"batch": i // BATCH + 1, "stratum": s, "run_id": r}
                  for i, (s, r) in enumerate(items)},
    }  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(key, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{path}: {len(items)} items in {(len(items) + BATCH - 1) // BATCH} batches")


#: A piece of an item's LaTeX: its text, and for a formula the text that replaces it when it
#: does not typeset (None for text, which is never replaced).
Chunk = tuple[str, str | None]

MATH = re.compile(
    r"\\\(|\\\[|\\begin\{(?:equation|align|gather|multline|eqnarray|flalign|alignat)\*?\}"
)


def as_written(latex: str, display: bool) -> str:
    """A formula of an answer that does not typeset, shown as written (with its line breaks
    when it stands on its own)."""
    text = "".join(TEX.get(c, c) for c in re.sub(r"\n\s*", "\n", latex.strip()))
    text = text.replace("\n", r"\newline " if display else " ")
    shown = r"{\small\ttfamily " + text + r"}\,{\color{gray}\scriptsize[as written]}"
    return "\\par\\noindent " + shown + "\\par " if display else shown


def answer_chunks(markdown: str) -> list[Chunk]:
    """The answer through pandoc, split into text and formulas (verbatim blocks stay text)."""
    import pypandoc

    latex = pypandoc.convert_text(
        markdown,
        "latex",
        format="markdown+tex_math_single_backslash",
        extra_args=["--syntax-highlighting=none", "--wrap=preserve"],
    )
    chunks: list[Chunk] = []
    for part in re.split(r"(\\begin\{verbatim\}.*?\\end\{verbatim\})", latex, flags=re.S):
        if part.startswith("\\begin{verbatim}"):
            chunks.append((part, None))
            continue
        i = 0
        while (m := MATH.search(part, i)) is not None:
            opening = m.group(0)
            closing = {"\\(": "\\)", "\\[": "\\]"}.get(opening, opening.replace("begin", "end"))
            end = part.find(closing, m.end())
            if end < 0:
                break
            end += len(closing)
            tables = part.count("\\begin{longtable}", 0, m.start())
            in_table = tables > part.count("\\end{longtable}", 0, m.start())
            chunks.append((part[i : m.start()], None))
            span = part[m.start() : end]
            chunks.append((span, as_written(span, opening != "\\(" and not in_table)))
            i = end
        chunks.append((part[i:], None))
    return chunks


def source_chunks(markdown: str) -> list[Chunk]:
    return [(
        r"{\small\itshape The answer did not typeset; it is shown as its source.}\par"
        + "\n\\begin{Verbatim}[breaklines,breakanywhere,fontsize=\\scriptsize]\n"
        + markdown.replace("\\end{Verbatim}", "\\end {Verbatim}")
        + "\n\\end{Verbatim}\n",
        None,
    )]  # fmt: skip


def balanced(s: str) -> bool:
    depth = 0
    for c in s.replace("\\{", "").replace("\\}", ""):
        depth += {"{": 1, "}": -1}.get(c, 0)
        if depth < 0:
            return False
    return depth == 0


def formula(s: str) -> Chunk:
    """A string of the parser typeset as a formula, or as written when it cannot be."""
    raw = re.sub(r"[\x00-\x1f]", "", str(s).translate(CTRL)).strip()
    inner = raw.strip("$").strip()
    for a, b in (("\\(", "\\)"), ("\\[", "\\]")):
        if inner.startswith(a) and inner.endswith(b):
            inner = inner[2:-2].strip()
    shown = r"\texttt{" + esc(raw) + "}"
    unsafe = ("&", "%", "#", "$", "\\\\", "\\begin", "\\end", "\\par")
    if not inner or not balanced(inner) or any(t in inner for t in unsafe):
        return (shown, None)
    return (r"\(" + inner + r"\)", shown)


def check_chunks(code: str, stratum: str, graph: dict) -> list[Chunk]:
    """The check page: the questions, a note field and what the parser read."""
    model = parse_reply(graph["call"]["response"]["content"])
    core = core_model(model)
    kept_c = {c.Number for c in core.constraints}
    kept_v = {v.Number for v in core.variablesInModel}
    abbr = {v.Number: v.Abbreviation for v in model.variablesInModel}
    out: list[Chunk] = []

    def text(s: str) -> None:
        out.append((s, None))

    head = [r"\clearpage", r"{\sffamily\bfseries\large Item " + code + r": check}\par\medskip",
            r"{\renewcommand{\arraystretch}{1.9}",
            r"\begin{tabular}{@{}p{55mm}@{\hspace{3mm}}>{\raggedright\arraybackslash}p{85mm}@{}}"]  # fmt: skip
    n = 0
    for key, question, options, strata in QUESTIONS:
        if stratum not in strata:
            continue
        n += 1
        boxes = r"\quad ".join(rf"\cb{{{key}.{v}}}\,{label}" for v, label in options)
        head.append(rf"\textbf{{{n}}}\enspace {question} & {boxes}\\")
    head += [r"\end{tabular}}\par\medskip",
             r"{\sffamily Note (optional)}\par\nopagebreak",
             r"\noindent{\setlength{\fboxsep}{0pt}\mk{note}\fbox{\rule{0pt}{"
             f"{NOTE_MM[1]}mm" r"}\rule{" f"{NOTE_MM[0]}mm" r"}{0pt}}}\par\bigskip",
             r"{\sffamily\bfseries What the parser read}\par\smallskip\footnotesize",
             r"\begin{longtable}{@{}r@{\hspace{2mm}}p{44mm}@{\hspace{2mm}}c@{\hspace{2mm}}p{80mm}@{}}",
             r"\toprule no. & name & lin. & variables\\\midrule\endhead", ""]  # fmt: skip
    text("\n".join(head))

    def mark(eq, is_objective: bool) -> str:
        if stratum == "warning" and not is_objective and eq.Number not in kept_c:
            return r"\mbox{\textbf{CUT}}"
        if stratum == "nonlinear" and not eq.Linear and (is_objective or eq.Number in kept_c):
            return r"\mbox{\textbf{NONLINEAR}}"
        return ""

    def row(label: str, eq, is_objective: bool) -> None:
        m = mark(eq, is_objective)
        lin = "✓" if eq.Linear else r"\textbf{×}"
        text(f"{label} & {esc(eq.Name)} {m} & {lin} & ")
        for j, i in enumerate(eq.VariablesIncluded):
            if j:
                text(", ")
            out.append(formula(abbr.get(i, f"?{i}")))
        text("\\\\\n" if eq.VariablesIncluded else "--\\\\\n")
        if m:
            text(r"\multicolumn{4}{@{}p{\dimexpr\linewidth\relax}@{}}{\quad\small ")
            out.append(formula(eq.equation))
            text("}\\\\[1mm]\n")

    for eq in model.objective_functions:
        row(f"obj {eq.Number}", eq, True)
    text("\\midrule\n")
    for eq in model.constraints:
        row(str(eq.Number), eq, False)
    text("\\bottomrule\\end{longtable}\n\\textbf{Variables:} ")
    for j, v in enumerate(model.variablesInModel):
        cut = r" \textbf{CUT}" if stratum == "warning" and v.Number not in kept_v else ""
        text((", " if j else "") + f"{v.Number}~")
        out.append(formula(v.Abbreviation))
        text(f"~({DOMAIN.get(v.Domain, v.Domain)}){cut}")
    text("\\par\n")
    return out


def item_head(code: str, stratum: str, batch: int) -> str:
    return (rf"\fancyhead[L]{{\small\sffamily Item {code} · {LETTER[stratum]}}}"
            rf"\fancyhead[R]{{\small\sffamily Paper 0 audit · batch {batch} · \thepage}}")  # fmt: skip


def item_chunks(code: str, stratum: str, answer: list[Chunk], check: list[Chunk]) -> list[Chunk]:
    title = rf"{{\sffamily\bfseries\large Item {code}: the answer as printed}}\par\medskip" + "\n"
    shown = [(title, None), *answer]
    # an N item asks about named equations only: its check page comes first and names them
    if stratum == "nonlinear":
        return [*check, ("\\clearpage\n", None), *shown]
    return [*shown, ("\n", None), *check]


def assemble(chunks: list[Chunk]) -> tuple[str, dict[int, tuple[int, int]]]:
    """The LaTeX of ``chunks``, with every formula on lines of its own (joined by comments, so
    no space is added), and the first and last line of every formula."""
    parts, spans, line = [], {}, 1
    for i, (s, fallback) in enumerate(chunks):
        if fallback is not None:
            spans[i] = (line + 1, line + 1 + s.count("\n"))
            s = "%\n" + s + "%\n"
        parts.append(s)
        line += s.count("\n")
    return "".join(parts), spans


def lualatex(
    workdir: Path, name: str, tex: str, halt: bool = True
) -> tuple[Path | None, list[str], list[int], bool]:
    """Typeset ``tex``: the PDF (if any), the missing characters, the input lines of the
    errors, and whether it typeset without an error."""
    (workdir / f"{name}.tex").write_text(tex, encoding="utf-8", newline="\n")
    r = subprocess.run(
        ["lualatex", "-interaction=nonstopmode", *(["-halt-on-error"] if halt else []), f"{name}.tex"],
        cwd=workdir, capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    log = (workdir / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    missing = re.findall(r"Missing character: There is no (\S+)", log)
    lines = [int(n) for n in re.findall(r"^l\.(\d+)", log, flags=re.M)]
    pdf = workdir / f"{name}.pdf"
    ok = r.returncode == 0 and pdf.is_file() and not re.search(r"^! ", log, flags=re.M)
    return (pdf if pdf.is_file() else None), missing, lines, ok


def render(
    work: Path, name: str, head: str, chunks: list[Chunk]
) -> tuple[Path | None, list[str], int, bool]:
    """Typeset an item; a formula that does not typeset is shown as written. The PDF, the
    missing characters, the number of formulas shown as written, and whether errors in the
    text remain (the PDF is then LaTeX's recovery)."""
    full = [
        (PREAMBLE + head + "\n\\begin{document}\n", None),
        *chunks,
        ("\n\\end{document}\n", None),
    ]
    replaced = 0
    for _ in range(6):
        tex, spans = assemble(full)
        pdf, missing, lines, ok = lualatex(work, name, tex, halt=False)
        if ok:
            return pdf, missing, replaced, False
        # an error is reported at a line of the formula, or at the line after it
        bad = [i for i, (a, b) in spans.items() if any(a <= n <= b + 1 for n in lines)]
        if not bad:
            return pdf, missing, replaced, True
        for i in bad:
            full[i] = (full[i][1], None)
        replaced += len(bad)
    return pdf, missing, replaced, True


def positions(pos_file: Path) -> dict[str, dict]:
    """Box and note positions (page of the item, rectangle in PDF points from the top left)."""
    import pymupdf

    out = {}
    pdf = pymupdf.open(pos_file.with_suffix(".pdf"))
    for line in pos_file.read_text(encoding="utf-8").splitlines():
        ident, page, x, y = line.split()
        h = pdf[int(page) - 1].rect.height
        x0, y0 = int(x) / SP_PER_BP, h - int(y) / SP_PER_BP
        w, hh = NOTE_MM if ident == "note" else (BOX_MM, BOX_MM)
        out[ident] = {"page": int(page), "rect": [x0, y0 - hh * MM, x0 + w * MM, y0]}
    return out


def build(root: Path, graphs: dict, runs: dict, batches: list[int]) -> None:
    import pymupdf

    key = json.loads((root / "audit" / "forms" / "key.json").read_text(encoding="utf-8"))
    items = key["items"]
    n_batches = max(v["batch"] for v in items.values())
    out = root / "audit" / "forms" / "build"
    out.mkdir(parents=True, exist_ok=True)
    boxes_path = out / "boxes.json"
    boxes = json.loads(boxes_path.read_text(encoding="utf-8")) if boxes_path.is_file() else {}
    report = []
    for batch in batches or range(1, n_batches + 1):
        codes = sorted(c for c, v in items.items() if v["batch"] == batch)
        work = out / f"work_{batch}"
        work.mkdir(exist_ok=True)
        intro = (INSTRUCTIONS.replace("NBATCH", str(n_batches)).replace("BATCH", str(batch))
                 .replace("FIRST", codes[0]).replace("LAST", codes[-1]))  # fmt: skip
        pdf, _, _, _ = lualatex(work, "intro", PREAMBLE + intro)
        if pdf is None:
            raise SystemExit(f"batch {batch}: the instruction page does not typeset ({work})")
        doc = pymupdf.open(pdf)
        for code in codes:
            item = items[code]
            graph, run = graphs[item["run_id"]], runs[item["run_id"]]
            head = item_head(code, item["stratum"], batch)
            check = check_chunks(code, item["stratum"], graph)
            answer = run["final_answer"] or ""
            try:
                body = answer_chunks(answer)
            except RuntimeError:
                body = None
            name = f"item{code}"
            shown, pdf, missing, replaced, text_errors = "source", None, [], 0, True
            if body is not None:
                pdf, missing, replaced, text_errors = render(
                    work, name, head, item_chunks(code, item["stratum"], body, check)
                )
                shown = "typeset"
                if text_errors and pdf is not None:
                    # LaTeX recovered from an error outside the formulas: say so on the page
                    notice = (
                        r"{\small\itshape LaTeX reported an error in the text of this answer;"
                        r" if a passage looks garbled, say so in the note.}\par" + "\n",
                        None,
                    )
                    pdf, missing, replaced, _ = render(
                        work, name, head, item_chunks(code, item["stratum"], [notice, *body], check)
                    )
                    shown = "recovered"
            if pdf is None:
                shown = "source"
                pdf, missing, replaced, text_errors = render(
                    work,
                    name,
                    head,
                    item_chunks(code, item["stratum"], source_chunks(answer), check),
                )
            if pdf is None:
                raise SystemExit(f"item {code}: the check page does not typeset ({work})")
            first = len(doc)
            item_doc = pymupdf.open(pdf)
            doc.insert_pdf(item_doc)
            pos = positions(work / f"item{code}.pos")
            boxes[code] = {k: {"page": first + v["page"] - 1, "rect": v["rect"]}
                           for k, v in pos.items()}  # fmt: skip
            report.append(f"{code} batch {batch} {item['stratum']:9s} {shown:9s} "
                          f"{len(item_doc)} pages, formulas as written: {replaced}, "
                          f"missing characters: {len(missing)}")  # fmt: skip
            print(report[-1], flush=True)
        name = out / f"P0 audit {batch} of {n_batches}.pdf"
        doc.set_metadata({"title": f"Paper 0 audit, batch {batch} of {n_batches}"})
        doc.save(name, garbage=3, deflate=True)
        print(f"{name}: {len(doc)} pages")
    boxes_path.write_text(json.dumps(boxes, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                          newline="\n")  # fmt: skip
    with (out / "build.log").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")


def send(root: Path, batches: list[int]) -> None:
    out = root / "audit" / "forms" / "build"
    subprocess.run([RMAPI, "mkdir", "/Papers"], capture_output=True, timeout=180)
    subprocess.run([RMAPI, "mkdir", REMOTE], capture_output=True, timeout=180)
    for pdf in sorted(out.glob("P0 audit * of *.pdf")):
        batch = int(pdf.stem.split()[2])
        if batches and batch not in batches:
            continue
        r = subprocess.run([RMAPI, "put", str(pdf), REMOTE], capture_output=True, text=True,
                           timeout=300)  # fmt: skip
        print(f"{pdf.name}: {'sent' if r.returncode == 0 else (r.stderr or r.stdout).strip()}")


def ink(page, rect, dpi: int = 150) -> float:
    """Share of dark pixels inside ``rect`` (inset by 15 % on every side)."""
    import pymupdf

    r = pymupdf.Rect(rect)
    dx, dy = r.width * 0.15, r.height * 0.15
    clip = pymupdf.Rect(r.x0 + dx, r.y0 + dy, r.x1 - dx, r.y1 - dy)
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=pymupdf.csGRAY)
    data = pix.samples
    return sum(1 for b in data if b < 200) / max(1, len(data))


def read(root: Path) -> None:
    import pymupdf

    forms = root / "audit" / "forms"
    key = json.loads((forms / "key.json").read_text(encoding="utf-8"))["items"]
    boxes = json.loads((forms / "build" / "boxes.json").read_text(encoding="utf-8"))
    returned = forms / "returned"
    returned.mkdir(exist_ok=True)
    marks_path = forms / "marks.json"
    marks = json.loads(marks_path.read_text(encoding="utf-8")) if marks_path.is_file() else {}
    for blank in sorted((forms / "build").glob("P0 audit * of *.pdf")):
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run([RMAPI, "geta", f"{REMOTE}/{blank.stem}"], cwd=td,
                               capture_output=True, text=True, timeout=300)  # fmt: skip
            pdfs = list(Path(td).glob("*.pdf"))
            if r.returncode != 0 or not pdfs:
                print(f"{blank.stem}: no annotated copy yet")
                continue
            annotated = returned / f"{blank.stem} annotated.pdf"
            shutil.move(str(pdfs[0]), annotated)
        doc, orig = pymupdf.open(annotated), pymupdf.open(blank)
        pages = {}  # check pages by their title (the tablet may add pages)
        for i, page in enumerate(doc):
            for m in re.finditer(r"Item (\d{3}): check", page.get_text()):
                pages[m.group(1)] = i
        batch = int(blank.stem.split()[2])
        for code in sorted(c for c, v in key.items() if v["batch"] == batch):
            if code not in pages:
                print(f"item {code}: check page not found")
                continue
            page, blank_page = doc[pages[code]], orig[boxes[code]["note"]["page"]]
            answers, doubtful, filled = {}, [], 0
            for ident, b in boxes[code].items():
                if ident == "note":
                    continue
                q, value = ident.split(".", 1)
                share = ink(page, b["rect"]) - ink(blank_page, b["rect"])
                if share >= TICK:
                    answers.setdefault(q, []).append(value)
                    filled += 1
                elif share > EMPTY:
                    doubtful.append(ident)
            note = ink(page, boxes[code]["note"]["rect"]) - ink(
                blank_page, boxes[code]["note"]["rect"]
            )
            if not answers and not doubtful and note <= NOTE_INK:
                continue  # not labelled yet
            questions = [q for q, _, _, strata in QUESTIONS if key[code]["stratum"] in strata]
            unanswered = [q for q in questions if q not in answers and q not in ("kind", "unsure")]
            several = [q for q, v in answers.items() if len(v) > 1 and q not in MULTI]
            entry = {"stratum": key[code]["stratum"], "run_id": key[code]["run_id"],
                     "answers": {q: (v if q in MULTI else v[0]) for q, v in sorted(answers.items())},
                     "note": note > NOTE_INK, "doubtful": doubtful,
                     "unanswered": unanswered, "several": several}  # fmt: skip
            marks[code] = entry
            if entry["note"] or doubtful or unanswered or several:
                rect = pymupdf.Rect(boxes[code]["note"]["rect"])
                top = min(b["rect"][1] for b in boxes[code].values()) - 20
                clip = pymupdf.Rect(0, top, page.rect.width, rect.y1 + 6)
                page.get_pixmap(dpi=110, clip=clip).save(returned / f"item{code}.png")
            print(f"item {code}: {entry['answers']}"
                  + (" (look: " + ", ".join(doubtful + unanswered + several) + ")"
                     if doubtful or unanswered or several else "")
                  + (" + note" if entry["note"] else ""))  # fmt: skip
    marks_path.write_text(json.dumps(marks, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                          encoding="utf-8", newline="\n")  # fmt: skip


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in ("draw", "build", "send", "read"):
        print(__doc__)
        return 2
    command, rest = args[0], args[1:]
    toml = next((a for a in rest if a.endswith(".toml")), "studies/paper0_2026/study.toml")
    batches = [int(a) for a in rest if a.isdigit()]
    spec = load_study(toml)
    root = spec.root
    if command == "draw":
        rows, _, _ = load(root, list(spec.models))
        draw(root, rows)
    elif command == "build":
        _, graphs, runs = load(root, list(spec.models))
        build(root, graphs, runs, batches)
    elif command == "send":
        send(root, batches)
    else:
        read(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
