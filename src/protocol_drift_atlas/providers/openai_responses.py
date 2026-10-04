"""OpenAI provider using the Chat Completions API with JSON output.

This adapter supports any OpenAI-compatible endpoint that accepts a
``response_format={"type": "json_object"}`` parameter and returns a
JSON object with a ``verdict`` field.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping

from ..models.judgment import (
    ExecutionStatus,
    JudgeRequest,
    JudgmentResult,
    Verdict,
)


DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenAIProvider:
    """Provider adapter for the OpenAI Chat Completions API."""

    provider_id = "openai"
    adapter_id = "openai_chat_completions"
    adapter_version = "0.1.0"
    endpoint_type = "chat_completions"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: API key. If not provided, ``OPENAI_API_KEY`` is used.
            base_url: Optional custom base URL. If not provided, the
                OpenAI default is used.
            timeout: Request timeout in seconds.

        Raises:
            RuntimeError: If no API key is available.
        """
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. "
                "Set the environment variable or pass api_key explicitly. "
                "For offline use, select the mock provider instead."
            )

        client_kwargs: dict[str, Any] = {"api_key": key, "timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = OpenAI(**client_kwargs)

    def judge(self, request: JudgeRequest) -> JudgmentResult:
        start = time.perf_counter()
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        try:
            response = self._client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=(
                    request.temperature if request.temperature is not None else 0.0
                ),
                top_p=request.top_p if request.top_p is not None else 1.0,
                max_tokens=request.max_output_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            return JudgmentResult(
                status=ExecutionStatus.PROVIDER_ERROR,
                verdict=None,
                brief_rationale=None,
                raw_text=str(exc),
                provider_id=self.provider_id,
                adapter_version=self.adapter_version,
                model_requested=request.model,
                model_returned=None,
                request_id=None,
                input_tokens=None,
                output_tokens=None,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                provider_extras={},
            )

        raw_text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        model_returned = getattr(response, "model", None)
        request_id = getattr(response, "id", None)
        latency_ms = (time.perf_counter() - start) * 1000.0

        return self._parse_response(
            raw_text=raw_text,
            request=request,
            model_returned=model_returned,
            request_id=request_id,
            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            latency_ms=latency_ms,
        )

    def _parse_response(
        self,
        *,
        raw_text: str,
        request: JudgeRequest,
        model_returned: str | None,
        request_id: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: float,
    ) -> JudgmentResult:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return self._invalid_output(
                raw_text=raw_text,
                request=request,
                model_returned=model_returned,
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )

        if not isinstance(parsed, dict):
            return self._invalid_output(
                raw_text=raw_text,
                request=request,
                model_returned=model_returned,
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )

        verdict_raw = str(parsed.get("verdict", "")).strip().lower()
        try:
            verdict = Verdict(verdict_raw)
        except ValueError:
            return self._invalid_output(
                raw_text=raw_text,
                request=request,
                model_returned=model_returned,
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )

        rationale = parsed.get("brief_rationale")
        return JudgmentResult(
            status=ExecutionStatus.COMPLETED,
            verdict=verdict,
            brief_rationale=rationale if isinstance(rationale, str) else None,
            raw_text=raw_text,
            provider_id=self.provider_id,
            adapter_version=self.adapter_version,
            model_requested=request.model,
            model_returned=model_returned,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider_extras={},
        )

    def _invalid_output(
        self,
        *,
        raw_text: str,
        request: JudgeRequest,
        model_returned: str | None,
        request_id: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: float,
    ) -> JudgmentResult:
        return JudgmentResult(
            status=ExecutionStatus.INVALID_OUTPUT,
            verdict=None,
            brief_rationale=None,
            raw_text=raw_text,
            provider_id=self.provider_id,
            adapter_version=self.adapter_version,
            model_requested=request.model,
            model_returned=model_returned,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider_extras={},
        )

    def manifest_extras(self) -> Mapping[str, Any]:
        return {"api_response_format": "json_object"}