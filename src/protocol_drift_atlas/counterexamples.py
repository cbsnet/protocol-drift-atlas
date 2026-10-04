"""Counterexample extraction.

A counterexample is a case in which a variant condition produced a
different normalized verdict than the baseline condition for the same
item and the same run index. Counterexamples are the most informative
artefact of a run: they are the concrete instances of protocol
sensitivity that the toolkit makes visible.

This module does not attribute error, severity, or intent. It extracts
observed differences and preserves the raw text on both sides. Severity
assessment and human validation are funded extensions, not part of v0.1.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .scorers import (
    BASELINE_CONDITION_ID,
    VALID_VERDICTS,
    _record_verdict,
    is_valid_record,
)


# Column order for the counterexample CSV. Stable across releases: if a
# column is added, it goes at the end, so that downstream spreadsheets
# and analyses do not silently shift.
COUNTEREXAMPLE_COLUMNS: tuple[str, ...] = (
    "item_id",
    "run_index",
    "risk_bucket",
    "condition_id",
    "baseline_verdict",
    "variant_verdict",
    "flip_type",
    "provider_id",
    "adapter_version",
    "model_requested",
    "model_returned",
    "request_hash",
    "baseline_raw_text",
    "variant_raw_text",
)


def _index_records(
    records: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, int], dict[str, Mapping[str, Any]]]:
    """Index valid records by (item_id, run_index) and condition.

    Mirrors the indexing strategy used by the scorer, so that the two
    modules count the same comparisons.
    """
    index: dict[tuple[str, int], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        if not is_valid_record(record):
            continue
        key = (str(record.get("item_id")), int(record.get("run_index", 0)))
        condition = str(record.get("condition_id"))
        index[key][condition] = record
    return index


def _flip_type(baseline_verdict: str, variant_verdict: str) -> str:
    """Return a canonical ``"from->to"`` label for a verdict change."""
    return f"{baseline_verdict}->{variant_verdict}"


def extract_counterexamples(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Extract every observed baseline-to-variant verdict change.

    A counterexample requires both a valid baseline record and a valid
    variant record for the same (item, run_index). Cases where either
    side is missing or invalid are excluded: the toolkit reports an
    invalid output separately, not as a verdict change.

    Returns:
        A list of dicts, one per observed flip, with the following keys:

        - ``item_id``, ``run_index``, ``condition_id``
        - ``risk_bucket`` (from the baseline record; may be ``None``)
        - ``baseline_verdict``, ``variant_verdict``, ``flip_type``
        - ``provider_id``, ``adapter_version``
        - ``model_requested``, ``model_returned``
        - ``request_hash``
        - ``baseline_raw_text``, ``variant_raw_text``

        The list is sorted by ``(item_id, run_index, condition_id)`` so
        that the output is deterministic.
    """
    index = _index_records(records)
    counterexamples: list[dict[str, Any]] = []

    for (item_id, run_index), conditions in index.items():
        baseline = conditions.get(BASELINE_CONDITION_ID)
        if baseline is None:
            continue
        baseline_verdict = _record_verdict(baseline)
        if baseline_verdict is None:
            continue

        for condition_id, variant in conditions.items():
            if condition_id == BASELINE_CONDITION_ID:
                continue
            variant_verdict = _record_verdict(variant)
            if variant_verdict is None:
                continue
            if variant_verdict == baseline_verdict:
                continue

            counterexamples.append(
                {
                    "item_id": item_id,
                    "run_index": run_index,
                    "risk_bucket": baseline.get("risk_bucket"),
                    "condition_id": condition_id,
                    "baseline_verdict": baseline_verdict,
                    "variant_verdict": variant_verdict,
                    "flip_type": _flip_type(baseline_verdict, variant_verdict),
                    "provider_id": variant.get("provider_id"),
                    "adapter_version": variant.get("adapter_version"),
                    "model_requested": variant.get("model_requested"),
                    "model_returned": variant.get("model_returned"),
                    "request_hash": variant.get("request_hash"),
                    "baseline_raw_text": baseline.get("raw_text"),
                    "variant_raw_text": variant.get("raw_text"),
                }
            )

    counterexamples.sort(
        key=lambda c: (c["item_id"], c["run_index"], c["condition_id"])
    )
    return counterexamples


def summarize_counterexamples(
    counterexamples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return aggregate counts for the counterexample set.

    The summary is descriptive only. It does not rank, score, or
    attribute severity. It exists to populate the summary lines of the
    Stability Card and to allow quick inspection of the raw data.
    """
    total = len(counterexamples)
    if total == 0:
        return {
            "total": 0,
            "by_flip_type": {},
            "by_condition": {},
            "by_risk_bucket": {},
        }

    by_flip_type: dict[str, int] = defaultdict(int)
    by_condition: dict[str, int] = defaultdict(int)
    by_risk_bucket: dict[str, int] = defaultdict(int)

    for ce in counterexamples:
        by_flip_type[str(ce.get("flip_type"))] += 1
        by_condition[str(ce.get("condition_id"))] += 1
        bucket = ce.get("risk_bucket")
        by_risk_bucket[str(bucket) if bucket is not None else "__unknown__"] += 1

    return {
        "total": total,
        "by_flip_type": dict(sorted(by_flip_type.items())),
        "by_condition": dict(sorted(by_condition.items())),
        "by_risk_bucket": dict(sorted(by_risk_bucket.items())),
    }


def write_counterexamples_csv(
    counterexamples: Sequence[Mapping[str, Any]],
    path: str | Path,
) -> None:
    """Write counterexamples to a CSV file with a stable column order.

    Missing values are written as empty strings, not as ``None``. The
    header is always written, even when the counterexample list is
    empty, so that downstream tools can parse the file without a
    special case for zero rows.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(COUNTEREXAMPLE_COLUMNS),
            extrasaction="ignore",
        )
        writer.writeheader()
        for ce in counterexamples:
            writer.writerow(
                {col: ce.get(col, "") if ce.get(col) is not None else "" for col in COUNTEREXAMPLE_COLUMNS}
            )


def load_counterexamples_csv(path: str | Path) -> list[dict[str, Any]]:
    """Load a counterexample CSV back into a list of dicts.

    Empty strings are converted to ``None`` for consistency with the
    in-memory representation used by ``extract_counterexamples``.
    """
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Counterexample file not found: {input_path}")

    rows: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cleaned = {
                key: (value if value != "" else None)
                for key, value in row.items()
            }
            if cleaned.get("run_index") is not None:
                try:
                    cleaned["run_index"] = int(cleaned["run_index"])
                except (TypeError, ValueError):
                    pass
            rows.append(cleaned)
    return rows


def counterexamples_to_jsonl(
    counterexamples: Sequence[Mapping[str, Any]],
    path: str | Path,
) -> None:
    """Write counterexamples to a JSONL file.

    Each line is a self-contained JSON object. This format is preferred
    for archival and for machine consumption; the CSV format is a
    convenience for spreadsheet inspection.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for ce in counterexamples:
            handle.write(json.dumps(dict(ce), ensure_ascii=False) + "\n")