"""Extract a paper's input text (abstract + introduction) from PDF text.

    python3 scripts/extract_input_pdftext.py <text.txt> <out.md> \
        --abstract-start '^Abstract$' --abstract-end '^Keywords' \
        --intro-start '^Introduction$' --intro-end '^Conflict detection and resolution modelling$' \
        [--drop '^Running header of the paper']

For papers without publisher XML. The text comes from a PDF extraction with page
markers (``=== PAGE n ===``); the script keeps the lines between the markers (and
the rest of the start line, as in ``Abstract. Text...``), drops page markers, lone
page and section numbers, citation footers and every line matching a ``--drop``
pattern (running headers name the title and authors, which must not reach the
model), mends hyphenation at line ends and rebuilds paragraphs (a line that ends
a sentence and is clearly shorter than the text width ends a paragraph). The
output format is that of scripts/extract_input.py.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path


def _between(lines: list[str], start: str, end: str) -> list[str]:
    s = next(i for i, line in enumerate(lines) if re.search(start, line))
    e = next(i for i in range(s + 1, len(lines)) if re.search(end, lines[i]))
    rest = re.sub(start, "", lines[s], count=1).strip()
    return ([rest] if rest else []) + lines[s + 1 : e]


#: Running page furniture of repository PDFs (citation footers name title and authors,
#: which must never reach the model).
FURNITURE = re.compile(r"^(To cite this (paper|article)|https?://doi\.org/|HAL Id:)", re.I)


def _clean(lines: list[str], drop: tuple[str, ...] = ()) -> list[str]:
    """Drop page markers, page and section numbers, citation footers (up to and incl. the
    DOI line) and lines matching a ``drop`` pattern."""
    out = []
    skipping = 0
    for line in lines:
        line = line.rstrip()
        if skipping:
            skipping -= 1
            if "doi.org/" in line:
                skipping = 0
            continue
        if line.startswith("=== PAGE") or re.fullmatch(r"\s*\d{1,3}\.?\s*", line):
            continue
        if any(re.search(pattern, line) for pattern in drop):
            continue
        if FURNITURE.search(line):
            skipping = 0 if "doi.org/" in line else 3
            continue
        out.append(line)
    return out


_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
#: Spacing accents that LaTeX-made PDFs extract before their letter (``Sch¨obel``), with the
#: combining mark each stands for.
_ACCENTS = {"¨": "\u0308", "´": "\u0301", "`": "\u0300", "˜": "\u0303", "ˆ": "\u0302"}
_DETACHED = re.compile("([" + "".join(_ACCENTS) + "])([A-Za-z])")


def _compose_accents(text: str) -> str:
    """``Sch¨obel`` -> ``Schöbel``: a spacing accent before a letter becomes its diacritic."""
    return unicodedata.normalize(
        "NFC", _DETACHED.sub(lambda m: m.group(2) + _ACCENTS[m.group(1)], text)
    )


def vocabulary(lines: list[str]) -> set[str]:
    """Every word of the document that is not cut at a line end (lower case)."""
    words: set[str] = set()
    for line in lines:
        words.update(w.lower() for w in _WORD.findall(re.sub(r"\S+-$", "", line.rstrip())))
    return words


def _mend(current: str, line: str, vocab: set[str]) -> str:
    """Join a line cut after a hyphen: keep the hyphen of a compound the document writes
    with one elsewhere (high-speed), drop it at a syllable break (re-scheduling)."""
    left = _WORD.findall(current[:-1])[-1].split("-")[-1] if _WORD.findall(current[:-1]) else ""
    right = (_WORD.findall(line) or [""])[0]
    if f"{left}-{right}".lower() in vocab and f"{left}{right}".lower() not in vocab:
        return current + line.strip()
    return current[:-1] + line.strip()


def _paragraphs(lines: list[str], vocab: set[str] | None = None) -> list[str]:
    vocab = vocabulary(lines) if vocab is None else vocab
    width = max((len(line) for line in lines), default=80)
    paras: list[str] = []
    current = ""
    for line in lines:
        if not line.strip():
            continue
        if line.lstrip().startswith("•"):
            # a list item is a paragraph of its own; its bullet goes, as list labels do in
            # the XML extraction
            if current:
                paras.append(current)
            current = line.lstrip()[1:].strip()
            continue
        if current.endswith("-") and line[:1].islower():
            current = _mend(current, line, vocab)
        else:
            current = (current + " " + line.strip()).strip()
        if line.rstrip().endswith((".", ":")) and len(line) < 0.8 * width:
            paras.append(current)
            current = ""
    if current:
        paras.append(current)
    return [_compose_accents(re.sub(r"\s+", " ", p)) for p in paras]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--abstract-start", required=True)
    ap.add_argument("--abstract-end", required=True)
    ap.add_argument("--intro-start", required=True)
    ap.add_argument("--intro-end", required=True)
    ap.add_argument("--drop", action="append", default=[], help="drop lines matching this")
    args = ap.parse_args()
    lines = args.text.read_text(encoding="utf-8").splitlines()
    drop = tuple(args.drop)
    vocab = vocabulary(_clean(lines, drop))
    abstract = " ".join(
        _paragraphs(_clean(_between(lines, args.abstract_start, args.abstract_end), drop), vocab)
    )
    intro = _paragraphs(_clean(_between(lines, args.intro_start, args.intro_end), drop), vocab)
    text = abstract + "\n\nIntroduction\n\n" + "\n\n".join(intro) + "\n"
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(text.split())} words, {len(intro)} paragraphs written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
