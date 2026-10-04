"""Tests for the epistemic claim boundaries of the project.

Protocol Drift Atlas defines itself by what it does *not* claim. These
tests make those boundaries enforceable. They verify that:

- no perturbation in the registry claims human validation;
- no perturbation is eligible for primary empirical claims;
- the README and the documentation do not contain overclaim words;
- the source code does not use forbidden vocabulary in user-facing
  strings;
- the interpretation boundary is present in every public artifact.

A failure here is a scope violation: the project has started claiming
something it cannot support. This is more serious than a functional
bug.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Words that must not appear in user-facing prose without an explicit,
# evidence-based justification. In v0.1 there is no such justification,
# so the presence of any of these words in the README or in the
# documentation is a scope violation.
OVERCLAIM_WORDS: tuple[str, ...] = (
    "certified",
    "guaranteed",
    "proven safe",
    "validated stability",
    "reliable model",
    "trustworthy model",
    "safety score",
    "human-validated stability",
)

# Files whose prose must not contain the overclaim words. These are the
# public-facing documents that a reviewer, funder, or reader will see
# first. Internal source files are covered separately where relevant.
PUBLIC_PROSE_FILES: tuple[str, ...] = (
    "README.md",
)

# Directories whose markdown files must also respect the claim
# boundaries. Add a path here when a new public document is added.
DOCS_DIRS: tuple[str, ...] = (
    "docs",
)

# Words that negate a phrase. Used to distinguish an affirmative claim
# from a correct disclaimer such as "is not a safety benchmark".
NEGATION_WORDS: tuple[str, ...] = ("not", "never", "no longer", "isn't", "aren't")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _has_affirmative_phrase(
    text: str,
    phrase: str,
    *,
    lookback: int = 40,
) -> tuple[bool, str]:
    """Return (True, context) if ``phrase`` appears affirmatively in ``text``.

    The function returns ``False`` when every occurrence of ``phrase``
    is preceded, within ``lookback`` characters, by a negation word.
    This allows correct disclaimers such as "is not a safety benchmark"
    to pass while still rejecting affirmative claims.

    The comparison is case-insensitive: the caller is expected to pass
    already-lowercased text for consistency, but the function lowercases
    both the phrase and the lookback window defensively.
    """
    lowered = text.lower()
    needle = phrase.lower()
    start = 0
    while True:
        index = lowered.find(needle, start)
        if index == -1:
            return False, ""
        window_start = max(0, index - lookback)
        window = lowered[window_start:index]
        if not any(neg in window for neg in NEGATION_WORDS):
            context_start = max(0, index - lookback)
            context_end = min(len(text), index + len(phrase) + 20)
            context = text[context_start:context_end].replace("\n", " ")
            return True, context
        start = index + len(needle)


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------


def test_registry_perturbations_are_all_declared_unvalidated(
    registry_path: Path,
) -> None:
    """Every perturbation in v0.1 must be declared_unvalidated.

    This duplicates a test in test_perturbation_registry.py on purpose.
    The claim boundary is the single most important invariant of the
    project, so it is checked in more than one place.
    """
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        assert entry["status"] == "declared_unvalidated", (
            f"{entry['perturbation_id']} claims a status other than "
            f"'declared_unvalidated'. v0.1 forbids this."
        )


def test_registry_perturbations_are_not_eligible_for_primary_claims(
    registry_path: Path,
) -> None:
    """No perturbation may be eligible for a primary empirical claim."""
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    for entry in registry["perturbations"]:
        assert entry["eligible_for_primary_claims"] is False, (
            f"{entry['perturbation_id']} is marked eligible for primary "
            f"claims. v0.1 forbids this."
        )


def test_registry_contains_only_expected_perturbations(
    registry_path: Path,
) -> None:
    """The scope of v0.1 is four perturbations, no more, no less."""
    expected = {
        "P1_RUBRIC_PARAPHRASE",
        "P2_RESPONSE_POSITION",
        "P3_DECISION_LABEL_WORDING",
        "P4_AUDIT_FRAMING",
    }
    with open(registry_path, "r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)

    actual = {entry["perturbation_id"] for entry in registry["perturbations"]}
    assert actual == expected


# ---------------------------------------------------------------------------
# Interpretation boundary
# ---------------------------------------------------------------------------


def test_interpretation_boundary_is_a_constant() -> None:
    """The boundary must be defined once and imported where needed."""
    from protocol_drift_atlas.reporting import INTERPRETATION_BOUNDARY

    assert isinstance(INTERPRETATION_BOUNDARY, str)
    assert "does not establish ground truth" in INTERPRETATION_BOUNDARY
    assert "model safety" in INTERPRETATION_BOUNDARY


def test_v0_1_limitations_cover_all_deferred_topics() -> None:
    """The limitations list must mention each deferred extension track."""
    from protocol_drift_atlas.reporting import V0_1_LIMITATIONS

    text = " ".join(V0_1_LIMITATIONS).lower()
    required_topics = [
        "human",
        "invariance",
        "demonstration",
        "replication",
        "multilingual",
    ]
    for topic in required_topics:
        assert topic in text, (
            f"The limitations list does not mention {topic!r}. "
            "Each deferred topic must be declared."
        )


def test_interpretation_boundary_appears_in_every_card() -> None:
    """Every card built by build_card must carry the boundary verbatim."""
    from protocol_drift_atlas.reporting import (
        INTERPRETATION_BOUNDARY,
        build_card,
    )

    manifest = {
        "schema_version": "0.1.0",
        "toolkit": {"name": "protocol-drift-atlas", "version": "0.1.0",
                    "source_revision": None},
        "execution": {"run_id": "t", "timestamp_utc": "2026-10-04T00:00:00Z",
                      "execution_role": "custom"},
        "provider": {"provider_id": "mock", "adapter_id": "mock",
                     "adapter_version": "0.1.0", "endpoint_type": None},
        "model": {"model_requested": "mock", "model_returned": "mock"},
        "parameters": {"temperature": 0.0, "top_p": 1.0,
                       "max_output_tokens": 50, "seed_requested": None,
                       "seed_supported": False,
                       "reproducibility_note": "x"},
        "protocol": {"baseline_protocol_id": "BASELINE_V0_1",
                     "prompt_template_id": "baseline.jinja2",
                     "prompt_template_hash": "sha256:" + "a" * 64,
                     "perturbation_registry_hash": "sha256:" + "b" * 64,
                     "perturbation_ids": ["P1_RUBRIC_PARAPHRASE"]},
        "artifacts": {"dataset_id": "x", "dataset_hash": "sha256:" + "c" * 64,
                      "response_schema_hash": "sha256:" + "d" * 64},
        "provider_extras": {},
    }
    card = build_card(manifest=manifest, records=[], bootstrap_resamples=50)
    assert card["interpretation_boundary"] == INTERPRETATION_BOUNDARY


# ---------------------------------------------------------------------------
# README and public prose
# ---------------------------------------------------------------------------


def test_readme_does_not_contain_overclaim_words(repository_root: Path) -> None:
    """No overclaim word may appear in the README, even in a quotation."""
    readme = repository_root / "README.md"
    if not readme.exists():
        pytest.skip("README.md not present yet.")
    text = readme.read_text(encoding="utf-8").lower()
    for word in OVERCLAIM_WORDS:
        found, context = _has_affirmative_phrase(text, word)
        if found:
            pytest.fail(
                f"README contains overclaim word {word!r} affirmatively: "
                f"...{context}..."
            )


def test_readme_mentions_interpretation_boundary(repository_root: Path) -> None:
    """The README must carry the interpretation boundary prominently."""
    readme = repository_root / "README.md"
    if not readme.exists():
        pytest.skip("README.md not present yet.")
    text = readme.read_text(encoding="utf-8").lower()
    assert "interpretation boundary" in text or "does not establish" in text


def test_readme_does_not_claim_benchmark_status(repository_root: Path) -> None:
    """The README must not describe the corpus as a safety benchmark.

    Correct disclaimers such as "is not a safety benchmark" are
    allowed. Only affirmative uses fail the test.
    """
    readme = repository_root / "README.md"
    if not readme.exists():
        pytest.skip("README.md not present yet.")
    text = readme.read_text(encoding="utf-8").lower()
    found, context = _has_affirmative_phrase(text, "safety benchmark")
    if found:
        pytest.fail(
            f"README uses 'safety benchmark' affirmatively: ...{context}..."
        )


def test_readme_does_not_describe_model_as_safe(repository_root: Path) -> None:
    """The README must not describe any model as safe or unsafe.

    The regex is deliberately narrow: it matches phrases such as
    "model X is safe" or "gpt-4o is unsafe", but not legitimate
    phrases such as "whether a model is safe".
    """
    readme = repository_root / "README.md"
    if not readme.exists():
        pytest.skip("README.md not present yet.")
    text = readme.read_text(encoding="utf-8").lower()
    pattern = re.compile(r"\bmodel\s+\w+\s+is\s+(safe|unsafe)\b")
    assert not pattern.search(text), (
        "README appears to certify a model as safe or unsafe."
    )


# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------


def test_documentation_files_do_not_contain_overclaim_words(
    repository_root: Path,
) -> None:
    """Markdown files in docs/ must respect the same boundaries as the README."""
    for dirname in DOCS_DIRS:
        docs_dir = repository_root / dirname
        if not docs_dir.exists():
            continue
        for md_file in docs_dir.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for word in OVERCLAIM_WORDS:
                found, context = _has_affirmative_phrase(text, word)
                if found:
                    relative = md_file.relative_to(repository_root)
                    pytest.fail(
                        f"{relative} contains overclaim word {word!r} "
                        f"affirmatively: ...{context}..."
                    )


# ---------------------------------------------------------------------------
# Source code vocabulary
# ---------------------------------------------------------------------------


def test_reporting_module_defines_boundary_and_limitations() -> None:
    """The reporting module must expose the boundary and the limitation list."""
    from protocol_drift_atlas import reporting

    assert reporting.INTERPRETATION_BOUNDARY
    assert reporting.V0_1_LIMITATIONS
    assert isinstance(reporting.V0_1_LIMITATIONS, tuple)


def test_stability_card_renderer_does_not_produce_overclaim() -> None:
    """The rendered Markdown of a minimal card must not contain overclaim words."""
    from protocol_drift_atlas.reporting import build_card, render_markdown

    manifest = {
        "schema_version": "0.1.0",
        "toolkit": {"name": "protocol-drift-atlas", "version": "0.1.0",
                    "source_revision": None},
        "execution": {"run_id": "t", "timestamp_utc": "2026-10-04T00:00:00Z",
                      "execution_role": "custom"},
        "provider": {"provider_id": "mock", "adapter_id": "mock",
                     "adapter_version": "0.1.0", "endpoint_type": None},
        "model": {"model_requested": "mock", "model_returned": "mock"},
        "parameters": {"temperature": 0.0, "top_p": 1.0,
                       "max_output_tokens": 50, "seed_requested": None,
                       "seed_supported": False,
                       "reproducibility_note": "x"},
        "protocol": {"baseline_protocol_id": "BASELINE_V0_1",
                     "prompt_template_id": "baseline.jinja2",
                     "prompt_template_hash": "sha256:" + "a" * 64,
                     "perturbation_registry_hash": "sha256:" + "b" * 64,
                     "perturbation_ids": ["P1_RUBRIC_PARAPHRASE"]},
        "artifacts": {"dataset_id": "x", "dataset_hash": "sha256:" + "c" * 64,
                      "response_schema_hash": "sha256:" + "d" * 64},
        "provider_extras": {},
    }
    card = build_card(manifest=manifest, records=[], bootstrap_resamples=50)
    md = render_markdown(card).lower()
    for word in OVERCLAIM_WORDS:
        found, context = _has_affirmative_phrase(md, word)
        if found:
            pytest.fail(
                f"Rendered Markdown contains overclaim word {word!r}: "
                f"...{context}..."
            )


# ---------------------------------------------------------------------------
# Corpus policy
# ---------------------------------------------------------------------------


def test_corpus_readme_declares_de_risking_policy(
    repository_root: Path,
) -> None:
    """The corpus documentation must declare the de-risking criteria."""
    corpus_readme = repository_root / "data" / "README.md"
    if not corpus_readme.exists():
        pytest.skip("data/README.md not present yet.")
    text = corpus_readme.read_text(encoding="utf-8").lower()
    assert "de-risking" in text or "de-risked" in text
    assert "interpretation boundary" in text or "does not establish" in text


def test_corpus_readme_does_not_claim_benchmark_status(
    repository_root: Path,
) -> None:
    """The corpus documentation must not describe the corpus as a safety benchmark.

    Correct disclaimers such as "is not a safety benchmark" are
    allowed. Only affirmative uses fail the test.
    """
    corpus_readme = repository_root / "data" / "README.md"
    if not corpus_readme.exists():
        pytest.skip("data/README.md not present yet.")
    text = corpus_readme.read_text(encoding="utf-8").lower()
    found, context = _has_affirmative_phrase(text, "safety benchmark")
    if found:
        pytest.fail(
            f"Corpus README uses 'safety benchmark' affirmatively: "
            f"...{context}..."
        )


# ---------------------------------------------------------------------------
# Vocabulary of the toolkit itself
# ---------------------------------------------------------------------------


def test_judgment_status_values_are_frozen() -> None:
    """The execution statuses are a closed set. No new status may appear."""
    from protocol_drift_atlas.models.judgment import ExecutionStatus

    expected = {"completed", "invalid_output", "provider_error", "timeout"}
    actual = {s.value for s in ExecutionStatus}
    assert actual == expected


def test_verdict_values_are_frozen() -> None:
    """The verdicts are a closed set. No fourth verdict may appear."""
    from protocol_drift_atlas.models.judgment import Verdict

    expected = {"safe", "unsafe", "indeterminate"}
    actual = {v.value for v in Verdict}
    assert actual == expected


def test_execution_status_and_verdict_are_distinct() -> None:
    """An execution status must not be a valid verdict, and vice versa."""
    from protocol_drift_atlas.models.judgment import ExecutionStatus, Verdict

    verdicts = {v.value for v in Verdict}
    statuses = {s.value for s in ExecutionStatus}
    # The two sets must not overlap. In particular, 'invalid_output'
    # must never be treated as a verdict.
    assert verdicts & statuses == set()