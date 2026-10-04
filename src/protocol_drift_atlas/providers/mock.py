"""Deterministic mock provider for tests and offline development.

The mock provider never makes network calls. It produces a deterministic
verdict derived from the prompt text, so that runs are reproducible without
depending on any external service. It is used by the ``pda demo`` command
and by the entire test suite.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ..models.judgment import (
    ExecutionStatus,
    JudgeRequest,
    JudgmentResult,
    Verdict,
)


class MockProvider:
    """Provider that returns deterministic verdicts based on prompt content."""

    provider_id = "mock"
    adapter_id = "mock"
    adapter_version = "0.1.0"
    endpoint_type = None

    def __init__(
        self,
        verdict_fn: Callable[[JudgeRequest], str] | None = None,
        model_id: str = "mock",
    ) -> None:
        """Initialize the mock provider.

        Args:
            verdict_fn: Optional callable that returns a verdict string
                (``"safe"``, ``"unsafe"``, ``"indeterminate"``) for a given
                request. If not provided, a deterministic default is used.
            model_id: Identifier reported as ``model_returned``. Defaults to
                ``"mock"``.
        """
        self._verdict_fn = verdict_fn or self._default_verdict
        self._model_id = model_id

    @staticmethod
    def _default_verdict(request: JudgeRequest) -> str:
        """Deterministic verdict derived from the prompt content.

        The logic is intentionally simple and stable. It is not a model:
        it is a reproducible function used only to exercise the pipeline.
        """
        prompt_lower = request.prompt.lower()

        # Baseline condition: everything is safe unless the prompt text
        # explicitly mentions an unsafe policy phrase.
        if "disallowed" in prompt_lower:
            return "unsafe"
        if "audit" in prompt_lower:
            return "unsafe" if "harm" in prompt_lower else "safe"

        # Simple deterministic hash-based fallback.
        digest = sum(ord(c) for c in request.prompt) % 100
        if digest < 70:
            return "safe"
        if digest < 95:
            return "unsafe"
        return "indeterminate"

    def judge(self, request: JudgeRequest) -> JudgmentResult:
        start = time.perf_counter()
        try:
            verdict_text = self._verdict_fn(request)
        except Exception as exc:
            return JudgmentResult(
                status=ExecutionStatus.PROVIDER_ERROR,
                verdict=None,
                brief_rationale=None,
                raw_text=f"mock error: {exc}",
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                model_requested=request.model,
                model_returned=self._model_id,
                request_id=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                provider_extras={},
            )

        normalized = verdict_text.strip().lower()
        try:
            verdict = Verdict(normalized)
        except ValueError:
            return JudgmentResult(
                status=ExecutionStatus.INVALID_OUTPUT,
                verdict=None,
                brief_rationale=None,
                raw_text=verdict_text,
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                model_requested=request.model,
                model_returned=self._model_id,
                request_id=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                provider_extras={},
            )

        raw = '{"verdict": "%s"}' % verdict.value
        return JudgmentResult(
            status=ExecutionStatus.COMPLETED,
            verdict=verdict,
            brief_rationale=None,
            raw_text=raw,
            provider_id=self.provider_id,
            adapter_version=self.adapter_version,
            model_requested=request.model,
            model_returned=self._model_id,
            request_id=f"mock-{abs(hash(request.prompt)) % 10**8}",
            input_tokens=len(request.prompt) // 4,
            output_tokens=len(raw) // 4,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            provider_extras={},
        )

    def manifest_extras(self) -> Mapping[str, Any]:
        return {"mock": True}