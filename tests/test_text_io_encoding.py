"""Guard: text I/O declares ``encoding="utf-8"``; writes in the package also pin ``newline``.

Run records are interchange artifacts (published with the paper). Under a
non-UTF-8 locale default a read mojibakes non-ASCII text and a write can raise,
and a default ``newline`` writes CRLF on Windows. Same rule and same AST check
as the sibling lab repository (its ADR-0016).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKED_TREES = ("genstudy", "tests")
PRODUCER_TREES = ("genstudy",)
_TEXT_METHODS = frozenset({"read_text", "write_text"})


def _mode(call: ast.Call) -> str:
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        return str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return ""


def _calls(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Call):
            yield node


def _is_text_io(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr in _TEXT_METHODS:
        return True
    return isinstance(node.func, ast.Name) and node.func.id == "open" and "b" not in _mode(node)


def test_text_io_declares_utf8():
    found = []
    for tree in CHECKED_TREES:
        for path in sorted((REPO_ROOT / tree).rglob("*.py")):
            for node in _calls(path):
                if _is_text_io(node) and not any(k.arg == "encoding" for k in node.keywords):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert found == [], "text I/O without encoding=: " + ", ".join(found)


def test_producer_writes_pin_newline():
    found = []
    for tree in PRODUCER_TREES:
        for path in sorted((REPO_ROOT / tree).rglob("*.py")):
            for node in _calls(path):
                writes = (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "write_text"
                ) or (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "open"
                    and any(c in _mode(node) for c in "wa")
                    and "b" not in _mode(node)
                )
                if writes and not any(k.arg == "newline" for k in node.keywords):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert found == [], "text writes without newline=: " + ", ".join(found)
