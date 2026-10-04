"""One chat completion against an OpenAI-compatible endpoint, gently and on the record.

Two rules carry this module.

**What is sent is what is logged.** The request body is built by the caller as a
plain dict and stored verbatim in the :class:`CallResult` (the API key travels
only in the session header and never appears in a record). The 2025 harness
handed its settings to a library that dropped two of them without a word
(ADR-0001); with the body on the record, a missing system prompt or temperature
is visible in the data.

**A transient fault is not a result.** Overload, rate limiting and transport
errors are retried with backoff (honouring ``Retry-After``) through
:func:`genstudy._http.request_with_retry`. When the attempts run
out the call raises :class:`EndpointError` with ``transient=True`` and the
runner stops *without* recording the run, so network weather never enters the
data as a model failure. A non-retryable HTTP status is an answer about the
request (e.g. a context-length refusal) and raises with ``transient=False``.

ScaDS is a shared academic service: :class:`ChatClient` keeps one request in
flight, waits ``min_interval_s`` between requests and stops at a daily request
cap that is persisted across processes.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from genstudy._http import (
    RetryPolicy,
    is_transient_exception,
    is_transient_status,
    request_with_retry,
)
from genstudy.config import PacingSpec


class EndpointError(RuntimeError):
    """The endpoint did not produce a completion for this request."""

    def __init__(self, message: str, *, status: int | None = None, transient: bool) -> None:
        super().__init__(message)
        self.status = status
        self.transient = transient


class DailyCapReached(EndpointError):
    """The study's own daily request budget is used up; resume tomorrow."""

    def __init__(self, cap: int) -> None:
        super().__init__(f"daily request cap of {cap} reached", transient=True)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class CallResult:
    """One completed request: the exact body sent and what came back."""

    request: Mapping[str, Any]
    content: str
    reasoning: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str | None
    usage: Mapping[str, Any]
    served_model: str | None
    response_id: str | None
    latency_s: float
    attempts: int
    rate_headers: Mapping[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "request": dict(self.request),
            "response": {
                "content": self.content,
                "reasoning": self.reasoning,
                "tool_calls": [
                    {"id": t.id, "name": t.name, "arguments": t.arguments} for t in self.tool_calls
                ],
                "finish_reason": self.finish_reason,
                "usage": dict(self.usage),
                "served_model": self.served_model,
                "response_id": self.response_id,
            },
            "latency_s": round(self.latency_s, 3),
            "attempts": self.attempts,
            "rate_headers": dict(self.rate_headers),
        }


class DailyCounter:
    """Requests per UTC day, persisted as JSON so separate processes share the budget."""

    def __init__(self, path: Path | None, cap: int, wall: Callable[[], float]) -> None:
        self.path = path
        self.cap = cap
        self._wall = wall
        self._counts: dict[str, int] = {}
        if path is not None and path.is_file():
            self._counts = json.loads(path.read_text(encoding="utf-8"))

    def _today(self) -> str:
        return datetime.fromtimestamp(self._wall(), tz=UTC).strftime("%Y-%m-%d")

    def used_today(self) -> int:
        return self._counts.get(self._today(), 0)

    def check(self) -> None:
        if self.used_today() >= self.cap:
            raise DailyCapReached(self.cap)

    def add(self, n: int = 1) -> None:
        day = self._today()
        self._counts[day] = self._counts.get(day, 0) + n
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._counts, sort_keys=True), encoding="utf-8", newline="\n")
            tmp.replace(self.path)


class ChatClient:
    """Sequential, paced chat completions with retry and a daily budget."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        pacing: PacingSpec,
        session: requests.Session | None = None,
        counter_path: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        rng: random.Random | None = None,
        on_retry: Callable[[int, float, str], None] | None = None,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.pacing = pacing
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.counter = DailyCounter(counter_path, pacing.max_requests_per_day, wall)
        self._sleep = sleep
        self._clock = clock
        self._wall = wall
        self._rng = rng or random.Random(0)
        self._on_retry = on_retry
        self._last_end: float | None = None
        self.policy = RetryPolicy(
            attempts=pacing.max_tries, base_delay=5.0, max_delay=120.0, max_retry_after=900.0
        )

    def _pace(self) -> None:
        if self._last_end is None:
            return
        wait = self.pacing.min_interval_s - (self._clock() - self._last_end)
        if wait > 0:
            self._sleep(wait)

    def complete(self, body: Mapping[str, Any], *, describe: str = "chat") -> CallResult:
        """Send one request (with retries) and parse the first choice."""
        self.counter.check()
        self._pace()
        attempts = 0

        def send() -> requests.Response:
            nonlocal attempts
            self.counter.check()
            attempts += 1
            self.counter.add()
            return self.session.post(self.url, json=body, timeout=self.pacing.request_timeout_s)

        start = self._clock()
        try:
            resp = request_with_retry(
                send,
                policy=self.policy,
                sleep=self._sleep,
                rng=self._rng,
                now=self._wall,
                describe=describe,
                on_retry=self._on_retry,
            )
        except DailyCapReached:
            raise
        except requests.RequestException as exc:
            raise EndpointError(
                f"{describe}: {type(exc).__name__}", transient=is_transient_exception(exc)
            ) from exc
        finally:
            self._last_end = self._clock()
        latency = self._last_end - start

        if resp.status_code != 200:
            raise EndpointError(
                f"{describe}: HTTP {resp.status_code}: {resp.text[:300]}",
                status=resp.status_code,
                transient=is_transient_status(resp.status_code),
            )
        try:
            payload = resp.json()
            choice = payload["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise EndpointError(f"{describe}: malformed response body", transient=True) from exc

        tool_calls = tuple(
            ToolCall(
                id=str(tc.get("id") or f"call_{i}"),
                name=str((tc.get("function") or {}).get("name", "")),
                arguments=str((tc.get("function") or {}).get("arguments", "")),
            )
            for i, tc in enumerate(message.get("tool_calls") or [])
        )
        rate = {
            k.lower(): v
            for k, v in resp.headers.items()
            if k.lower().startswith(("x-ratelimit", "retry-after"))
        }
        return CallResult(
            request=dict(body),
            content=str(message.get("content") or ""),
            reasoning=str(message.get("reasoning_content") or message.get("reasoning") or ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            usage=dict(payload.get("usage") or {}),
            served_model=payload.get("model"),
            response_id=payload.get("id"),
            latency_s=latency,
            attempts=attempts,
            rate_headers=rate,
        )
