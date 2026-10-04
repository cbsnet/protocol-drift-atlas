"""Tests for counterexample extraction and serialization.

A counterexample is an observed verdict change between the baseline
condition and a variant condition, on the same item and the same run.
These tests verify that:

- only valid records produce counterexamples;
- flips are classified with the correct directional label;
- the output is deterministic and stably ordered;
- the CSV round-trip preserves all information;
- the summary counts are accurate.
"""

from __future__ import annotations

from pathlib import Path

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
    raw_text: str | None = None,
    request_hash: str | None = None,
) -> dict:
    normalized = verdict if status == "completed" else None
    if raw_text is None:
        raw_text = f'{{"verdict": "{verdict}"}}' if verdict else ""
    if request_hash is None:
        request_hash = f"sha256:{'0' * 60}{run_index:02d}"
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
        "request_hash": request_hash,
        "raw_text": raw_text,
    }


BASELINE = "BASELINE_V0_1"
P1 = "P1_RUBRIC_PARAPHRASE"
P2 = "P2_RESPONSE_POSITION"
P4 = "P4_AUDIT_FRAMING"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_extraction_on_empty_input() -> None:
    """An empty record list must produce an empty counterexample list."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    assert extract_counterexamples([]) == []


def test_extraction_ignores_agreement() -> None:
    """When baseline and variant agree, no counterexample is produced."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="safe"),
        _record(condition_id=P1, verdict="safe"),
    ]
    assert extract_counterexamples(records) == []


def test_extraction_detects_safe_to_unsafe_flip() -> None:
    """A safe baseline with an unsafe variant must produce one counterexample."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="safe"),
        _record(condition_id=P1, verdict="unsafe"),
    ]
    counterexamples = extract_counterexamples(records)
    assert len(counterexamples) == 1
    ce = counterexamples[0]
    assert ce["item_id"] == "ITEM_001"
    assert ce["condition_id"] == P1
    assert ce["baseline_verdict"] == "safe"
    assert ce["variant_verdict"] == "unsafe"
    assert ce["flip_type"] == "safe->unsafe"


def test_extraction_detects_unsafe_to_safe_flip() -> None:
    """The reverse direction must be recorded distinctly."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="unsafe"),
        _record(condition_id=P2, verdict="safe"),
    ]
    counterexamples = extract_counterexamples(records)
    assert len(counterexamples) == 1
    assert counterexamples[0]["flip_type"] == "unsafe->safe"


def test_extraction_detects_indeterminate_transitions() -> None:
    """Transitions involving indeterminate must be recorded."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P4, verdict="indeterminate"),
        _record(item_id="B", condition_id=BASELINE, verdict="indeterminate"),
        _record(item_id="B", condition_id=P4, verdict="safe"),
    ]
    counterexamples = extract_counterexamples(records)
    types = sorted(ce["flip_type"] for ce in counterexamples)
    assert types == ["indeterminate->safe", "safe->indeterminate"]


def test_extraction_skips_invalid_records() -> None:
    """An invalid_output on a variant must not produce a counterexample."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="safe"),
        _record(condition_id=P1, status="invalid_output"),
    ]
    assert extract_counterexamples(records) == []


def test_extraction_requires_baseline() -> None:
    """A variant without a baseline must not produce a counterexample."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=P1, verdict="unsafe"),
    ]
    assert extract_counterexamples(records) == []


def test_extraction_handles_multiple_variants_per_item() -> None:
    """Each variant condition produces its own counterexample."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="safe"),
        _record(condition_id=P1, verdict="unsafe"),
        _record(condition_id=P2, verdict="indeterminate"),
        _record(condition_id=P4, verdict="safe"),  # agreement, no CE
    ]
    counterexamples = extract_counterexamples(records)
    assert len(counterexamples) == 2
    conditions = sorted(ce["condition_id"] for ce in counterexamples)
    assert conditions == [P1, P2]


def test_extraction_separates_runs() -> None:
    """The same item in different runs produces independent counterexamples."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(item_id="A", run_index=0, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=0, condition_id=P1, verdict="unsafe"),
        _record(item_id="A", run_index=1, condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", run_index=1, condition_id=P1, verdict="unsafe"),
    ]
    counterexamples = extract_counterexamples(records)
    assert len(counterexamples) == 2
    assert {ce["run_index"] for ce in counterexamples} == {0, 1}


def test_extraction_preserves_raw_text() -> None:
    """The raw text of both baseline and variant must be preserved."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(condition_id=BASELINE, verdict="safe",
                raw_text='{"verdict": "safe", "brief_rationale": "ok"}'),
        _record(condition_id=P1, verdict="unsafe",
                raw_text='{"verdict": "unsafe", "brief_rationale": "bad"}'),
    ]
    ce = extract_counterexamples(records)[0]
    assert "safe" in ce["baseline_raw_text"]
    assert "unsafe" in ce["variant_raw_text"]


def test_extraction_is_sorted_deterministically() -> None:
    """The output order must be stable across shuffled inputs."""
    from protocol_drift_atlas.counterexamples import extract_counterexamples

    records = [
        _record(item_id="B", condition_id=BASELINE, verdict="safe"),
        _record(item_id="B", condition_id=P1, verdict="unsafe"),
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P2, verdict="unsafe"),
        _record(item_id="C", condition_id=BASELINE, verdict="safe"),
        _record(item_id="C", condition_id=P4, verdict="unsafe"),
    ]
    forward = extract_counterexamples(records)
    backward = extract_counterexamples(list(reversed(records)))
    assert forward == backward


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_on_empty_input() -> None:
    """An empty counterexample list must produce zeroed summary."""
    from protocol_drift_atlas.counterexamples import summarize_counterexamples

    summary = summarize_counterexamples([])
    assert summary["total"] == 0
    assert summary["by_flip_type"] == {}
    assert summary["by_condition"] == {}
    assert summary["by_risk_bucket"] == {}


def test_summary_counts_by_flip_type() -> None:
    """Transitions must be counted by their directional label."""
    from protocol_drift_atlas.counterexamples import summarize_counterexamples

    counterexamples = [
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": "a"},
        {"flip_type": "safe->unsafe", "condition_id": P2, "risk_bucket": "a"},
        {"flip_type": "unsafe->safe", "condition_id": P4, "risk_bucket": "b"},
    ]
    summary = summarize_counterexamples(counterexamples)
    assert summary["total"] == 3
    assert summary["by_flip_type"]["safe->unsafe"] == 2
    assert summary["by_flip_type"]["unsafe->safe"] == 1


def test_summary_counts_by_condition() -> None:
    """Each perturbation must be counted separately."""
    from protocol_drift_atlas.counterexamples import summarize_counterexamples

    counterexamples = [
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": "a"},
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": "a"},
        {"flip_type": "safe->unsafe", "condition_id": P2, "risk_bucket": "a"},
    ]
    summary = summarize_counterexamples(counterexamples)
    assert summary["by_condition"][P1] == 2
    assert summary["by_condition"][P2] == 1


def test_summary_counts_by_risk_bucket() -> None:
    """Risk buckets with no value are counted under a stable placeholder."""
    from protocol_drift_atlas.counterexamples import summarize_counterexamples

    counterexamples = [
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": "a"},
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": None},
        {"flip_type": "safe->unsafe", "condition_id": P1, "risk_bucket": "b"},
    ]
    summary = summarize_counterexamples(counterexamples)
    assert summary["by_risk_bucket"]["a"] == 1
    assert summary["by_risk_bucket"]["b"] == 1
    assert summary["by_risk_bucket"]["__unknown__"] == 1


# ---------------------------------------------------------------------------
# CSV round-trip
# ---------------------------------------------------------------------------


def test_csv_round_trip_preserves_records(tmp_path: Path) -> None:
    """Writing and reading back must produce the same data."""
    from protocol_drift_atlas.counterexamples import (
        extract_counterexamples,
        load_counterexamples_csv,
        write_counterexamples_csv,
    )

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
        _record(item_id="B", condition_id=BASELINE, verdict="unsafe"),
        _record(item_id="B", condition_id=P2, verdict="safe"),
    ]
    counterexamples = extract_counterexamples(records)

    csv_path = tmp_path / "ces.csv"
    write_counterexamples_csv(counterexamples, csv_path)
    reloaded = load_counterexamples_csv(csv_path)

    assert len(reloaded) == len(counterexamples)
    # Compare on a stable subset of fields.
    for original, back in zip(counterexamples, reloaded):
        for field in ("item_id", "condition_id", "flip_type"):
            assert back[field] == original[field]


def test_csv_is_written_with_header_even_when_empty(tmp_path: Path) -> None:
    """An empty counterexample list must still produce a CSV with a header."""
    from protocol_drift_atlas.counterexamples import write_counterexamples_csv

    csv_path = tmp_path / "empty.csv"
    write_counterexamples_csv([], csv_path)
    content = csv_path.read_text(encoding="utf-8")
    first_line = content.splitlines()[0]
    assert "item_id" in first_line
    assert "flip_type" in first_line


def test_csv_column_order_is_stable(tmp_path: Path) -> None:
    """The CSV header must match the frozen column order."""
    from protocol_drift_atlas.counterexamples import (
        COUNTEREXAMPLE_COLUMNS,
        write_counterexamples_csv,
    )

    csv_path = tmp_path / "col_order.csv"
    write_counterexamples_csv([], csv_path)
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == list(COUNTEREXAMPLE_COLUMNS)


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------


def test_jsonl_output_is_one_object_per_line(tmp_path: Path) -> None:
    """Each counterexample must be serialized as a single JSON object."""
    import json

    from protocol_drift_atlas.counterexamples import (
        counterexamples_to_jsonl,
        extract_counterexamples,
    )

    records = [
        _record(item_id="A", condition_id=BASELINE, verdict="safe"),
        _record(item_id="A", condition_id=P1, verdict="unsafe"),
    ]
    counterexamples = extract_counterexamples(records)
    jsonl_path = tmp_path / "ces.jsonl"
    counterexamples_to_jsonl(counterexamples, jsonl_path)

    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["flip_type"] == "safe->unsafe"


def test_jsonl_output_empty_when_no_counterexamples(tmp_path: Path) -> None:
    """An empty counterexample list must produce an empty JSONL file."""
    from protocol_drift_atlas.counterexamples import counterexamples_to_jsonl

    jsonl_path = tmp_path / "empty.jsonl"
    counterexamples_to_jsonl([], jsonl_path)
    assert jsonl_path.read_text(encoding="utf-8") == ""