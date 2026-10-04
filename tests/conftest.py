"""Shared fakes: an endpoint that answers from a script, and a minimal study spec.

No test touches the network. ``FakeSession`` stands in for ``requests.Session``
(it records every request body and plays back scripted HTTP responses);
``ScriptedClient`` stands in for :class:`genstudy.llm.ChatClient` at the
workflow level and answers each request with a function of its body.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from genstudy.config import PacingSpec
from genstudy.llm import CallResult, ToolCall


def http_response(status: int, payload: dict[str, Any] | None = None, **headers: str):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload or {}).encode("utf-8")
    r.headers = CaseInsensitiveDict(headers)
    return r


def completion(content: str = "", tool_calls: list[dict[str, Any]] | None = None, **extra: Any):
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "cmpl-1",
        "model": extra.get("model", "m"),
        "choices": [{"message": message, "finish_reason": extra.get("finish", "stop")}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


class FakeSession:
    """Plays back ``responses`` in order and records the JSON bodies it was sent."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.sent: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def post(self, url: str, json: dict[str, Any], timeout: float):
        self.sent.append(json)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class ScriptedClient:
    """Workflow-level fake: ``answer(body) -> CallResult``; records every body."""

    def __init__(self, answer: Callable[[dict[str, Any]], CallResult]) -> None:
        self.answer = answer
        self.bodies: list[dict[str, Any]] = []

    def complete(self, body: dict[str, Any], *, describe: str = "chat") -> CallResult:
        self.bodies.append(body)
        return self.answer(body)


def result(content: str = "", tool_calls: tuple[ToolCall, ...] = (), body=None) -> CallResult:
    return CallResult(
        request=body or {},
        content=content,
        reasoning="",
        tool_calls=tool_calls,
        finish_reason="tool_calls" if tool_calls else "stop",
        usage={},
        served_model="m",
        response_id="r",
        latency_s=0.0,
        attempts=1,
    )


@pytest.fixture
def pacing() -> PacingSpec:
    return PacingSpec(min_interval_s=0.0, max_requests_per_day=10_000, max_tries=3)


MINI_SPEC = """
study_id = "test"
base_url = "https://example.invalid/v1"
seed = 1

[pacing]
min_interval_s = 0.0
max_tries = 2

[models.a]
served_id = "org/model-a"
max_tokens = 100

[papers.P1]
doi = "10.1/x"
licence = "cc-by"
input = "inputs/P1.md"

[[experiments]]
name = "exp1"
papers = ["P1"]
models = ["a"]
workflows = ["ZS", "PS"]
temperatures = [0.2, 1.0]
replicates = 2
"""


@pytest.fixture
def study_path(tmp_path: Path) -> Path:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "P1.md").write_text("Trains are delayed.", encoding="utf-8")
    path = tmp_path / "study.toml"
    path.write_text(MINI_SPEC, encoding="utf-8")
    return path
