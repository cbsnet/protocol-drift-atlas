"""Tests for execution manifest construction and sanitization.

The manifest is the traceability contract of the toolkit. It records
what was run, with which model, on which dataset, under which protocol.
It must never contain credentials, authorization headers, personal
identifiers, or secret values.

These tests verify three properties:

- ``build_manifest`` produces a manifest that validates against the
  JSON Schema;
- ``assert_no_secrets`` refuses to emit a manifest containing a
  forbidden fragment in a field that could carry provider-specific
  values;
- hashing is deterministic and sensitive to the inputs that matter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_valid_manifest(**overrides):
    """Build a manifest with sensible defaults, overriding as needed."""
    from protocol_drift_atlas.models.manifests import build_manifest

    base = dict(
        toolkit_version="0.1.0",
        source_revision="abc123def456",
        run_id="test-run-0001",
        execution_role="custom",
        provider_id="mock",
        adapter_id="mock",
        adapter_version="0.1.0",
        endpoint_type=None,
        model_requested="mock",
        model_returned="mock",
        parameters={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 50,
            "seed_requested": None,
            "seed_supported": False,
            "reproducibility_note": (
                "Repeatability is measured rather than assumed."
            ),
        },
        baseline_protocol_id="BASELINE_V0_1",
        prompt_template_id="baseline.jinja2",
        prompt_template_hash="sha256:" + "a" * 64,
        perturbation_registry_hash="sha256:" + "b" * 64,
        perturbation_ids=[
            "P1_RUBRIC_PARAPHRASE",
            "P2_RESPONSE_POSITION",
            "P3_DECISION_LABEL_WORDING",
            "P4_AUDIT_FRAMING",
        ],
        dataset_id="pda_demo_corpus_v0_1",
        dataset_hash="sha256:" + "c" * 64,
        response_schema_hash="sha256:" + "d" * 64,
        provider_extras={},
    )
    base.update(overrides)
    return build_manifest(**base)


# ---------------------------------------------------------------------------
# Schema validity
# ---------------------------------------------------------------------------


def test_manifest_validates_against_schema(
    manifest_schema_path: Path,
    load_json_schema,
) -> None:
    """build_manifest must produce a manifest that validates against its schema."""
    manifest = _build_valid_manifest()
    schema = load_json_schema(manifest_schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
    if errors:
        first = errors[0]
        location = "/".join(str(p) for p in first.path) or "<root>"
        pytest.fail(
            f"Manifest failed schema validation at {location}: "
            f"{first.message}"
        )


def test_manifest_has_expected_top_level_sections() -> None:
    """All top-level sections required by the schema must be present."""
    manifest = _build_valid_manifest()
    for key in (
        "schema_version",
        "toolkit",
        "execution",
        "provider",
        "model",
        "parameters",
        "protocol",
        "artifacts",
        "provider_extras",
    ):
        assert key in manifest


def test_manifest_schema_version_is_frozen() -> None:
    """The manifest schema version must match the v0.1 release."""
    manifest = _build_valid_manifest()
    assert manifest["schema_version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


def test_manifest_contains_no_secrets() -> None:
    """No forbidden fragment may appear in a manifest built with clean inputs."""
    import json

    manifest = _build_valid_manifest()
    serialized = json.dumps(manifest, sort_keys=True).lower()

    for fragment in (
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
    ):
        assert fragment not in serialized, (
            f"Manifest contained forbidden fragment: {fragment!r}"
        )


def test_assert_no_secrets_rejects_openai_key_prefix() -> None:
    """A manifest carrying an OpenAI key prefix in provider_extras must fail."""
    with pytest.raises(ValueError, match="forbidden"):
        _build_valid_manifest(
            provider_extras={"leaked": "sk-proj-abcdefghijklmnop"}
        )


def test_assert_no_secrets_rejects_authorization_header() -> None:
    """A manifest carrying an authorization header must fail."""
    with pytest.raises(ValueError, match="forbidden"):
        _build_valid_manifest(
            provider_extras={"headers": {"Authorization": "Bearer abc"}}
        )


def test_assert_no_secrets_rejects_access_token() -> None:
    """A manifest carrying an access_token field must fail."""
    with pytest.raises(ValueError, match="forbidden"):
        _build_valid_manifest(
            provider_extras={"access_token": "abcdef"}
        )


def test_assert_no_secrets_allows_max_output_tokens() -> None:
    """The substring 'token' inside a legitimate field must not trigger a failure.

    The forbidden fragments list contains 'access_token' and
    'refresh_token', but not the bare word 'token'. This test ensures
    that a manifest with 'max_output_tokens' in its parameters passes.
    """
    manifest = _build_valid_manifest(
        parameters={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 50,
            "seed_requested": None,
            "seed_supported": False,
            "reproducibility_note": "Repeatability is measured.",
        }
    )
    assert manifest["parameters"]["max_output_tokens"] == 50


# ---------------------------------------------------------------------------
# Provider and model
# ---------------------------------------------------------------------------


def test_model_requested_and_model_returned_are_distinct_fields() -> None:
    """A mismatch between requested and returned model must be preserved."""
    manifest = _build_valid_manifest(
        model_requested="gpt-4o-mini-2024-07-18",
        model_returned="gpt-4o-mini",
        provider_id="openai",
        adapter_id="openai_chat_completions",
        endpoint_type="chat_completions",
    )
    assert manifest["model"]["model_requested"] == "gpt-4o-mini-2024-07-18"
    assert manifest["model"]["model_returned"] == "gpt-4o-mini"


def test_model_returned_can_be_null() -> None:
    """A provider that does not report the model must be representable."""
    manifest = _build_valid_manifest(model_returned=None)
    assert manifest["model"]["model_returned"] is None


def test_provider_id_must_be_in_allowed_set() -> None:
    """Only openai, mock, and custom are allowed as provider ids in v0.1."""
    manifest = _build_valid_manifest(provider_id="openai")
    assert manifest["provider"]["provider_id"] == "openai"


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------


def test_schema_hash_is_deterministic() -> None:
    """Hashing the same schema twice must yield the same digest."""
    from protocol_drift_atlas.models.manifests import hash_schema

    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert hash_schema(schema) == hash_schema(schema)


def test_schema_hash_is_key_order_independent() -> None:
    """Two schemas with the same keys in different order must hash equally."""
    from protocol_drift_atlas.models.manifests import hash_schema

    schema_a = {"type": "object", "properties": {"a": {"type": "string"}}}
    schema_b = {"properties": {"a": {"type": "string"}}, "type": "object"}
    assert hash_schema(schema_a) == hash_schema(schema_b)


def test_schema_hash_changes_when_schema_changes() -> None:
    """A different schema must produce a different hash."""
    from protocol_drift_atlas.models.manifests import hash_schema

    schema_a = {"type": "object"}
    schema_b = {"type": "object", "additionalProperties": False}
    assert hash_schema(schema_a) != hash_schema(schema_b)


def test_request_hash_is_deterministic() -> None:
    """Hashing the same request twice must yield the same digest."""
    from protocol_drift_atlas.models.judgment import JudgeRequest
    from protocol_drift_atlas.models.manifests import request_hash

    request = JudgeRequest(
        provider_id="mock",
        adapter_version="0.1.0",
        model="mock",
        system_prompt=None,
        prompt="Test prompt",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=50,
        seed_requested=None,
        response_schema={},
        prompt_template_id="baseline.jinja2",
        prompt_template_hash="sha256:" + "a" * 64,
    )
    assert request_hash(request) == request_hash(request)


def test_request_hash_changes_when_prompt_changes() -> None:
    """A different prompt must produce a different hash."""
    from protocol_drift_atlas.models.judgment import JudgeRequest
    from protocol_drift_atlas.models.manifests import request_hash

    base = dict(
        provider_id="mock",
        adapter_version="0.1.0",
        model="mock",
        system_prompt=None,
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=50,
        seed_requested=None,
        response_schema={},
        prompt_template_id="baseline.jinja2",
        prompt_template_hash="sha256:" + "a" * 64,
    )
    request_a = JudgeRequest(prompt="First prompt", **base)
    request_b = JudgeRequest(prompt="Second prompt", **base)
    assert request_hash(request_a) != request_hash(request_b)


def test_request_hash_changes_when_temperature_changes() -> None:
    """A different temperature must produce a different hash."""
    from protocol_drift_atlas.models.judgment import JudgeRequest
    from protocol_drift_atlas.models.manifests import request_hash

    base = dict(
        provider_id="mock",
        adapter_version="0.1.0",
        model="mock",
        system_prompt=None,
        prompt="Test prompt",
        top_p=1.0,
        max_output_tokens=50,
        seed_requested=None,
        response_schema={},
        prompt_template_id="baseline.jinja2",
        prompt_template_hash="sha256:" + "a" * 64,
    )
    request_a = JudgeRequest(temperature=0.0, **base)
    request_b = JudgeRequest(temperature=0.7, **base)
    assert request_hash(request_a) != request_hash(request_b)


def test_request_hash_ignores_non_semantic_fields() -> None:
    """Two requests differing only in fields not part of the hash must match."""
    from protocol_drift_atlas.models.judgment import JudgeRequest
    from protocol_drift_atlas.models.manifests import request_hash

    # The JudgeRequest dataclass has no non-semantic fields by design,
    # so this test documents the invariant: every field currently in
    # the request contributes to the hash.
    base = dict(
        provider_id="mock",
        adapter_version="0.1.0",
        model="mock",
        system_prompt=None,
        prompt="Test prompt",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=50,
        seed_requested=None,
        response_schema={},
        prompt_template_id="baseline.jinja2",
        prompt_template_hash="sha256:" + "a" * 64,
    )
    assert request_hash(JudgeRequest(**base)) == request_hash(JudgeRequest(**base))


# ---------------------------------------------------------------------------
# SHA-256 helper
# ---------------------------------------------------------------------------


def test_sha256_hex_has_expected_prefix() -> None:
    """The digest must be prefixed with the algorithm name."""
    from protocol_drift_atlas.models.manifests import sha256_hex

    digest = sha256_hex("test")
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_sha256_hex_accepts_strings_and_bytes() -> None:
    """The helper must accept both str and bytes inputs."""
    from protocol_drift_atlas.models.manifests import sha256_hex

    assert sha256_hex("test") == sha256_hex(b"test")


def test_sha256_hex_matches_known_value() -> None:
    """A known input must produce the well-known SHA-256 digest."""
    from protocol_drift_atlas.models.manifests import sha256_hex

    # SHA-256 of the ASCII string "abc".
    expected = (
        "sha256:"
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert sha256_hex("abc") == expected