"""Data models for judge requests and results.

This module defines the canonical data structures passed between the runner,
the provider adapters, and the scoring layer. The structures are deliberately
small and immutable so that every record can be serialized, hashed, and
audited without ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Verdict(str, Enum):
    """The three valid safety classifications a judge may return.

    A value in this enum represents a substantive judgment. It is distinct
    from an execution status: a response may fail to produce a parsable
    verdict, in which case ``JudgmentResult.verdict`` is ``None`` and the
    status is ``invalid_output``.
    """

    SAFE = "safe"
    UNSAFE = "unsafe"
    INDETERMINATE = "indeterminate"


class ExecutionStatus(str, Enum):
    """The execution outcome of a single provider call.

    ``COMPLETED`` indicates that the provider returned a parsable judgment.
    The other statuses indicate that no valid verdict was obtained, and they
    are counted in execution-quality metrics rather than in agreement metrics.
    """

    COMPLETED = "completed"
    INVALID_OUTPUT = "invalid_output"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class JudgeRequest:
    """A single request to a judge provider.

    All fields required to reproduce the call are included here. The request
    hash computed from these fields is the cache key: two requests with the
    same hash are guaranteed to have been issued with identical inputs.
    """

    provider_id: str
    adapter_version: str
    model: str
    system_prompt: str | None
    prompt: str
    temperature: float | None
    top_p: float | None
    max_output_tokens: int
    seed_requested: int | None
    response_schema: Mapping[str, Any]
    prompt_template_id: str
    prompt_template_hash: str


@dataclass(frozen=True)
class JudgmentResult:
    """The outcome of a single judge call.

    ``status`` describes the execution outcome. ``verdict`` is populated only
    when ``status == ExecutionStatus.COMPLETED``. The raw provider text is
    preserved for audit and for the counterexample log, but is never used as a
    metric input.

    ``model_requested`` and ``model_returned`` are kept separate so that any
    mismatch reported by the provider is preserved rather than silently
    overwritten.
    """

    status: ExecutionStatus
    verdict: Verdict | None
    brief_rationale: str | None
    raw_text: str
    provider_id: str
    adapter_version: str
    model_requested: str
    model_returned: str | None
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float | None
    provider_extras: Mapping[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Return True only when a parsable verdict was obtained."""
        return (
            self.status == ExecutionStatus.COMPLETED
            and self.verdict is not None
        )