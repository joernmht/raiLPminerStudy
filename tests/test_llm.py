"""The client: retries what is transient, refuses what is not, paces, budgets, logs."""

from __future__ import annotations

import pytest
import requests
from conftest import FakeSession, completion, http_response

from genstudy.config import PacingSpec
from genstudy.llm import ChatClient, DailyCapReached, EndpointError


def _client(session, *, pacing=None, sleeps=None, clock=None, counter_path=None, wall=None):
    return ChatClient(
        "https://example.invalid/v1",
        "secret-key",
        pacing=pacing or PacingSpec(min_interval_s=0.0, max_tries=3),
        session=session,
        counter_path=counter_path,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
        clock=clock or (lambda: 0.0),
        wall=wall or (lambda: 1_760_000_000.0),
    )


def test_parses_content_reasoning_tool_calls_and_keeps_the_body():
    payload = completion("answer", [{"id": "t1", "function": {"name": "f", "arguments": "{}"}}])
    payload["choices"][0]["message"]["reasoning_content"] = "thinking"
    session = FakeSession([http_response(200, payload, **{"x-ratelimit-remaining": "5"})])
    res = _client(session).complete({"model": "m", "temperature": 0.2, "seed": 3})
    assert res.content == "answer"
    assert res.reasoning == "thinking"
    assert res.tool_calls[0].name == "f"
    assert res.request == {"model": "m", "temperature": 0.2, "seed": 3}
    assert res.rate_headers == {"x-ratelimit-remaining": "5"}
    record = res.to_record()
    assert "secret-key" not in repr(record)


def test_retries_overload_then_succeeds():
    sleeps: list[float] = []
    session = FakeSession(
        [
            http_response(503),
            http_response(429, **{"Retry-After": "2"}),
            http_response(200, completion("ok")),
        ]
    )
    res = _client(session, sleeps=sleeps).complete({"model": "m"})
    assert res.content == "ok"
    assert res.attempts == 3
    assert len(sleeps) == 2


def test_exhausted_retries_are_transient():
    session = FakeSession([http_response(503)] * 3)
    with pytest.raises(EndpointError) as exc:
        _client(session).complete({"model": "m"})
    assert exc.value.transient is True
    assert exc.value.status == 503


def test_transport_errors_are_transient():
    session = FakeSession([requests.ConnectionError("reset")] * 3)
    with pytest.raises(EndpointError) as exc:
        _client(session).complete({"model": "m"})
    assert exc.value.transient is True


def test_client_errors_are_answers_not_faults():
    session = FakeSession([http_response(400, {"error": "context too long"})])
    with pytest.raises(EndpointError) as exc:
        _client(session).complete({"model": "m"})
    assert exc.value.transient is False
    assert exc.value.status == 400
    assert len(session.sent) == 1


def test_pacing_waits_between_requests():
    sleeps: list[float] = []
    times = iter([0.0, 1.0, 1.5, 2.0, 2.5])
    session = FakeSession(
        [http_response(200, completion("a")), http_response(200, completion("b"))]
    )
    client = _client(
        session,
        pacing=PacingSpec(min_interval_s=3.0, max_tries=2),
        sleeps=sleeps,
        clock=lambda: next(times),
    )
    client.complete({"model": "m"})
    client.complete({"model": "m"})
    assert sleeps and sleeps[0] == pytest.approx(2.5)


def test_daily_cap_is_persisted_and_enforced(tmp_path):
    counter = tmp_path / "state" / "requests.json"
    pacing = PacingSpec(min_interval_s=0.0, max_requests_per_day=2, max_tries=2)
    session = FakeSession(
        [http_response(200, completion("a")), http_response(200, completion("b"))]
    )
    client = _client(session, pacing=pacing, counter_path=counter)
    client.complete({"model": "m"})
    client.complete({"model": "m"})
    again = _client(FakeSession([]), pacing=pacing, counter_path=counter)
    with pytest.raises(DailyCapReached) as exc:
        again.complete({"model": "m"})
    assert exc.value.transient is True
