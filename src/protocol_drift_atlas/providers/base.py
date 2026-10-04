"""Provider protocol for judge execution.

Every provider adapter must implement this protocol. The protocol is kept
deliberately small: a provider issues calls and returns results. Everything
else — perturbing the prompt, hashing the request, building the manifest,
scoring the outcome — is handled outside the provider.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..models.judgment import JudgeRequest, JudgmentResult


class JudgeProvider(Protocol):
    """Structural interface implemented by all provider adapters."""

    provider_id: str
    adapter_id: str
    adapter_version: str
    endpoint_type: str | None

    def judge(self, request: JudgeRequest) -> JudgmentResult:
        """Issue one judge call and return the parsed result.

        Implementations must never raise on provider errors. Instead, they
        must return a ``JudgmentResult`` with ``status`` set to one of
        ``provider_error``, ``timeout``, or ``invalid_output``. This keeps
        the runner free of provider-specific exception handling.
        """
        ...

    def manifest_extras(self) -> Mapping[str, Any]:
        """Return sanitized, provider-specific metadata for the manifest.

        The returned mapping is placed in the ``provider_extras`` field of
        the execution manifest. It must not contain credentials,
        authorization headers, personal identifiers, or secret values.
        """
        ...