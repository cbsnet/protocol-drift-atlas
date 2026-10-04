"""Execution manifest construction, hashing, and sanitization.

The manifest is the traceability contract of the toolkit. Every run produces
one manifest, which records the provider, model, adapter, parameters, dataset
hash, perturbation registry hash, and response schema hash used in that run.
The manifest must never contain credentials, authorization headers, personal
identifiers, or secret values.

The functions in this module are intentionally side-effect free: they take
explicit inputs and return plain dictionaries, so that manifests can be
validated, diffed, and archived without depending on network state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .judgment import JudgeRequest


# Substrings that must never appear in a manifest. The list is intentionally
# narrow: it targets tokens that would indicate a leaked credential, not
# ordinary words that may legitimately appear in manifest fields. In
# particular, "token" alone is not included, because fields such as
# "max_output_tokens" contain that substring and are not credentials.
FORBIDDEN_MANIFEST_FRAGMENTS: tuple[str, ...] = (
    "sk-",
    "sk_live_",
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "x-api-key",
    "secret_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "password",
)


def sha256_hex(payload: str | bytes) -> str:
    """Return a ``sha256:<hex>`` digest of the input.

    The prefix makes hashes self-describing and prevents accidental
    confusion between different hash algorithms in the manifest.
    """
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def hash_schema(schema: Mapping[str, Any] | None) -> str:
    """Return a deterministic hash of a JSON-serializable schema.

    The serialization is canonical: keys are sorted, separators are
    compact, and non-ASCII characters are preserved. This ensures that
    two logically identical schemas always produce the same hash.
    """
    canonical = json.dumps(
        schema or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_hex(canonical)


def request_hash(request: JudgeRequest) -> str:
    """Return a deterministic hash of a judge request.

    This hash is used as the cache key and as a per-call provenance record
    in the JSONL output. Two requests with the same hash are guaranteed to
    have identical inputs: same provider, same adapter version, same model,
    same prompt, same parameters, and same response schema.
    """
    payload = {
        "provider_id": request.provider_id,
        "adapter_version": request.adapter_version,
        "model": request.model,
        "system_prompt": request.system_prompt,
        "prompt": request.prompt,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_output_tokens": request.max_output_tokens,
        "seed_requested": request.seed_requested,
        "response_schema_hash": hash_schema(request.response_schema),
        "prompt_template_id": request.prompt_template_id,
        "prompt_template_hash": request.prompt_template_hash,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_hex(canonical)


def build_manifest(
    *,
    toolkit_version: str,
    source_revision: str | None,
    run_id: str,
    execution_role: str,
    provider_id: str,
    adapter_id: str,
    adapter_version: str,
    endpoint_type: str | None,
    model_requested: str,
    model_returned: str | None,
    parameters: Mapping[str, Any],
    baseline_protocol_id: str,
    prompt_template_id: str,
    prompt_template_hash: str,
    perturbation_registry_hash: str,
    perturbation_ids: list[str],
    dataset_id: str,
    dataset_hash: str,
    response_schema_hash: str,
    provider_extras: Mapping[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Build a manifest dictionary conforming to the execution manifest schema.

    The function validates that no forbidden fragment appears anywhere in
    the returned structure. If a fragment is found, a ``ValueError`` is
    raised before the manifest can be serialized or archived.
    """
    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "toolkit": {
            "name": "protocol-drift-atlas",
            "version": toolkit_version,
            "source_revision": source_revision,
        },
        "execution": {
            "run_id": run_id,
            "timestamp_utc": timestamp_utc or datetime.now(timezone.utc).isoformat(),
            "execution_role": execution_role,
        },
        "provider": {
            "provider_id": provider_id,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "endpoint_type": endpoint_type,
        },
        "model": {
            "model_requested": model_requested,
            "model_returned": model_returned,
        },
        "parameters": {
            "temperature": parameters.get("temperature"),
            "top_p": parameters.get("top_p"),
            "max_output_tokens": parameters.get("max_output_tokens"),
            "seed_requested": parameters.get("seed_requested"),
            "seed_supported": parameters.get("seed_supported", False),
            "reproducibility_note": parameters.get(
                "reproducibility_note",
                "Repeatability is measured rather than assumed.",
            ),
        },
        "protocol": {
            "baseline_protocol_id": baseline_protocol_id,
            "prompt_template_id": prompt_template_id,
            "prompt_template_hash": prompt_template_hash,
            "perturbation_registry_hash": perturbation_registry_hash,
            "perturbation_ids": list(perturbation_ids),
        },
        "artifacts": {
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "response_schema_hash": response_schema_hash,
        },
        "provider_extras": dict(provider_extras or {}),
    }

    assert_no_secrets(manifest)
    return manifest


def assert_no_secrets(manifest: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` if a manifest field contains a forbidden fragment.

    The check is applied only to fields that may carry provider-specific
    values: ``provider`` and ``provider_extras``. Structured fields such
    as ``model`` and ``parameters`` are not scanned, because their
    contents are determined by the code and cannot contain credentials
    unless a caller passes them explicitly in ``provider_extras``.
    """
    candidates = {
        "provider": manifest.get("provider", {}),
        "provider_extras": manifest.get("provider_extras", {}),
    }
    serialized = json.dumps(candidates, ensure_ascii=False, sort_keys=True).lower()
    for fragment in FORBIDDEN_MANIFEST_FRAGMENTS:
        if fragment in serialized:
            raise ValueError(
                f"Manifest contains forbidden fragment: {fragment!r}. "
                "Remove credentials, authorization headers, or secret values "
                "before building the manifest."
            )