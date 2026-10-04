# Roadmap and Funded Extension Tracks

Protocol Drift Atlas v0.1 is complete within its self-funded scope. It
is a reproducible measurement toolkit, not a human-validated safety
evaluation or a model-certification system.

This document describes the extension tracks that would become possible
with external funding. None of these extensions is required for v0.1 to
be useful within its stated scope. They expand empirical coverage,
human validation, and external replicability.

---

## Current status (unfunded)

**Scope**

- 24 author-created, public, de-risked demonstration items.
- 4 risk buckets, 6 items each.
- 4 declared perturbations at three levels (protocol, prompt, framing).
- 2 execution configurations: mock and OpenAI hosted.
- 2 runs per condition.

**Deliverables**

- Versioned perturbation registry with declared failure hypotheses.
- Sanitized execution manifest schema.
- Provider-agnostic runner with local cache.
- Scorer with baseline–variant agreement, directional transitions,
  invalid-output rate, valid-response coverage.
- Exploratory Stability Card in Markdown and JSON.
- Counterexample log in CSV and JSONL.
- 129 tests, all offline, all deterministic.

**Known limitations**

- No human-adjudicated safety labels.
- No human validation of perturbation invariance.
- No flip-severity assessment.
- No external replication.
- No multilingual coverage.
- No longitudinal version-drift measurement.
- Small, non-representative corpus.

These are not defects. They are the boundary of what can be delivered
without paid human review. v0.1 is designed to be useful within that
boundary.

---

## Extension Track 1 — Human-Validated Invariance (v0.2)

**What it adds**

- Three independent annotators with documented background in trust and
  safety, content policy, or AI evaluation.
- One senior adjudicator for persistent disagreements.
- One independent methodological reviewer for protocol audit.
- Human validation of invariance claims for the four declared
  perturbations on a stratified subset.
- Adjudicated safety labels for base items and selected variants.
- Flip-severity assessment for validated flips.

**Why it matters**

Without human validation, an observed flip can only be reported as a
declared sensitivity. With validation, it becomes evidence about
evaluator reliability under an invariance assumption that has been
independently examined.

**Indicative budget**

| Line | Range |
|---|---:|
| Annotators (3, part-time) | $6,000–$12,000 |
| Senior adjudicator | $2,000–$5,000 |
| External methodological reviewer | $2,000–$5,000 |
| **Total** | **$10,000–$22,000** |

**Preferred prerequisites**

- v0.1 publicly released.
- Stable perturbation registry and Stability Card specification.
- Documented user feedback, early adopters, or identified replication
  partners.

**Deliverables**

- Annotated dataset with inter-annotator agreement report.
- Human-Validated Stability Card format, distinct from the Exploratory
  Stability Card.
- v0.2 release with changelog.

**Notes**

The v0.1 Exploratory Stability Card and the v0.2 Human-Validated
Stability Card must remain distinct artifacts. The first reports
observed sensitivity; the second reports sensitivity under
human-validated invariance. Merging them would erase the distinction
the project exists to preserve.

---

## Extension Track 2 — External Replication (v0.3)

**What it adds**

- Two to three funded external replicators, selected via public
  criteria.
- Application of the toolkit to at least one benchmark or corpus
  external to the project.
- Public replication reports, including negative results.

**Why it matters**

Replication is the test of whether the toolkit is infrastructure or a
single-author study. Without it, the project remains a demonstration.

**Indicative budget**

| Line | Range |
|---|---:|
| Microgrants (2–3, $2,000–$5,000 each) | $4,000–$15,000 |
| Onboarding and technical support | $2,000–$3,000 |
| **Total** | **$6,000–$18,000** |

**Preferred prerequisites**

- v0.2 stable.
- Onboarding documentation complete.
- At least one partner benchmark identified.

**Deliverables**

- Replication reports in `reports/replication-reports/`.
- v0.3 release addressing bugs and transfer limitations.
- Public post-mortem on what did and did not transfer across contexts.

**Notes**

Success is not defined as reproducing the same effect sizes. Success is
defined as: the toolkit installs and runs without substantial
engineering support; at least two groups produce complete, comparable
reports; at least one external benchmark produces an interpretable
result; and bugs, ambiguities, or limits are documented and corrected
in a v0.3.

---

## Extension Track 3 — Multilingual Extension (v1.0)

**What it adds**

- Italian and one additional language (candidate: Arabic or Chinese).
- Forward translation, independent review, and back-translation on a
  sample.
- Explicit labeling of semantic, pragmatic, and policy-relevant
  equivalence for each item.
- Per-language stability analysis, without direct cross-language
  comparison unless item distributions are demonstrably comparable.

**Why it matters**

LLM safety evaluation remains Anglocentric. A controlled multilingual
extension tests whether protocol-level stability transfers across
languages, without conflating translation artifacts with evaluator
instability.

**Indicative budget**

| Line | Range |
|---|---:|
| Translation and review | $6,000–$12,000 |
| Additional annotation | $6,000–$12,000 |
| Analysis and reporting | $3,000–$6,000 |
| **Total** | **$15,000–$30,000** |

**Preferred prerequisites**

- v0.3 stable.
- Translation protocol peer-reviewed.
- Native-speaker reviewers identified.

**Deliverables**

- Multilingual dataset with equivalence annotations.
- Per-language Stability Cards.
- Report on non-equivalent items as a result, not as an error to hide.

**Notes**

The translation is not assumed to preserve meaning. Items that fail
semantic, pragmatic, or policy-relevant equivalence are reported as
such. Cross-language comparisons are not drawn unless item
distributions are demonstrably comparable.

---

## Exploratory note: longitudinal version drift

A future longitudinal study may re-run frozen protocols against named
model versions at scheduled intervals. This work is not currently a
funded extension track and has no committed delivery timeline.

If pursued, it would require:

- long-term storage of manifests and run records;
- a documented version-drift report format;
- a maintenance commitment beyond the v0.1 twelve-month window.

---

## What is explicitly out of scope

Even with funding, Protocol Drift Atlas does not aim to:

- certify any model as safe or unsafe;
- produce a universal ranking of LLM judges;
- replace human judgment with automated verdicts;
- cover all risk domains, providers, or languages;
- serve as a regulatory compliance tool.

These boundaries are part of the project's design, not a limitation of
its current funding status.

---

## Summary

| Track | Prerequisite | Indicative budget | Primary deliverable |
|---|---|---:|---|
| v0.1 (current) | — | $0 | Toolkit, card, counterexamples, tests |
| v0.2 Human-Validated Invariance | v0.1 released | $10k–$22k | Annotated dataset, validated card |
| v0.3 External Replication | v0.2 stable | $6k–$18k | Replication reports |
| v1.0 Multilingual | v0.3 stable | $15k–$30k | Per-language cards |

---

## How to propose a new track

A new extension track may be proposed by opening a GitHub issue with:

- a clear scientific or methodological motivation;
- a defined deliverable;
- an indicative budget;
- prerequisites;
- a description of how the track differs from the three listed here.

Proposals that duplicate the existing tracks are not accepted. The
project maintains a narrow scope on purpose.