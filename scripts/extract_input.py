"""Extract a paper's input text (its introduction) from Elsevier full-text XML.

    python3 scripts/extract_input.py <article.xml> <out.md>

The output is exactly the text the models receive: the word "Introduction" and
the introduction with its subsections, citation markers kept as text, floats and
footnotes dropped, inline mathematics reduced to its characters. The abstract is
not part of the input since 2026-10-04 (ADR-0002: it summarises the paper's own
model); neither are title and authors, which would cue recall and are printed to
stdout for the attribution list. The licence is read from the XML and refused
unless it is one of the Creative Commons licences admitted by ADR-0002.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from lxml import etree

CE = "{http://www.elsevier.com/xml/common/dtd}"
DC = "{http://purl.org/dc/elements/1.1/}"
PRISM = "{http://prismstandard.org/namespaces/basic/2.0/}"
ADMITTED = ("/licenses/by/", "/licenses/by-sa/", "/licenses/by-nc/", "/licenses/by-nc-nd/")
DROP = {f"{CE}float-anchor", f"{CE}footnote", f"{CE}label", f"{CE}inter-ref"}


def _text(node: etree._Element) -> str:
    parts: list[str] = []

    def walk(n: etree._Element) -> None:
        if n.tag in DROP:
            if n.tail:
                parts.append(n.tail)
            return
        if n.text:
            parts.append(n.text)
        for child in n:
            walk(child)
        if n is not node and n.tail:
            parts.append(n.tail)

    walk(node)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def extract(xml: Path) -> tuple[str, dict[str, str]]:
    root = etree.parse(str(xml)).getroot()
    licence = next(
        (
            e.text.strip()
            for e in root.iter()
            if etree.QName(e).localname.lower() == "openaccessuserlicense" and e.text
        ),
        "",
    )
    if not any(tag in licence for tag in ADMITTED):
        raise SystemExit(f"licence not admitted by ADR-0002: {licence!r}")
    intro = next(
        (
            s
            for s in root.iter(f"{CE}section")
            if _text(s.find(f"{CE}section-title")).lower() == "introduction"
        ),
        None,
    )
    if intro is None:
        raise SystemExit("no section titled Introduction")
    lines: list[str] = []
    for node in intro.iter(f"{CE}para", f"{CE}section-title"):
        if node.tag == f"{CE}section-title":
            if node.getparent() is not intro:
                lines.append(_text(node))
            continue
        lines.append(_text(node))
    text = "Introduction\n\n" + "\n\n".join(line for line in lines if line) + "\n"
    meta = {
        "doi": (root.findtext(f".//{PRISM}doi") or "").strip(),
        "title": " ".join((root.findtext(f".//{DC}title") or "").split()),
        "licence": licence,
    }
    return text, meta


def main() -> int:
    xml, out = Path(sys.argv[1]), Path(sys.argv[2])
    text, meta = extract(xml)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(meta)
    print(f"{len(text.split())} words written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
