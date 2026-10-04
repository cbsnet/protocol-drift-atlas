"""Stability Card generation.

This module produces the Exploratory Stability Card in two formats:

- Markdown: the human-readable artefact, designed to be scannable in
  under a minute and to carry the interpretation boundary prominently.
- JSON: the machine-readable artefact, designed to be archived alongside
  the run file and the execution manifest.

The card is the primary public output of a run. It reports observed
sensitivity, not model safety. Every card carries the same interpretation
boundary and the same list of v0.1 limitations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .counterexamples import (
    extract_counterexamples,
    summarize_counterexamples,
)
from .scorers import compute_metrics


# The interpretation boundary is a constant. It appears verbatim in every
# Markdown card and in every JSON card. Tests assert its presence.
INTERPRETATION_BOUNDARY: str = (
    "This card reports observed changes in model judgments under declared, "
    "unvalidated protocol perturbations. It does not establish ground truth, "
    "semantic invariance, error severity, model safety, or model reliability "
    "outside the stated setup."
)


# v0.1 limitations. These are factual statements about the scope of the
# release, not hedges. They must appear in every card.
V0_1_LIMITATIONS: tuple[str, ...] = (
    "No human-adjudicated safety labels.",
    "No human validation of perturbation invariance.",
    "Small, non-representative demonstration corpus.",
    "No external replication.",
    "No multilingual coverage.",
    "Results may vary across model versions, providers, parameters, and time.",
    "Hosted provider availability, model identifiers, and pricing may change "
    "without notice.",
)


# Words that must not appear in the Markdown card without an explicit,
# evidence-based justification. v0.1 has none, so the check is enforced by
# a test rather than by this module at runtime.
FORBIDDEN_CARD_WORDS: tuple[str, ...] = (
    "certified",
    "validated stability",
    "human-validated",
    "safety score",
    "reliable model",
    "trustworthy model",
    "guaranteed",
    "proven safe",
)


# ---------------------------------------------------------------------------
# Card construction
# ---------------------------------------------------------------------------


def build_card(
    *,
    manifest: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    bootstrap_resamples: int = 1000,
    bootstrap_seed: int = 12345,
) -> dict[str, Any]:
    """Build the full Stability Card as a JSON-serializable dict.

    The card embeds:

    - the execution manifest, verbatim;
    - the computed metrics;
    - the counterexample summary;
    - the counterexample list;
    - the interpretation boundary;
    - the v0.1 limitations.

    The card does not contain the raw run records. Those live in the
    JSONL file referenced by the manifest. The card is a summary, not a
    mirror of the run.
    """
    metrics = compute_metrics(
        records,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    counterexamples = extract_counterexamples(records)
    counterexamples_summary = summarize_counterexamples(counterexamples)

    return {
        "card_version": "0.1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": dict(manifest),
        "metrics": metrics,
        "counterexamples_summary": counterexamples_summary,
        "counterexamples": counterexamples,
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
        "limitations": list(V0_1_LIMITATIONS),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _fmt_ci(ci: Sequence[float] | None) -> str:
    if not ci or len(ci) != 2:
        return "n/a"
    low, high = ci
    return f"[{low:.3f}, {high:.3f}]"


def _fmt_count(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def render_markdown(card: Mapping[str, Any]) -> str:
    """Render a Stability Card as Markdown.

    The layout is deliberate: identity first, then primary results, then
    sensitivity breakdowns, then counterexamples, then interpretation
    boundary and limitations. A reader who stops after the primary
    results table will have seen the numbers and the context in which
    they were produced.
    """
    manifest = card["manifest"]
    metrics = card["metrics"]
    quality = metrics["execution_quality"]
    agreement = metrics["baseline_variant_agreement"]
    run_agreement = metrics["baseline_run_agreement"]
    ce_summary = card["counterexamples_summary"]

    lines: list[str] = []

    # Title and interpretation boundary first: the reader must see the
    # boundary before the numbers, not after.
    lines.append("# Exploratory Stability Card")
    lines.append("")
    lines.append(f"> {card['interpretation_boundary']}")
    lines.append("")

    # --- Identity ---
    lines.append("## Evaluation identity")
    lines.append("")
    lines.append(f"- Evaluation ID: `{manifest['execution']['run_id']}`")
    lines.append(f"- Toolkit version: `{manifest['toolkit']['version']}`")
    lines.append(f"- Timestamp (UTC): `{manifest['execution']['timestamp_utc']}`")
    lines.append(f"- Execution role: `{manifest['execution']['execution_role']}`")
    lines.append(f"- Dataset ID: `{manifest['artifacts']['dataset_id']}`")
    lines.append(f"- Dataset hash: `{manifest['artifacts']['dataset_hash']}`")
    lines.append(
        f"- Prompt template hash: `{manifest['protocol']['prompt_template_hash']}`"
    )
    lines.append(
        f"- Perturbation registry hash: "
        f"`{manifest['protocol']['perturbation_registry_hash']}`"
    )
    lines.append("")

    # --- Model configuration ---
    lines.append("## Model configuration")
    lines.append("")
    lines.append(f"- Provider: `{manifest['provider']['provider_id']}`")
    lines.append(
        f"- Adapter: `{manifest['provider']['adapter_id']}` "
        f"({manifest['provider']['adapter_version']})"
    )
    lines.append(f"- Model requested: `{manifest['model']['model_requested']}`")
    lines.append(
        f"- Model returned: "
        f"`{manifest['model']['model_returned'] or 'n/a'}`"
    )
    lines.append(f"- Temperature: {manifest['parameters']['temperature']}")
    lines.append(f"- Top-p: {manifest['parameters']['top_p']}")
    lines.append(
        f"- Max output tokens: {manifest['parameters']['max_output_tokens']}"
    )
    lines.append("")

    # --- Execution quality (first, because agreement depends on it) ---
    lines.append("## Execution quality")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total records | {quality['total_records']} |")
    lines.append(f"| Valid records | {quality['valid_records']} |")
    lines.append(
        f"| Valid response coverage | {_fmt_rate(quality['valid_response_coverage'])} |"
    )
    lines.append(
        f"| Invalid output rate | {_fmt_rate(quality['invalid_output_rate'])} |"
    )
    lines.append(
        f"| Provider error rate | {_fmt_rate(quality['provider_error_rate'])} |"
    )
    lines.append(f"| Timeout rate | {_fmt_rate(quality['timeout_rate'])} |")
    lines.append(f"| Cache hit rate | {_fmt_rate(quality['cache_hit_rate'])} |")
    lines.append("")

    # --- Primary results ---
    lines.append("## Observed stability")
    lines.append("")
    lines.append("| Metric | Estimate | 95% bootstrap interval |")
    lines.append("|---|---:|---:|")
    lines.append(
        f"| Baseline–variant agreement rate | "
        f"{_fmt_rate(agreement['agreement_rate'])} | "
        f"{_fmt_ci(agreement.get('agreement_rate_ci95'))} |"
    )
    lines.append(
        f"| Any-flip rate | {_fmt_rate(agreement['any_flip_rate'])} | "
        f"{_fmt_ci(agreement.get('any_flip_rate_ci95'))} |"
    )
    lines.append(
        f"| Baseline run agreement | "
        f"{_fmt_rate(run_agreement['agreement_rate'])} | n/a |"
    )
    lines.append(f"| Comparisons | {agreement['comparisons']} | n/a |")
    lines.append(
        f"| Items with multiple baseline runs | "
        f"{run_agreement['items_with_multiple_runs']} | n/a |"
    )
    lines.append("")

    # --- Sensitivity by perturbation ---
    by_perturbation = agreement.get("by_perturbation") or {}
    if by_perturbation:
        lines.append("## Sensitivity by perturbation")
        lines.append("")
        lines.append("| Perturbation | Comparisons | Agreement rate | Any-flip rate |")
        lines.append("|---|---:|---:|---:|")
        for pid in sorted(by_perturbation.keys()):
            entry = by_perturbation[pid]
            lines.append(
                f"| `{pid}` | {entry['comparisons']} | "
                f"{_fmt_rate(entry['agreement_rate'])} | "
                f"{_fmt_rate(entry['any_flip_rate'])} |"
            )
        lines.append("")

    # --- Sensitivity by risk bucket ---
    by_bucket = agreement.get("by_risk_bucket") or {}
    if by_bucket:
        lines.append("## Sensitivity by risk bucket")
        lines.append("")
        lines.append("| Risk bucket | Comparisons | Agreement rate | Any-flip rate |")
        lines.append("|---|---:|---:|---:|")
        for bucket in sorted(by_bucket.keys()):
            entry = by_bucket[bucket]
            lines.append(
                f"| `{bucket}` | {entry['comparisons']} | "
                f"{_fmt_rate(entry['agreement_rate'])} | "
                f"{_fmt_rate(entry['any_flip_rate'])} |"
            )
        lines.append("")

    # --- Directional transitions ---
    directional = agreement.get("directional_transitions") or {}
    if directional:
        lines.append("## Directional transitions")
        lines.append("")
        lines.append("| Transition | Count |")
        lines.append("|---|---:|")
        for key in sorted(directional.keys()):
            lines.append(f"| `{key}` | {directional[key]} |")
        lines.append("")

    # --- Counterexamples ---
    lines.append("## Observed counterexamples")
    lines.append("")
    lines.append(
        f"- Total observed verdict changes: {ce_summary['total']}"
    )
    if ce_summary["total"] == 0:
        lines.append(
            "- None observed in this run. This is a result of the run, "
            "not evidence that the transformation is invariant."
        )
    else:
        by_flip = ce_summary.get("by_flip_type") or {}
        if by_flip:
            lines.append("- By transition type:")
            for key in sorted(by_flip.keys()):
                lines.append(f"  - `{key}`: {by_flip[key]}")
        by_cond = ce_summary.get("by_condition") or {}
        if by_cond:
            lines.append("- By perturbation:")
            for key in sorted(by_cond.keys()):
                lines.append(f"  - `{key}`: {by_cond[key]}")
        by_bucket_ce = ce_summary.get("by_risk_bucket") or {}
        if by_bucket_ce:
            lines.append("- By risk bucket:")
            for key in sorted(by_bucket_ce.keys()):
                lines.append(f"  - `{key}`: {by_bucket_ce[key]}")
    lines.append("")

    # --- Reproducibility note ---
    lines.append("## Reproducibility")
    lines.append("")
    lines.append(manifest["parameters"].get("reproducibility_note", ""))
    lines.append("")

    # --- Interpretation boundary ---
    lines.append("## Interpretation boundary")
    lines.append("")
    lines.append(card["interpretation_boundary"])
    lines.append("")

    # --- Limitations ---
    lines.append("## Limitations")
    lines.append("")
    for limitation in card["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def write_card(
    card: Mapping[str, Any],
    *,
    markdown_path: str | Path,
    json_path: str | Path,
) -> None:
    """Write the Stability Card in both Markdown and JSON formats.

    The Markdown file is the public artefact. The JSON file is the
    archival artefact. Both are written from the same in-memory card, so
    they cannot diverge.
    """
    md_path = Path(markdown_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(render_markdown(card))

    json_out = Path(json_path)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, "w", encoding="utf-8") as handle:
        json.dump(card, handle, indent=2, sort_keys=True, ensure_ascii=False)


def load_card(path: str | Path) -> dict[str, Any]:
    """Load a Stability Card from a JSON file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid JSON object.
    """
    card_path = Path(path)
    if not card_path.exists():
        raise FileNotFoundError(f"Stability Card not found: {card_path}")
    with open(card_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Stability Card is not a JSON object: {card_path}")
    return data