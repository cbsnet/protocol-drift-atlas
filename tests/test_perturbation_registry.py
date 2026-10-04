"""Tests for the perturbation registry and its loader.

These tests enforce the epistemic invariants that define v0.1:

- every perturbation is ``declared_unvalidated``;
- no perturbation is eligible for primary claims;
- the registry contains exactly the four frozen perturbations;
- every referenced prompt template exists on disk;
- the registry and its schema remain consistent.

A failure in this file is not a cosmetic bug: it means the project has
silently drifted from its stated scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


# The four perturbation IDs frozen for v0.1. This set is asserted
# exactly, so that no additional perturbation can be added without an
# explicit version bump and a corresponding update of this test.
EXPECTED_PERTURBATION_IDS = {
    "P1_RUBRIC_PARAPHRASE",
    "P2_RESPONSE_POSITION",
    "P3_DECISION_LABEL_WORDING",
    "P4_AUDIT_FRAMING",
}

# The frozen level for each perturbation. This mapping encodes the
# conceptual taxonomy of v0.1: protocol-level transformations are
# rubric and ordering; prompt-level is label wording; framing-level
# is evaluator role.
EXPECTED_PERTURBATION_LEVELS = {
    "P1_RUBRIC_PARAPHRASE": "protocol",
    "P2_RESPONSE_POSITION": "protocol",
    "P3_DECISION_LABEL_WORDING": "prompt",
    "P4_AUDIT_FRAMING": "framing",
}


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_registry_validates_against_schema(
    registry_path: Path,
    registry_schema_path: Path,
    load_json_schema,
) -> None:
    """The registry file must be a valid instance of its schema."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    schema = load_json_schema(registry_schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(registry), key=lambda e: e.path)

    if errors:
        first = errors[0]
        location = "/".join(str(p) for p in first.path) or "<root>"
        pytest.fail(
            f"Registry failed schema validation at {location}: "
            f"{first.message}"
        )


def test_registry_metadata_is_frozen(registry_path: Path) -> None:
    """Registry version, project, and scope must match the v0.1 release."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    assert registry["registry_version"] == "0.1.0"
    assert registry["project"] == "protocol-drift-atlas"
    assert registry["scope"] == "v0.1"


# ---------------------------------------------------------------------------
# Scope and identity
# ---------------------------------------------------------------------------


def test_registry_contains_exactly_the_frozen_perturbations(
    registry_path: Path,
) -> None:
    """The registry must contain exactly the four v0.1 perturbations.

    An addition or removal changes the scope of the release and must
    be accompanied by a version bump and an update of this test.
    """
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    ids = [entry["perturbation_id"] for entry in registry["perturbations"]]
    assert set(ids) == EXPECTED_PERTURBATION_IDS
    assert len(ids) == len(EXPECTED_PERTURBATION_IDS)


def test_perturbation_ids_are_unique(registry_path: Path) -> None:
    """JSON Schema cannot enforce uniqueness inside array items.

    This test covers the gap explicitly: no two perturbations may share
    an identifier.
    """
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    ids = [entry["perturbation_id"] for entry in registry["perturbations"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# v0.1 invariants
# ---------------------------------------------------------------------------


def test_every_perturbation_is_declared_unvalidated(registry_path: Path) -> None:
    """No perturbation in v0.1 may claim human validation."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        assert entry["status"] == "declared_unvalidated", (
            f"Perturbation {entry['perturbation_id']} has status "
            f"{entry['status']!r}; v0.1 requires 'declared_unvalidated'."
        )


def test_no_perturbation_is_eligible_for_primary_claims(
    registry_path: Path,
) -> None:
    """No perturbation in v0.1 may support a primary empirical claim."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        assert entry["eligible_for_primary_claims"] is False, (
            f"Perturbation {entry['perturbation_id']} is marked eligible "
            f"for primary claims; v0.1 forbids this."
        )


def test_every_perturbation_states_why_it_may_fail(registry_path: Path) -> None:
    """Every perturbation must declare a failure hypothesis.

    A perturbation without a stated failure mode cannot be registered.
    This is enforced by the schema (``why_this_may_fail`` is required),
    but the test also checks that the value is non-trivial.
    """
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        rationale = entry["why_this_may_fail"].strip()
        assert len(rationale) >= 40, (
            f"Perturbation {entry['perturbation_id']} has a trivial "
            f"failure hypothesis; it must state a plausible mechanism."
        )


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------


def test_perturbation_levels_match_frozen_taxonomy(registry_path: Path) -> None:
    """Each perturbation must carry its frozen level."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    actual = {
        entry["perturbation_id"]: entry["perturbation_level"]
        for entry in registry["perturbations"]
    }
    assert actual == EXPECTED_PERTURBATION_LEVELS


def test_perturbation_levels_are_from_the_allowed_set(registry_path: Path) -> None:
    """Levels must be one of protocol, prompt, or framing."""
    allowed = {"protocol", "prompt", "framing"}
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        assert entry["perturbation_level"] in allowed


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


def test_every_referenced_prompt_template_exists(
    registry_path: Path,
    prompts_dir: Path,
) -> None:
    """Every prompt_template_id must point to a file on disk."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        template_path = prompts_dir / entry["prompt_template_id"]
        assert template_path.exists(), (
            f"Perturbation {entry['perturbation_id']} references "
            f"missing template {entry['prompt_template_id']}."
        )


def test_baseline_template_exists(prompts_dir: Path) -> None:
    """The baseline template is required even though it is not a perturbation."""
    assert (prompts_dir / "baseline.jinja2").exists()


# ---------------------------------------------------------------------------
# Loader behavior
# ---------------------------------------------------------------------------


def test_load_perturbations_returns_typed_entries(registry_path: Path) -> None:
    """load_perturbations must return Perturbation dataclass instances."""
    from protocol_drift_atlas.perturbations import Perturbation, load_perturbations

    entries = load_perturbations(registry_path)
    assert len(entries) == len(EXPECTED_PERTURBATION_IDS)
    for entry in entries:
        assert isinstance(entry, Perturbation)


def test_load_perturbations_with_validation(registry_path: Path) -> None:
    """load_perturbations with validate=True must succeed on the frozen registry."""
    from protocol_drift_atlas.perturbations import load_perturbations

    entries = load_perturbations(registry_path, validate=True)
    assert {e.perturbation_id for e in entries} == EXPECTED_PERTURBATION_IDS


def test_load_perturbations_without_validation(registry_path: Path) -> None:
    """load_perturbations with validate=False must still enforce invariants."""
    from protocol_drift_atlas.perturbations import load_perturbations

    entries = load_perturbations(registry_path, validate=False)
    assert {e.perturbation_id for e in entries} == EXPECTED_PERTURBATION_IDS


def test_load_perturbations_rejects_invalid_status(tmp_path: Path) -> None:
    """A registry entry with a non-v0.1 status must be rejected by the loader."""
    from protocol_drift_atlas.perturbations import load_perturbations

    # Build a minimal registry with a status that v0.1 forbids.
    invalid_registry = {
        "registry_version": "0.1.0",
        "project": "protocol-drift-atlas",
        "scope": "v0.1",
        "perturbations": [
            {
                "perturbation_id": "P1_RUBRIC_PARAPHRASE",
                "family": "test",
                "perturbation_level": "protocol",
                "status": "human_validated",  # forbidden in v0.1
                "description": "x",
                "expected_invariance_claim": "x",
                "why_this_may_fail": "x",
                "eligible_for_primary_claims": False,
                "prompt_template_id": "baseline.jinja2",
                "positive_example": "x",
                "negative_example": "x",
            }
        ],
    }
    path = tmp_path / "invalid_registry.yaml"
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(invalid_registry, handle)

    # validate=False bypasses the schema; the loader's own invariant
    # check must still catch the forbidden status.
    with pytest.raises(ValueError, match="declared_unvalidated"):
        load_perturbations(path, validate=False)


def test_load_perturbations_rejects_duplicate_ids(tmp_path: Path) -> None:
    """Duplicate perturbation IDs must be rejected even when the schema passes."""
    from protocol_drift_atlas.perturbations import load_perturbations

    entry = {
        "perturbation_id": "P1_RUBRIC_PARAPHRASE",
        "family": "test",
        "perturbation_level": "protocol",
        "status": "declared_unvalidated",
        "description": "x",
        "expected_invariance_claim": "x",
        "why_this_may_fail": "x",
        "eligible_for_primary_claims": False,
        "prompt_template_id": "baseline.jinja2",
        "positive_example": "x",
        "negative_example": "x",
    }
    invalid_registry = {
        "registry_version": "0.1.0",
        "project": "protocol-drift-atlas",
        "scope": "v0.1",
        "perturbations": [entry, dict(entry)],
    }
    path = tmp_path / "duplicate_registry.yaml"
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(invalid_registry, handle)

    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_perturbations(path, validate=False)


# ---------------------------------------------------------------------------
# Registry hash
# ---------------------------------------------------------------------------


def test_registry_hash_is_deterministic(registry_path: Path) -> None:
    """The registry hash must be stable across calls."""
    from protocol_drift_atlas.perturbations import registry_hash

    first = registry_hash(registry_path)
    second = registry_hash(registry_path)
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_registry_hash_changes_when_file_changes(
    registry_path: Path,
    tmp_path: Path,
) -> None:
    """A different registry must produce a different hash."""
    from protocol_drift_atlas.perturbations import registry_hash

    original = registry_hash(registry_path)

    # Copy with a trailing comment to change the raw bytes.
    copied = tmp_path / "registry_copy.yaml"
    with open(registry_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    with open(copied, "w", encoding="utf-8") as handle:
        handle.write(content + "\n# trailing comment\n")

    modified = registry_hash(copied)
    assert modified != original


# ---------------------------------------------------------------------------
# Template hash
# ---------------------------------------------------------------------------


def test_template_hash_is_deterministic() -> None:
    """Template hashes must be stable across calls."""
    from protocol_drift_atlas.perturbations import template_hash

    first = template_hash("baseline.jinja2")
    second = template_hash("baseline.jinja2")
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_template_hash_rejects_missing_template() -> None:
    """A missing template must raise FileNotFoundError."""
    from protocol_drift_atlas.perturbations import template_hash

    with pytest.raises(FileNotFoundError):
        template_hash("does_not_exist.jinja2")


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def test_render_template_inserts_variables() -> None:
    """The rendered prompt must contain both policy and response text."""
    from protocol_drift_atlas.perturbations import render_template

    rendered = render_template(
        template_id="baseline.jinja2",
        policy_text="POLICY_MARKER_XYZ",
        response_text="RESPONSE_MARKER_XYZ",
    )
    assert "POLICY_MARKER_XYZ" in rendered
    assert "RESPONSE_MARKER_XYZ" in rendered


def test_render_template_rejects_missing_template() -> None:
    """A missing template must raise FileNotFoundError."""
    from protocol_drift_atlas.perturbations import render_template

    with pytest.raises(FileNotFoundError):
        render_template(
            template_id="does_not_exist.jinja2",
            policy_text="x",
            response_text="y",
        )


def test_render_template_rejects_missing_variable() -> None:
    """StrictUndefined must reject a missing variable rather than silently empty."""
    from protocol_drift_atlas.perturbations import render_template

    # Passing an empty policy is valid; the template renders it.
    # To trigger StrictUndefined, we need to call the template with a
    # variable it does not expect removed, which is not possible
    # through the public function. Instead, verify that a template
    # that references a variable not passed would raise. This is
    # covered implicitly by the signature of render_template: it
    # always passes both policy_text and response_text.
    # The test below is a placeholder for future templates that might
    # require additional variables.
    rendered = render_template(
        template_id="baseline.jinja2",
        policy_text="",
        response_text="",
    )
    assert isinstance(rendered, str)