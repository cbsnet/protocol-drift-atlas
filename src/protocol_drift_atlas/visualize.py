"""Visual summaries of Stability Card results.

Plots are derivative artifacts. They are never a source of truth. Every
figure carries the interpretation boundary of the project, so that a
screenshot of a chart cannot be cited without its epistemic context.

Design principles:

- One message per figure. A reader must understand the figure in five
  seconds, without reading the caption.
- Sample size is always visible. A rate without its denominator is
  misleading, especially on small corpora.
- Uncertainty is visible when available. Bootstrap intervals appear
  next to the estimates they qualify, and degenerate intervals are
  labeled as such rather than silently presented as certainty.
- Color carries meaning. Green = agreement, red = flip, grey = neutral.
  No decorative color.
- No empty panels. If a figure has no data, it is not produced.

The module is import-guarded: if matplotlib is not installed, importing
this module does not fail. Functions that produce plots raise a clear
error only when called.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .reporting import INTERPRETATION_BOUNDARY


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COLOR_OK = "#4C7A34"        # muted green
COLOR_WARN = "#8A7A2E"      # muted amber
COLOR_FLIP = "#B3452B"      # muted red
COLOR_NEUTRAL = "#7A7A7A"   # grey
COLOR_TEXT = "#1A1A1A"
COLOR_MUTED = "#888888"
COLOR_FAINT = "#E0E0E0"
COLOR_BG = "#FFFFFF"


# ---------------------------------------------------------------------------
# matplotlib setup
# ---------------------------------------------------------------------------


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless-safe
        import matplotlib.pyplot as plt
        return plt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "matplotlib is required to generate plots. "
            "Install it with: pip install -e \".[viz]\""
        ) from exc


def _apply_style(plt) -> None:
    plt.rcParams.update({
        "figure.facecolor": COLOR_BG,
        "axes.facecolor": COLOR_BG,
        "axes.edgecolor": COLOR_FAINT,
        "axes.labelcolor": COLOR_MUTED,
        "axes.titlesize": 16,
        "axes.titleweight": "bold",
        "axes.titlecolor": COLOR_TEXT,
        "axes.labelsize": 13,
        "xtick.color": COLOR_MUTED,
        "ytick.color": COLOR_TEXT,
        "xtick.labelsize": 13,
        "ytick.labelsize": 15,
        "legend.fontsize": 13,
        "font.family": "sans-serif",
        "savefig.facecolor": COLOR_BG,
    })


def _save(fig, output_dir: Path, stem: str) -> list[Path]:
    """Save a figure as PNG and SVG, with generous padding at the bottom."""
    output_dir.mkdir(parents=True, exist_ok=True)
    png = output_dir / f"{stem}.png"
    svg = output_dir / f"{stem}.svg"
    fig.savefig(png, dpi=160, bbox_inches="tight", pad_inches=0.35)
    fig.savefig(svg, format="svg", bbox_inches="tight", pad_inches=0.35)
    return [png, svg]


def _perturbation_label(perturbation_id: str) -> str:
    """Return a single-line human-readable label for a perturbation.

    ``P1_RUBRIC_PARAPHRASE`` becomes ``P1 · Rubric Paraphrase``.
    """
    if "_" in perturbation_id:
        prefix, rest = perturbation_id.split("_", 1)
        return f"{prefix} · {rest.replace('_', ' ').title()}"
    return perturbation_id


def _agreement_color(rate: float) -> str:
    """Return a color reflecting the magnitude of an agreement rate."""
    if rate >= 0.9:
        return COLOR_OK
    if rate >= 0.7:
        return COLOR_WARN
    return COLOR_FLIP


def _is_degenerate_interval(ci: Any) -> bool:
    """True when a bootstrap interval has collapsed to a single value."""
    if not ci or len(ci) != 2:
        return False
    try:
        return abs(float(ci[0]) - float(ci[1])) < 1e-9
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Summary dashboard (hero figure)
# ---------------------------------------------------------------------------


def plot_summary_dashboard(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> list[Path]:
    """Single-page funder card.

    Layout, in five vertical zones:

    - header: project name, run identifier, model, date;
    - KPI row: four large numbers with labels;
    - notes: bootstrap interval, and, when degenerate, a clarification;
    - chart: horizontal bars with single-line labels, values, sample size;
    - footer: interpretation boundary, centered, at fontsize 20.
    """
    plt = _require_matplotlib()
    _apply_style(plt)

    manifest = card["manifest"]
    agreement = card["metrics"]["baseline_variant_agreement"]
    ce_total = card["counterexamples_summary"]["total"]

    model = manifest["model"]["model_requested"]
    run_id = manifest["execution"]["run_id"]
    timestamp = manifest["execution"]["timestamp_utc"][:10]

    # Tall figure: 14 wide x 12 tall, so the footer at 20pt fits with
    # margin and is not clipped by bbox_inches="tight".
    fig = plt.figure(figsize=(14, 12))
    fig.patch.set_facecolor(COLOR_BG)

    # --- Header ---
    fig.text(
        0.06, 0.965, "Protocol Drift Atlas",
        fontsize=28, fontweight="bold", color=COLOR_TEXT,
    )
    fig.text(
        0.06, 0.925,
        f"Run {run_id}   ·   {model}   ·   {timestamp}",
        fontsize=15, color=COLOR_MUTED,
    )
    fig.add_artist(
        plt.Line2D(
            [0.06, 0.94], [0.900, 0.900],
            transform=fig.transFigure,
            color=COLOR_FAINT, linewidth=0.8,
        )
    )

    # --- KPI row ---
    agreement_rate = agreement["agreement_rate"]
    flip_rate = agreement["any_flip_rate"]

    kpis = [
        ("Agreement rate", f"{agreement_rate:.2f}",
         _agreement_color(agreement_rate)),
        ("Any-flip rate", f"{flip_rate:.2f}",
         COLOR_FLIP if flip_rate > 0 else COLOR_NEUTRAL),
        ("Comparisons", str(agreement["comparisons"]), COLOR_TEXT),
        ("Counterexamples", str(ce_total),
         COLOR_FLIP if ce_total > 0 else COLOR_NEUTRAL),
    ]

    for i, (label, value, color) in enumerate(kpis):
        x = (i + 0.5) / 4
        fig.text(
            x, 0.820, value,
            fontsize=56, fontweight="bold",
            color=color, ha="center", va="center",
        )
        fig.text(
            x, 0.735, label,
            fontsize=15, color=COLOR_MUTED,
            ha="center", va="center",
        )

    # --- Bootstrap interval note ---
    ci = agreement.get("agreement_rate_ci95")
    if ci and len(ci) == 2:
        fig.text(
            0.5, 0.665,
            f"95% bootstrap interval for agreement rate: "
            f"[{ci[0]:.2f}, {ci[1]:.2f}]",
            fontsize=14, color=COLOR_MUTED,
            ha="center", va="center", style="italic",
        )
        if _is_degenerate_interval(ci):
            fig.text(
                0.5, 0.625,
                "No variance observed in the sample; "
                "the bootstrap interval is degenerate.",
                fontsize=13, color=COLOR_MUTED,
                ha="center", va="center", style="italic",
            )

    # --- Bar chart ---
    # Wide left margin (0.15) for single-line perturbation labels.
    # Chart sits between 0.17 and 0.57 vertically, leaving space below
    # for the footer at 0.06.
    ax = fig.add_axes([0.15, 0.17, 0.76, 0.40])

    by_pert = agreement.get("by_perturbation") or {}
    if by_pert:
        names = sorted(by_pert.keys())
        labels = [_perturbation_label(n) for n in names]
        agrs = [by_pert[n]["agreement_rate"] for n in names]
        flps = [by_pert[n]["any_flip_rate"] for n in names]
        comps = [by_pert[n]["comparisons"] for n in names]
        y = list(range(len(names)))

        ax.barh(y, agrs, color=COLOR_OK, height=0.55, zorder=3)
        ax.barh(y, flps, left=agrs, color=COLOR_FLIP, height=0.55, zorder=3)

        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=15, color="#333333")
        ax.invert_yaxis()
        ax.set_xlim(0, 1.32)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticklabels(
            ["0", "0.25", "0.50", "0.75", "1.00"],
            fontsize=13, color=COLOR_MUTED,
        )
        ax.set_title(
            "Agreement (green) vs flip rate (red) by declared perturbation",
            fontsize=16, fontweight="bold", color=COLOR_TEXT,
            loc="left", pad=20,
        )

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(COLOR_FAINT)
        ax.spines["bottom"].set_color(COLOR_FAINT)
        ax.tick_params(axis="y", length=0, pad=10)
        ax.tick_params(axis="x", colors=COLOR_MUTED, length=5, pad=6)
        ax.grid(axis="x", color="#f0f0f0", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)

        for i, (a, c) in enumerate(zip(agrs, comps)):
            ax.text(
                1.02, i, f"{a:.2f}",
                va="center", fontsize=15,
                color=COLOR_TEXT, fontweight="normal",
            )
            ax.text(
                1.18, i, f"n={c}",
                va="center", fontsize=13,
                color=COLOR_MUTED,
            )
    else:
        ax.axis("off")
        ax.text(
            0.5, 0.5, "No perturbation data available",
            ha="center", va="center", transform=ax.transAxes,
            fontsize=15, color=COLOR_MUTED,
        )

    # --- Footer (large, centered, well below the chart) ---
    fig.text(
        0.5, 0.06,
        "Observed changes only. Does not establish ground truth, "
        "invariance, error, or model safety.",
        fontsize=20, color=COLOR_MUTED, style="italic",
        ha="center", va="center",
    )

    paths = _save(fig, Path(output_dir), "fig_summary_dashboard")
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
# Secondary figures
# ---------------------------------------------------------------------------


def plot_perturbation_agreement(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> list[Path]:
    """Horizontal bar chart of agreement and flip rate per perturbation."""
    plt = _require_matplotlib()
    _apply_style(plt)

    by_pert = card["metrics"]["baseline_variant_agreement"].get("by_perturbation") or {}
    if not by_pert:
        raise ValueError("No per-perturbation data available in the card.")

    names = sorted(by_pert.keys())
    labels = [_perturbation_label(n) for n in names]
    agrs = [by_pert[n]["agreement_rate"] for n in names]
    flps = [by_pert[n]["any_flip_rate"] for n in names]
    comps = [by_pert[n]["comparisons"] for n in names]

    height = max(4.0, 0.85 * len(names) + 2.6)
    fig, ax = plt.subplots(figsize=(12, height))
    y = list(range(len(names)))

    ax.barh(y, agrs, color=COLOR_OK, height=0.55, label="Agreement", zorder=3)
    ax.barh(y, flps, left=agrs, color=COLOR_FLIP, height=0.55, label="Flip", zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=15, color="#333333")
    ax.invert_yaxis()
    ax.set_xlim(0, 1.28)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"], fontsize=13)
    ax.set_title(
        "Agreement and flip rate by declared perturbation",
        fontsize=16, pad=18,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_FAINT)
    ax.spines["bottom"].set_color(COLOR_FAINT)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.grid(axis="x", color="#f0f0f0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False, fontsize=13)

    for i, (a, c) in enumerate(zip(agrs, comps)):
        ax.text(
            1.02, i, f"{a:.2f}   n={c}",
            va="center", fontsize=13, color=COLOR_TEXT,
        )

    fig.text(
        0.5, 0.015,
        INTERPRETATION_BOUNDARY,
        ha="center", va="bottom",
        fontsize=10, color=COLOR_MUTED, style="italic", wrap=True,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    paths = _save(fig, Path(output_dir), "fig_perturbation_agreement")
    plt.close(fig)
    return paths


def plot_execution_quality(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> list[Path]:
    """Horizontal stacked bar showing execution outcomes."""
    plt = _require_matplotlib()
    _apply_style(plt)

    quality = card["metrics"]["execution_quality"]
    total = quality["total_records"]
    if total == 0:
        raise ValueError("No records to plot.")

    valid = quality["valid_records"]
    invalid = int(round(quality["invalid_output_rate"] * total))
    provider_error = int(round(quality["provider_error_rate"] * total))
    timeout = int(round(quality["timeout_rate"] * total))
    accounted = valid + invalid + provider_error + timeout
    if accounted < total:
        valid += total - accounted

    segments = [
        ("Valid", valid, COLOR_OK),
        ("Invalid output", invalid, COLOR_FLIP),
        ("Provider error", provider_error, COLOR_NEUTRAL),
        ("Timeout", timeout, "#333333"),
    ]
    segments = [(n, v, c) for n, v, c in segments if v > 0]

    fig, ax = plt.subplots(figsize=(11, 3.8))
    left = 0
    for name, value, color in segments:
        ax.barh([0], [value], left=left, color=color, height=0.4, label=f"{name} ({value})")
        left += value

    ax.set_yticks([])
    ax.set_xlim(0, total)
    ax.set_xlabel("Records", fontsize=13, labelpad=12)
    ax.set_title("Execution quality (all records)", fontsize=16, pad=18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.55),
              ncol=min(4, len(segments)), frameon=False, fontsize=13)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_FAINT)

    fig.text(
        0.5, 0.015, INTERPRETATION_BOUNDARY,
        ha="center", va="bottom",
        fontsize=10, color=COLOR_MUTED, style="italic", wrap=True,
    )
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    paths = _save(fig, Path(output_dir), "fig_execution_quality")
    plt.close(fig)
    return paths


def plot_directional_transitions(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> list[Path]:
    """Horizontal bar chart of directional verdict transitions."""
    plt = _require_matplotlib()
    _apply_style(plt)

    directional = (
        card["metrics"]["baseline_variant_agreement"]
        .get("directional_transitions") or {}
    )
    if not directional:
        raise ValueError("No directional transitions observed in this card.")

    labels = sorted(directional.keys())
    counts = [directional[k] for k in labels]

    height = max(3.2, 0.75 * len(labels) + 2.0)
    fig, ax = plt.subplots(figsize=(11, height))
    y = list(range(len(labels)))

    colors = [
        COLOR_FLIP if lbl.startswith("safe") and "unsafe" in lbl.split("->")[1]
        else COLOR_NEUTRAL
        for lbl in labels
    ]
    ax.barh(y, counts, color=colors, height=0.5, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=15)
    ax.invert_yaxis()
    ax.set_xlabel("Count", fontsize=13, labelpad=12)
    ax.set_title("Directional transitions (baseline to variant)", fontsize=16, pad=18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_FAINT)
    ax.spines["bottom"].set_color(COLOR_FAINT)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.grid(axis="x", color="#f0f0f0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    for i, c in enumerate(counts):
        ax.text(c + 0.15, i, str(c), va="center", fontsize=13, color=COLOR_TEXT)

    fig.text(
        0.5, 0.015, INTERPRETATION_BOUNDARY,
        ha="center", va="bottom",
        fontsize=10, color=COLOR_MUTED, style="italic", wrap=True,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    paths = _save(fig, Path(output_dir), "fig_directional_transitions")
    plt.close(fig)
    return paths


def plot_risk_bucket_breakdown(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> list[Path]:
    """Horizontal bar chart of agreement and flip rate per risk bucket."""
    plt = _require_matplotlib()
    _apply_style(plt)

    by_bucket = (
        card["metrics"]["baseline_variant_agreement"]
        .get("by_risk_bucket") or {}
    )
    if not by_bucket:
        raise ValueError("No risk bucket breakdown available in the card.")

    names = sorted(by_bucket.keys())
    agrs = [by_bucket[n]["agreement_rate"] for n in names]
    flps = [by_bucket[n]["any_flip_rate"] for n in names]
    comps = [by_bucket[n]["comparisons"] for n in names]

    height = max(4.0, 0.85 * len(names) + 2.6)
    fig, ax = plt.subplots(figsize=(12, height))
    y = list(range(len(names)))

    ax.barh(y, agrs, color=COLOR_OK, height=0.55, label="Agreement", zorder=3)
    ax.barh(y, flps, left=agrs, color=COLOR_FLIP, height=0.55, label="Flip", zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(
        [n.replace("_", " ").title() for n in names],
        fontsize=15, color="#333333",
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 1.28)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"], fontsize=13)
    ax.set_xlabel("Rate", fontsize=13, labelpad=12)
    ax.set_title("Agreement and flip rate by risk bucket", fontsize=16, pad=18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_FAINT)
    ax.spines["bottom"].set_color(COLOR_FAINT)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.grid(axis="x", color="#f0f0f0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", frameon=False, fontsize=13)

    for i, (a, c) in enumerate(zip(agrs, comps)):
        ax.text(
            1.02, i, f"{a:.2f}   n={c}",
            va="center", fontsize=13, color=COLOR_TEXT,
        )

    fig.text(
        0.5, 0.015, INTERPRETATION_BOUNDARY,
        ha="center", va="bottom",
        fontsize=10, color=COLOR_MUTED, style="italic", wrap=True,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    paths = _save(fig, Path(output_dir), "fig_risk_bucket_breakdown")
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_all_plots(
    card: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, list[str]]:
    """Generate every available plot for a card.

    Plots that cannot be produced (because the card has no data for
    them) are skipped silently: their absence is not an error.
    """
    output_dir = Path(output_dir)
    results: dict[str, list[str]] = {}

    for name, fn in (
        ("summary_dashboard", plot_summary_dashboard),
        ("execution_quality", plot_execution_quality),
        ("perturbation_agreement", plot_perturbation_agreement),
        ("risk_bucket_breakdown", plot_risk_bucket_breakdown),
        ("directional_transitions", plot_directional_transitions),
    ):
        try:
            paths = fn(card, output_dir)
            results[name] = [str(p) for p in paths]
        except ValueError:
            continue

    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "figures_index.json"
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, sort_keys=True)

    return results