"""Tests for the Stability Card rendering.

The card is the primary public artifact of the toolkit. These tests
verify that:

- the interpretation boundary is always present, in Markdown and JSON;
- forbidden words (certified, validated, guaranteed) do not appear;
- all required sections are rendered when their data is available;
- the JSON round-trip preserves the card structure;
- an empty card (no counterexamples, no directional transitions) is
  rendered without crashing and without hiding the absence of data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    """Minimal schema-valid manifest for reporting tests."""
    return {
        "schema_version": "0.1.0",
        "toolkit": {
            "name": "protocol-drift-atlas",
            "version": "0.1.0",
            "source_revision": None,
        },
        "execution": {
            "run_id": "test-run-0001",
            "timestamp_utc": "2026-10-04T00:00:00+00:00",
            "execution_role": "custom",
        },
        "provider": {
            "provider_id": "mock",
            "adapter_id": "mock",
            "adapter_version": "0.1.0",
            "endpoint_type": None,
        },
        "model": {
            "model_requested": "mock",
            "model_returned": "mock",
        },
        "parameters": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 50,
            "seed_requested": None,
            "seed_supported": False,
            "reproducibility_note": (
                "Repeatability is measured rather than assumed."
            ),
        },
        "protocol": {
            "baseline_protocol_id": "BASELINE_V0_1",
            "prompt_template_id": "baseline.jinja2",
            "prompt_template_hash": "sha256:" + "a" * 64,
            "perturbation_registry_hash": "sha256:" + "b" * 64,
            "perturbation_ids": [
                "P1_RUBRIC_PARAPHRASE",
                "P2_RESPONSE_POSITION",
                "P3_DECISION_LABEL_WORDING",
                "P4_AUDIT_FRAMING",
            ],
        },
        "artifacts": {
            "dataset_id": "pda_demo_corpus_v0_1",
            "dataset_hash": "sha256:" + "c" * 64,
            "response_schema_hash": "sha256:" + "d" * 64,
        },
        "provider_extras": {},
    }


def _record(
    *,
    item_id: str = "ITEM_001",
    run_index: int = 0,
    condition_id: str = "BASELINE_V0_1",
    status: str = "completed",
    verdict: str | None = "safe",
    risk_bucket: str | None = "bucket_a",
) -> dict:
    normalized = verdict if status == "completed" else None
    return {
        "item_id": item_id,
        "run_index": run_index,
        "condition_id": condition_id,
        "status": status,
        "verdict": verdict,
        "normalized_verdict": normalized,
        "risk_bucket": risk_bucket,
        "provider_id": "mock",
        "adapter_version": "0.1.0",
        "model_requested": "mock",
        "model_returned": "mock",
        "request_hash": "sha256:" + "0" * 64,
        "raw_text": "",
    }


BASELINE = "BASELINE_V0_1"
P1 = "P1_RUBRIC_PARAPHRASE"


def _card_with_data() -> dict[str, Any]:
    from protocol_drift_atlas.reporting import build_card

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
        _record(item_id="B", condition_id=BASELINE, verdict="unsafe"),
        _record(item_id="B", condition_id=P1, verdict="safe"),
    ]
    return build_card(
        manifest=_manifest(),
        records=records,
        bootstrap_resamples=100,
        bootstrap_seed=42,
    )


def _empty_card() -> dict[str, Any]:
    from protocol_drift_atlas.reporting import build_card

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),
    ]
    return build_card(
        manifest=_manifest(),
        records=records,
        bootstrap_resamples=100,
        bootstrap_seed=42,
    )


# ---------------------------------------------------------------------------
# Card structure
# ---------------------------------------------------------------------------


def test_card_has_required_top_level_keys() -> None:
    """The card must contain all expected top-level sections."""
    card = _card_with_data()
    for key in (
        "card_version",
        "generated_utc",
        "manifest",
        "metrics",
        "counterexamples_summary",
        "counterexamples",
        "interpretation_boundary",
        "limitations",
    ):
        assert key in card, f"Missing top-level key: {key}"


def test_card_version_is_frozen() -> None:
    """The card version must match the v0.1 release."""
    card = _card_with_data()
    assert card["card_version"] == "0.1.0"


def test_card_manifest_is_embedded_verbatim() -> None:
    """The manifest must be present in the card without modification."""
    manifest = _manifest()
    from protocol_drift_atlas.reporting import build_card

    card = build_card(manifest=manifest, records=[], bootstrap_resamples=50)
    assert card["manifest"]["execution"]["run_id"] == manifest["execution"]["run_id"]
    assert card["manifest"]["model"]["model_requested"] == "mock"


def test_card_contains_interpretation_boundary() -> None:
    """The interpretation boundary must be a non-empty string."""
    from protocol_drift_atlas.reporting import INTERPRETATION_BOUNDARY

    card = _card_with_data()
    assert card["interpretation_boundary"] == INTERPRETATION_BOUNDARY
    assert len(card["interpretation_boundary"]) > 50


def test_card_contains_v0_1_limitations() -> None:
    """The card must carry the standard list of v0.1 limitations."""
    card = _card_with_data()
    limitations = card["limitations"]
    assert isinstance(limitations, list)
    assert any("human" in lim.lower() for lim in limitations)
    assert any("replication" in lim.lower() for lim in limitations)


# ---------------------------------------------------------------------------
# Counterexamples in the card
# ---------------------------------------------------------------------------


def test_card_with_flips_has_counterexamples() -> None:
    """A card built from records with flips must contain them."""
    card = _card_with_data()
    assert card["counterexamples_summary"]["total"] == 2
    assert len(card["counterexamples"]) == 2


def test_card_without_flips_has_empty_counterexamples() -> None:
    """A card with no observed flips must record zero, not omit the field."""
    card = _empty_card()
    assert card["counterexamples_summary"]["total"] == 0
    assert card["counterexamples"] == []


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def test_markdown_contains_title() -> None:
    """The Markdown card must begin with the Exploratory Stability Card title."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    assert "# Exploratory Stability Card" in md


def test_markdown_contains_interpretation_boundary() -> None:
    """The boundary must appear in the Markdown, not only in the JSON."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    assert "Interpretation boundary" in md
    assert "does not establish ground truth" in md.lower()


def test_markdown_contains_all_required_sections() -> None:
    """All sections expected in a populated card must be present."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    required = [
        "## Evaluation identity",
        "## Model configuration",
        "## Execution quality",
        "## Observed stability",
        "## Sensitivity by perturbation",
        "## Observed counterexamples",
        "## Reproducibility",
        "## Interpretation boundary",
        "## Limitations",
    ]
    for section in required:
        assert section in md, f"Missing section: {section}"


def test_markdown_contains_run_id() -> None:
    """The Markdown card must reference the run identifier."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    assert "test-run-0001" in md


def test_markdown_contains_model_name() -> None:
    """The Markdown card must reference the requested model."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    assert "mock" in md


def test_markdown_does_not_contain_forbidden_words() -> None:
    """No overclaim word may appear in the public Markdown."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data()).lower()
    forbidden = [
        "certified",
        "guaranteed",
        "proven safe",
        "validated stability",
        "reliable model",
        "trustworthy model",
        "safety score",
    ]
    for word in forbidden:
        assert word not in md, f"Forbidden word in Markdown: {word}"


def test_markdown_empty_card_notes_absence_of_flips() -> None:
    """When there are no flips, the card must say so explicitly."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_empty_card())
    assert "None observed in this run" in md
    assert "not evidence that the transformation is invariant" in md


def test_markdown_with_flips_lists_breakdowns() -> None:
    """When flips exist, the card must include their by-type and by-condition breakdowns."""
    from protocol_drift_atlas.reporting import render_markdown

    md = render_markdown(_card_with_data())
    assert "By transition type" in md
    assert "By perturbation" in md


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_card_json_round_trip(tmp_path: Path) -> None:
    """A card written to JSON and read back must preserve its structure."""
    from protocol_drift_atlas.reporting import (
        build_card,
        load_card,
        write_card,
    )

    card = build_card(manifest=_manifest(), records=[], bootstrap_resamples=50)
    md_path = tmp_path / "card.md"
    json_path = tmp_path / "card.json"
    write_card(card, markdown_path=md_path, json_path=json_path)

    reloaded = load_card(json_path)
    assert reloaded["card_version"] == card["card_version"]
    assert reloaded["interpretation_boundary"] == card["interpretation_boundary"]
    assert reloaded["manifest"]["execution"]["run_id"] == "test-run-0001"


def test_write_card_creates_both_files(tmp_path: Path) -> None:
    """write_card must produce both Markdown and JSON outputs."""
    from protocol_drift_atlas.reporting import build_card, write_card

    card = build_card(manifest=_manifest(), records=[], bootstrap_resamples=50)
    md_path = tmp_path / "card.md"
    json_path = tmp_path / "card.json"
    write_card(card, markdown_path=md_path, json_path=json_path)

    assert md_path.exists()
    assert json_path.exists()
    assert md_path.read_text(encoding="utf-8").startswith("# Exploratory Stability Card")


def test_load_card_rejects_non_object(tmp_path: Path) -> None:
    """A JSON file that is not an object must be rejected."""
    from protocol_drift_atlas.reporting import load_card

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_card(invalid)


# ---------------------------------------------------------------------------
# JSON schema shape
# ---------------------------------------------------------------------------


def test_card_json_is_serializable() -> None:
    """The card must be JSON-serializable without custom encoders."""
    card = _card_with_data()
    serialized = json.dumps(card, sort_keys=True)
    deserialized = json.loads(serialized)
    assert deserialized["card_version"] == "0.1.0"


def test_card_metrics_have_expected_structure() -> None:
    """The metrics block must expose the three expected groups."""
    card = _card_with_data()
    metrics = card["metrics"]
    assert set(metrics.keys()) == {
        "execution_quality",
        "baseline_variant_agreement",
        "baseline_run_agreement",
    }