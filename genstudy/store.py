"""Append-only JSONL store of run records, one file per model.

A run record is written once, after its workflow finished, as one line of
canonical JSON (sorted keys, UTF-8, ``\\n``). The file is flushed and fsynced
after every line, so a crash loses at most the run in flight, and a resumed
runner skips every ``run_id`` already on disk. Records are never rewritten;
analyses read them, they do not edit them.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class RunStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def records(self) -> Iterator[dict[str, Any]]:
        if not self.path.is_file():
            return
        opener = gzip.open if self.path.suffix == ".gz" else open
        with opener(self.path, "rt", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{self.path}:{lineno}: corrupt record") from exc

    def done_ids(self) -> set[str]:
        return {r["run_id"] for r in self.records()}

    def append(self, record: dict[str, Any]) -> None:
        if self.path.suffix == ".gz":
            raise ValueError(f"{self.path} is a frozen archive; append to the .jsonl file")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
