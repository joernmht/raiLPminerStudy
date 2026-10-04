"""Transient-fault handling for HTTP calls: retry what is worth retrying, nothing else.

Vendored from ``raiLPminerExperimentation/corpusbuilder/_http.py`` (same author,
MIT) at commit ``ceb87a9`` so that this repository has no code dependency on the
lab. The logic is unchanged; only the acquisition-specific error type is gone.

Two ideas carry the module:

**Retry only what is worth retrying.** :data:`RETRYABLE_STATUS` and
:func:`is_transient_exception` draw the line. Connection resets, timeouts and
overload statuses are retried with jittered exponential backoff, honouring an
upstream ``Retry-After`` when it sends one. A 400 is returned immediately: it
is an answer about the request, not a fault.

**A transient fault is not a result.** Callers that record outcomes (the study
runner) must stop instead of recording when the retries run out, so that network
weather never enters the data as a model failure.

``sleep``, ``rng`` and ``now`` are injectable so the tests stay deterministic and
instant.
"""

from __future__ import annotations

import email.utils
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

__all__ = [
    "RETRYABLE_STATUS",
    "RetryPolicy",
    "is_transient_exception",
    "is_transient_status",
    "parse_retry_after",
    "request_with_retry",
]

#: Statuses that mean "try again later", not "here is your answer":
#: 408 request-timeout, 425 too-early, 429 rate-limited, 5xx overload/upstream.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

#: requests exceptions that indicate a transport-level blip rather than a bug.
_TRANSIENT_EXC: tuple[type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try before giving up on a transient fault."""

    attempts: int = 4  # total tries, so 3 retries after the first call
    base_delay: float = 1.0  # seconds; doubled each attempt
    max_delay: float = 30.0  # cap on a single computed backoff
    max_retry_after: float = 300.0  # never honour an absurd upstream Retry-After
    jitter: bool = True  # full jitter: uniform(0, delay)


DEFAULT_POLICY = RetryPolicy()


def is_transient_status(status: int | None) -> bool:
    """True if an HTTP status means "try again later"."""
    return status in RETRYABLE_STATUS


def is_transient_exception(exc: BaseException) -> bool:
    """True if ``exc`` is a transport blip worth retrying."""
    return isinstance(exc, _TRANSIENT_EXC)


def parse_retry_after(
    value: str | None, *, now: float | None = None, cap: float = 300.0
) -> float | None:
    """Parse a ``Retry-After`` header into a non-negative delay in seconds.

    Supports both RFC 9110 forms (delta-seconds and an HTTP-date). Returns
    ``None`` if absent or unparseable and clamps to ``[0, cap]``.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        seconds = float(int(value))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        reference = time.time() if now is None else now
        seconds = when.timestamp() - reference
    return max(0.0, min(seconds, cap))


def _backoff(attempt: int, policy: RetryPolicy, rng: random.Random) -> float:
    delay = min(policy.base_delay * (2**attempt), policy.max_delay)
    return rng.uniform(0.0, delay) if policy.jitter else delay


def request_with_retry(
    send: Callable[[], requests.Response],
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    now: Callable[[], float] = time.time,
    describe: str = "request",
    on_retry: Callable[[int, float, str], None] | None = None,
) -> requests.Response:
    """Call ``send()`` with retries on transient faults; return the final response.

    Returns the last response even when it carries a retryable status and the
    attempts ran out; the caller maps the status to a domain error.
    Non-retryable exceptions, and the final transient exception after
    exhaustion, propagate unchanged.
    """
    rng = rng or random.Random()
    last_exc: Exception | None = None

    for attempt in range(policy.attempts):
        final = attempt == policy.attempts - 1
        try:
            response = send()
        except Exception as exc:
            if not is_transient_exception(exc) or final:
                raise
            last_exc = exc
            delay = _backoff(attempt, policy, rng)
            if on_retry:
                on_retry(attempt + 1, delay, f"{describe}: {type(exc).__name__}: {exc}")
            sleep(delay)
            continue

        if not is_transient_status(response.status_code) or final:
            return response

        retry_after = parse_retry_after(
            response.headers.get("Retry-After"), now=now(), cap=policy.max_retry_after
        )
        delay = retry_after if retry_after is not None else _backoff(attempt, policy, rng)
        if on_retry:
            on_retry(attempt + 1, delay, f"{describe}: HTTP {response.status_code}")
        sleep(delay)

    raise last_exc or RuntimeError(f"{describe}: retry loop exhausted")
