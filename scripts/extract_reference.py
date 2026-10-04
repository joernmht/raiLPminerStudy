"""Extract a paper's reference formulation (one or more sections) from Elsevier XML.

    python3 scripts/extract_reference.py <article.xml> <out.md> --section "4.1" --section "4.2"

Sections are selected by their label (``4.1``) or title. The output is the
sections' prose with every display formula as a numbered LaTeX block and inline
mathematics as ``$...$``. MathML is converted by a small deterministic
translator that covers the presentation elements these papers use; anything it
does not know is kept as its character content, so nothing is silently lost.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lxml import etree

CE = "{http://www.elsevier.com/xml/common/dtd}"
MML = "{http://www.w3.org/1998/Math/MathML}"

OPERATORS = {
    "≤": r"\le", "≥": r"\ge", "≠": r"\neq", "∑": r"\sum", "∀": r"\forall", "∈": r"\in",
    "∉": r"\notin", "×": r"\times", "⋅": r"\cdot", "·": r"\cdot", "−": "-", "∞": r"\infty",
    "∪": r"\cup", "∩": r"\cap", "⊆": r"\subseteq", "⊂": r"\subset", "∣": r"\mid",
    "→": r"\to", "∧": r"\land", "∨": r"\lor", "…": r"\ldots", "⋯": r"\cdots",
    "∏": r"\prod", "∃": r"\exists", "⌈": r"\lceil", "⌉": r"\rceil", "⌊": r"\lfloor",
    "⌋": r"\rfloor", "|": "|", "{": r"\{", "}": r"\}", "′": "'",
}  # fmt: skip
GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu",
    "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "φ": r"\varphi",
    "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "Γ": r"\Gamma", "Δ": r"\Delta",
    "Θ": r"\Theta", "Λ": r"\Lambda", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi", "Ω": r"\Omega",
}  # fmt: skip
ACCENTS = {"¯": r"\bar", "ˆ": r"\hat", "^": r"\hat", "˜": r"\tilde", "~": r"\tilde", "→": r"\vec"}


def _sym(text: str) -> str:
    return "".join(GREEK.get(ch, OPERATORS.get(ch, ch)) for ch in text.strip())


def tex(node: etree._Element) -> str:
    """LaTeX for a MathML node (presentation markup)."""
    tag = etree.QName(node).localname
    kids = [c for c in node if isinstance(c.tag, str)]
    if tag in ("mi", "mn"):
        t = _sym(node.text or "")
        return t if len(node.text or "") <= 1 or tag == "mn" else rf"\mathrm{{{t}}}"
    if tag == "mo":
        return " " + _sym(node.text or "") + " "
    if tag == "mtext":
        return rf"\text{{{(node.text or '').strip()}}}"
    if tag == "mspace":
        return r"\;"
    if tag in ("math", "mrow", "mstyle", "mpadded", "semantics"):
        return "".join(tex(c) for c in kids)
    if tag == "msub":
        return f"{{{tex(kids[0])}}}_{{{tex(kids[1])}}}"
    if tag == "msup":
        return f"{{{tex(kids[0])}}}^{{{tex(kids[1])}}}"
    if tag == "msubsup":
        return f"{{{tex(kids[0])}}}_{{{tex(kids[1])}}}^{{{tex(kids[2])}}}"
    if tag == "munder":
        return f"{{{tex(kids[0])}}}_{{{tex(kids[1])}}}"
    if tag == "munderover":
        return f"{{{tex(kids[0])}}}_{{{tex(kids[1])}}}^{{{tex(kids[2])}}}"
    if tag == "mover":
        accent = (kids[1].text or "").strip() if etree.QName(kids[1]).localname == "mo" else ""
        if accent in ACCENTS:
            return f"{ACCENTS[accent]}{{{tex(kids[0])}}}"
        return rf"\overset{{{tex(kids[1])}}}{{{tex(kids[0])}}}"
    if tag == "mfrac":
        return rf"\frac{{{tex(kids[0])}}}{{{tex(kids[1])}}}"
    if tag == "mfenced":
        open_, close = node.get("open", "("), node.get("close", ")")
        sep = node.get("separators", ",")
        return _sym(open_) + (sep[:1] or ",").join(tex(c) for c in kids) + _sym(close)
    if tag == "mtable":
        return r" \\ ".join(" & ".join(tex(td) for td in tr) for tr in kids)
    if tag in ("mtr", "mtd"):
        return "".join(tex(c) for c in kids)
    return _sym("".join(node.itertext()))


def _clean_tex(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def _para(node: etree._Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        if not isinstance(child.tag, str):
            continue
        name = etree.QName(child).localname
        if child.tag == f"{MML}math":
            parts.append(f"${_clean_tex(tex(child))}$")
        elif name == "display":
            parts.append(_display(child))
        elif name in ("float-anchor", "footnote"):
            pass
        else:
            parts.append(_para(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"[ \t]+", " ", "".join(parts)).strip()


def _display(node: etree._Element) -> str:
    """Every formula of a display as its own numbered block (displays group several)."""
    formulas = [f for f in node.iter(f"{CE}formula") if f.find(f"{MML}math") is not None]
    if not formulas:
        math = node.find(f".//{MML}math")
        return f"\n\n$$ {_clean_tex(tex(math)) if math is not None else _para(node)} $$\n\n"
    blocks = []
    for f in formulas:
        label = f.find(f"{CE}label")
        tag = f"  \\tag{{{label.text.strip('()')}}}" if label is not None and label.text else ""
        blocks.append(f"$$ {_clean_tex(tex(f.find(f'{MML}math')))}{tag} $$")
    return "\n\n" + "\n\n".join(blocks) + "\n\n"


def _section_text(section: etree._Element) -> str:
    out: list[str] = []
    for child in section:
        if not isinstance(child.tag, str):
            continue
        name = etree.QName(child).localname
        if name == "label":
            continue
        if name == "section-title":
            label = section.findtext(f"{CE}label") or ""
            out.append(f"## {label} {_para(child)}".replace("##  ", "## "))
        elif name == "section":
            out.append(_section_text(child))
        elif name in ("para", "display"):
            out.append(_para(child) if name == "para" else _display(child))
    return "\n\n".join(p.strip() for p in out if p.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--section", action="append", required=True)
    args = ap.parse_args()
    root = etree.parse(str(args.xml)).getroot()
    chosen = []
    for want in args.section:
        for s in root.iter(f"{CE}section"):
            label = (s.findtext(f"{CE}label") or "").strip()
            title = (
                " ".join("".join(s.find(f"{CE}section-title").itertext()).split())
                if s.find(f"{CE}section-title") is not None
                else ""
            )
            if want in (label, title):
                chosen.append(s)
                break
        else:
            raise SystemExit(f"section {want!r} not found")
    text = "\n\n".join(_section_text(s) for s in chosen) + "\n"
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(chosen)} sections, {text.count('$$') // 2} display formulas -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
