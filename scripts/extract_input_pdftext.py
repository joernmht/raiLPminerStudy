"""Extract a paper's input text (abstract + introduction) from PDF text.

    python3 scripts/extract_input_pdftext.py <text.txt> <out.md> \
        --abstract-start '^Abstract$' --abstract-end '^Keywords' \
        --intro-start '^Introduction$' --intro-end '^Conflict detection and resolution modelling$'

For papers without publisher XML. The text comes from a PDF extraction with page
markers (``=== PAGE n ===``); the script keeps the lines between the markers,
drops page markers, lone page numbers and the line before a section heading that
holds only the section number, mends hyphenation at line ends, and rebuilds
paragraphs (a line that ends a sentence and is clearly shorter than the text
width ends a paragraph). The output format is that of scripts/extract_input.py.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def _between(lines: list[str], start: str, end: str) -> list[str]:
    s = next(i for i, line in enumerate(lines) if re.search(start, line))
    e = next(i for i in range(s + 1, len(lines)) if re.search(end, lines[i]))
    return lines[s + 1 : e]


#: Running page furniture of repository PDFs (citation footers name title and authors,
#: which must never reach the model).
FURNITURE = re.compile(r"^(To cite this (paper|article)|https?://doi\.org/|HAL Id:)", re.I)


def _clean(lines: list[str]) -> list[str]:
    """Drop page markers, page numbers and citation footers (up to and incl. the DOI line)."""
    out = []
    skipping = 0
    for line in lines:
        line = line.rstrip()
        if skipping:
            skipping -= 1
            if "doi.org/" in line:
                skipping = 0
            continue
        if line.startswith("=== PAGE") or re.fullmatch(r"\s*\d{1,3}\s*", line):
            continue
        if FURNITURE.search(line):
            skipping = 0 if "doi.org/" in line else 3
            continue
        out.append(line)
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    width = max((len(line) for line in lines), default=80)
    paras: list[str] = []
    current = ""
    for line in lines:
        if not line.strip():
            continue
        first = line.strip().split(" ", 1)[0]
        if current.endswith("-") and line[:1].islower() and "-" not in first:
            current = current[:-1] + line.strip()
        elif current.endswith("-") and line[:1].islower():
            current = current + line.strip()
        else:
            current = (current + " " + line.strip()).strip()
        if line.rstrip().endswith((".", ":")) and len(line) < 0.8 * width:
            paras.append(current)
            current = ""
    if current:
        paras.append(current)
    return [re.sub(r"\s+", " ", p) for p in paras]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--abstract-start", required=True)
    ap.add_argument("--abstract-end", required=True)
    ap.add_argument("--intro-start", required=True)
    ap.add_argument("--intro-end", required=True)
    args = ap.parse_args()
    lines = args.text.read_text(encoding="utf-8").splitlines()
    abstract = " ".join(
        _paragraphs(_clean(_between(lines, args.abstract_start, args.abstract_end)))
    )
    intro = _paragraphs(_clean(_between(lines, args.intro_start, args.intro_end)))
    text = abstract + "\n\nIntroduction\n\n" + "\n\n".join(intro) + "\n"
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(text.split())} words, {len(intro)} paragraphs written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
