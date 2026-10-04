"""Tests for the scoring layer.

The scorer is the analytical core of the toolkit. These tests use
synthetic records with known properties, so that every metric can be
verified against hand-computed expectations.

The tests are organized by metric:

- execution quality: coverage, invalid output rate, provider error rate;
- baseline-variant agreement: agreement rate, any-flip rate,
  directional transitions, breakdowns by perturbation and risk bucket;
- baseline run agreement: repeatability of the baseline condition;
- bootstrap intervals: determinism, coverage, and degenerate behavior.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(
    *,
    item_id: str = "ITEM_001",
    run_index: int = 0,
    condition_id: str = "BASELINE_V0_1",
    status: str = "completed",
    verdict: str | None = "safe",
    risk_bucket: str | None = "bucket_a",
) -> dict:
    """Minimal record for scoring tests.

    This helper does not use the conftest ``make_record`` fixture so
    that this file can be read independently. It builds the exact
    shape of a runner record, with only the fields the scorer reads.
    """
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
P2 = "P2_RESPONSE_POSITION"
P3 = "P3_DECISION_LABEL_WORDING"
P4 = "P4_AUDIT_FRAMING"


# ---------------------------------------------------------------------------
# Execution quality
# ---------------------------------------------------------------------------


def test_execution_quality_on_empty_input() -> None:
    """An empty record list must produce zeroed metrics, not crash."""
    from protocol_drift_atlas.scorers import execution_quality_metrics

    metrics = execution_quality_metrics([])
    assert metrics["total_records"] == 0
    assert metrics["valid_records"] == 0
    assert metrics["valid_response_coverage"] == 0.0
    assert metrics["invalid_output_rate"] == 0.0
    assert metrics["provider_error_rate"] == 0.0


def test_execution_quality_all_valid() -> None:
    """When all records are valid, coverage is 1 and error rates are 0."""
    from protocol_drift_atlas.scorers import execution_quality_metrics

    records = [
        _record(condition_id=BASELINE, verdict="safe"),
        _record(condition_id=P1, verdict="unsafe"),
    ]
    metrics = execution_quality_metrics(records)
    assert metrics["total_records"] == 2
    assert metrics["valid_records"] == 2
    assert metrics["valid_response_coverage"] == 1.0
    assert metrics["invalid_output_rate"] == 0.0
    assert metrics["provider_error_rate"] == 0.0


def test_execution_quality_mixed_outcomes() -> None:
    """Each failure category must be counted exactly once."""
    from protocol_drift_atlas.scorers import execution_quality_metrics

    records = [
        _record(status="completed", verdict="safe"),
        _record(status="invalid_output"),
        _record(status="provider_error"),
        _record(status="timeout"),
    ]
    metrics = execution_quality_metrics(records)
    assert metrics["total_records"] == 4
    assert metrics["valid_records"] == 1
    assert metrics["valid_response_coverage"] == 0.25
    assert metrics["invalid_output_rate"] == 0.25
    assert metrics["provider_error_rate"] == 0.25
    assert metrics["timeout_rate"] == 0.25


def test_execution_quality_counts_cache_hits() -> None:
    """Cache hits must be counted as a fraction of total records."""
    from protocol_drift_atlas.scorers import execution_quality_metrics

    records = [
        {**_record(verdict="safe"), "cache_hit": True},
        {**_record(verdict="safe"), "cache_hit": False},
    ]
    metrics = execution_quality_metrics(records)
    assert metrics["cache_hit_rate"] == 0.5


# ---------------------------------------------------------------------------
# Baseline-variant agreement
# ---------------------------------------------------------------------------


def test_agreement_on_empty_input() -> None:
    """An empty record list must produce a zeroed agreement block."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    result = baseline_variant_agreement([])
    assert result["comparisons"] == 0
    assert result["agreement_rate"] == 0.0
    assert result["any_flip_rate"] == 0.0
    assert result["directional_transitions"] == {}
    assert result["by_perturbation"] == {}
    assert result["by_risk_bucket"] == {}


def test_full_agreement() -> None:
    """When every variant matches the baseline, agreement is 1 and flip is 0."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),
        _record(item_id="A", condition_id=P2, verdict="safe"),
        _record(item_id="A", condition_id=P3, verdict="safe"),
        _record(item_id="A", condition_id=P4, verdict="safe"),
    ]
    result = baseline_variant_agreement(records)
    assert result["comparisons"] == 4
    assert result["agreement_rate"] == 1.0
    assert result["any_flip_rate"] == 0.0
    assert result["directional_transitions"] == {}


def test_full_disagreement() -> None:
    """When every variant differs, agreement is 0 and flip is 1."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
    ]
    result = baseline_variant_agreement(records)
    assert result["comparisons"] == 1
    assert result["agreement_rate"] == 0.0
    assert result["any_flip_rate"] == 1.0
    assert result["directional_transitions"] == {"safe->unsafe": 1}


def test_mixed_agreement() -> None:
    """A balanced mix must produce a fraction of 0.5."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),   # agree
        _record(item_id="A", condition_id=P2, verdict="unsafe"), # flip
        _record(item_id="B", condition_id=BASELINE, verdict="unsafe"),
        _record(item_id="B", condition_id=P1, verdict="unsafe"), # agree
        _record(item_id="B", condition_id=P2, verdict="safe"),   # flip
    ]
    result = baseline_variant_agreement(records)
    assert result["comparisons"] == 4
    assert result["agreement_rate"] == 0.5
    assert result["any_flip_rate"] == 0.5


def test_directional_transitions_are_counted_separately() -> None:
    """safe->unsafe and unsafe->safe must be distinct categories."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
        _record(item_id="B", condition_id=BASELINE, verdict="unsafe"),
        _record(item_id="B", condition_id=P1, verdict="safe"),
    ]
    result = baseline_variant_agreement(records)
    transitions = result["directional_transitions"]
    assert transitions.get("safe->unsafe") == 1
    assert transitions.get("unsafe->safe") == 1


def test_indeterminate_transitions_are_counted() -> None:
    """Transitions involving indeterminate must appear in the directional table."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P4, verdict="indeterminate"),
        _record(item_id="B", condition_id=BASELINE, verdict="indeterminate"),
        _record(item_id="B", condition_id=P4, verdict="safe"),
    ]
    result = baseline_variant_agreement(records)
    transitions = result["directional_transitions"]
    assert transitions.get("safe->indeterminate") == 1
    assert transitions.get("indeterminate->safe") == 1


def test_invalid_records_are_excluded_from_agreement() -> None:
    """A record with invalid output must not enter the agreement denominator."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, status="invalid_output"),
        _record(item_id="A", condition_id=P2, verdict="safe"),
    ]
    result = baseline_variant_agreement(records)
    # Only P2 is a valid comparison; P1 is excluded entirely.
    assert result["comparisons"] == 1
    assert result["agreement_rate"] == 1.0


def test_missing_baseline_excludes_comparisons() -> None:
    """A variant without a baseline must not contribute to any metric."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
        _record(item_id="A", condition_id=P2, verdict="safe"),
    ]
    result = baseline_variant_agreement(records)
    assert result["comparisons"] == 0
    assert result["agreement_rate"] == 0.0


def test_comparisons_separate_runs() -> None:
    """Two runs of the same item are counted as independent comparisons."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=0, condition_id=P1, verdict="unsafe"),
        _record(item_id="A", run_index=1, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=1, condition_id=P1, verdict="unsafe"),
    ]
    result = baseline_variant_agreement(records)
    assert result["comparisons"] == 2
    assert result["any_flip_rate"] == 1.0


# ---------------------------------------------------------------------------
# Breakdowns
# ---------------------------------------------------------------------------


def test_breakdown_by_perturbation() -> None:
    """Each perturbation must be reported with its own comparisons count."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),
        _record(item_id="A", condition_id=P2, verdict="unsafe"),
    ]
    result = baseline_variant_agreement(records)
    by_pert = result["by_perturbation"]
    assert by_pert[P1]["comparisons"] == 1
    assert by_pert[P1]["agreement_rate"] == 1.0
    assert by_pert[P2]["comparisons"] == 1
    assert by_pert[P2]["agreement_rate"] == 0.0


def test_breakdown_by_risk_bucket() -> None:
    """Each risk bucket must be reported with its own comparisons count."""
    from protocol_drift_atlas.scorers import baseline_variant_agreement

    records = [
        _record(item_id="A", condition_id=BASELINE,
                verdict="safe", risk_bucket="bucket_a"),
        _record(item_id="A", condition_id=P1,
                verdict="safe", risk_bucket="bucket_a"),
        _record(item_id="B", condition_id=BASELINE,
                verdict="safe", risk_bucket="bucket_b"),
        _record(item_id="B", condition_id=P1,
                verdict="unsafe", risk_bucket="bucket_b"),
    ]
    result = baseline_variant_agreement(records)
    by_bucket = result["by_risk_bucket"]
    assert by_bucket["bucket_a"]["comparisons"] == 1
    assert by_bucket["bucket_a"]["agreement_rate"] == 1.0
    assert by_bucket["bucket_b"]["comparisons"] == 1
    assert by_bucket["bucket_b"]["agreement_rate"] == 0.0


# ---------------------------------------------------------------------------
# Baseline run agreement
# ---------------------------------------------------------------------------


def test_baseline_run_agreement_on_empty_input() -> None:
    """An empty input must produce zero eligible items."""
    from protocol_drift_atlas.scorers import baseline_run_agreement

    result = baseline_run_agreement([])
    assert result["items_with_multiple_runs"] == 0
    assert result["agreement_rate"] == 0.0


def test_baseline_run_agreement_requires_multiple_runs() -> None:
    """An item with a single baseline run is not eligible."""
    from protocol_drift_atlas.scorers import baseline_run_agreement

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
    ]
    result = baseline_run_agreement(records)
    assert result["items_with_multiple_runs"] == 0


def test_baseline_run_agreement_full() -> None:
    """Two identical baseline runs on every item must produce agreement 1."""
    from protocol_drift_atlas.scorers import baseline_run_agreement

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=1, condition_id=BASELINE, verdict="safe"),
        _record(item_id="B", run_index=0, condition_id=BASELINE, verdict="unsafe"),
        _record(item_id="B", run_index=1, condition_id=BASELINE, verdict="unsafe"),
    ]
    result = baseline_run_agreement(records)
    assert result["items_with_multiple_runs"] == 2
    assert result["agreement_rate"] == 1.0


def test_baseline_run_agreement_partial() -> None:
    """A single item with disagreeing runs must reduce the rate."""
    from protocol_drift_atlas.scorers import baseline_run_agreement

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=1, condition_id=BASELINE, verdict="safe"),
        _record(item_id="B", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="B", run_index=1, condition_id=BASELINE, verdict="unsafe"),
    ]
    result = baseline_run_agreement(records)
    assert result["items_with_multiple_runs"] == 2
    assert result["agreement_rate"] == 0.5


def test_baseline_run_agreement_ignores_variant_conditions() -> None:
    """Runs of a perturbation must not contribute to baseline agreement."""
    from protocol_drift_atlas.scorers import baseline_run_agreement

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=1, condition_id=BASELINE, verdict="safe"),
        # Variant records, different runs, must be ignored.
        _record(item_id="A", run_index=0, condition_id=P1, verdict="unsafe"),
        _record(item_id="A", run_index=1, condition_id=P1, verdict="unsafe"),
    ]
    result = baseline_run_agreement(records)
    assert result["items_with_multiple_runs"] == 1
    assert result["agreement_rate"] == 1.0


# ---------------------------------------------------------------------------
# Bootstrap intervals
# ---------------------------------------------------------------------------


def test_bootstrap_interval_is_deterministic() -> None:
    """The same input and seed must produce the same interval."""
    from protocol_drift_atlas.scorers import bootstrap_interval

    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    first = bootstrap_interval(values, seed=42)
    second = bootstrap_interval(values, seed=42)
    assert first == second


def test_bootstrap_interval_on_degenerate_input() -> None:
    """When all values are identical, the interval collapses."""
    from protocol_drift_atlas.scorers import bootstrap_interval

    values = [1.0] * 20
    low, high = bootstrap_interval(values, seed=42)
    assert low == high == 1.0


def test_bootstrap_interval_on_empty_input() -> None:
    """An empty list must produce (0.0, 0.0), not crash."""
    from protocol_drift_atlas.scorers import bootstrap_interval

    assert bootstrap_interval([]) == (0.0, 0.0)


def test_bootstrap_interval_contains_sample_mean() -> None:
    """The point estimate must lie inside the interval."""
    from protocol_drift_atlas.scorers import bootstrap_interval

    values = [1.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0]
    mean = sum(values) / len(values)
    low, high = bootstrap_interval(values, seed=42)
    assert low <= mean <= high


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------


def test_compute_metrics_shape() -> None:
    """compute_metrics must return the three expected top-level groups."""
    from protocol_drift_atlas.scorers import compute_metrics

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),
    ]
    metrics = compute_metrics(records, bootstrap_resamples=100, bootstrap_seed=42)
    assert set(metrics.keys()) == {
        "execution_quality",
        "baseline_variant_agreement",
        "baseline_run_agreement",
    }


def test_compute_metrics_attaches_bootstrap_intervals() -> None:
    """Agreement and flip rates must carry a 95% bootstrap interval."""
    from protocol_drift_atlas.scorers import compute_metrics

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="safe"),
        _record(item_id="A", condition_id=P2, verdict="unsafe"),
    ]
    metrics = compute_metrics(records, bootstrap_resamples=100, bootstrap_seed=42)
    agreement = metrics["baseline_variant_agreement"]
    assert "agreement_rate_ci95" in agreement
    assert "any_flip_rate_ci95" in agreement
    assert len(agreement["agreement_rate_ci95"]) == 2


def test_compute_metrics_empty_input() -> None:
    """compute_metrics on an empty list must not crash."""
    from protocol_drift_atlas.scorers import compute_metrics

    metrics = compute_metrics([])
    assert metrics["execution_quality"]["total_records"] == 0
    assert metrics["baseline_variant_agreement"]["comparisons"] == 0