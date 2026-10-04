# Limitations

This document lists the limitations of Protocol Drift Atlas v0.1. It is
the extended version of the non-claims that appear in the README. Each
item states what the toolkit does not establish, and why the limitation
matters for a reader who is considering the results.

The limitations are organized in four groups: measurement, human
validation, scope, and reproducibility.

---

## Measurement limitations

**No ground truth.**
The toolkit does not produce or use human-adjudicated safety labels. An
observed verdict is a judgment produced by a language model under a
stated policy, not a fact about the response. Any aggregate metric that
depends on labels — agreement, flip rate, coverage — is computed on
model-produced verdicts alone.

**No validated invariance.**
Every perturbation in v0.1 is recorded as `declared_unvalidated`. The
registry states an expected invariance claim and a plausible failure
mechanism for each transformation, but it does not test either. An
observed flip under a declared perturbation is reported as observed
sensitivity. It is not evidence that the perturbation was
safety-irrelevant, nor evidence of a model failure.

**No severity assessment.**
When a flip is observed, the toolkit records its direction
(`safe->unsafe`, `unsafe->safe`, `safe->indeterminate`, etc.) but does
not assign severity. A `safe->unsafe` flip on a benign item and a
`safe->unsafe` flip on a high-stakes item are recorded as the same
category. Severity is a research question deferred to the funded
extension track.

**No composition of error sources.**
Provider errors, invalid outputs, and timeouts are counted separately
from verdict agreement. They are not combined into a single reliability
score. A reader who wants a composite measure must construct one from
the reported components and state the weights explicitly.

---

## Human validation limitations

**No annotation panel.**
No human annotators reviewed the items, the perturbations, or the
model outputs. The toolkit cannot report inter-annotator agreement,
adjudication rates, or disagreement distributions, because no such
process took place.

**No methodological audit.**
The protocol has not been reviewed by an independent methodologist.
The design choices in the registry, the manifest schema, and the
Stability Card format are the author's, and they have not been
externally examined.

**No domain expertise.**
The four risk buckets in the demonstration corpus were defined by the
author. They do not correspond to any regulatory taxonomy, and they
were not reviewed by domain experts. Comparisons across buckets are
descriptive, not authoritative.

---

## Scope limitations

**Small, non-representative corpus.**
The v0.1 corpus contains 24 items. It is a de-risked demonstration
corpus, not a benchmark. It is not designed to estimate the prevalence
of protocol sensitivity in any population of items, models, or
deployments. Results on this corpus do not generalize.

**One reference model.**
The public reference run uses `gpt-4o-mini-2024-07-18`. Other models
may show different sensitivity profiles. The toolkit supports
additional execution configurations, but v0.1 does not include a
comparison across a model family.

**No multilingual coverage.**
All items, prompts, and templates are in English. The toolkit has not
been tested on any other language. Cross-linguistic stability is
described as a funded extension track, not as a property of v0.1.

**No longitudinal tracking.**
The toolkit does not measure how a judge's behavior changes across
model versions or over time. A Stability Card describes a single run
against a single model version on a single date.

---

## Reproducibility limitations

**Hosted providers are not reproducible.**
The hosted reference configuration depends on an external provider. The
model returned by the provider may differ from the model requested, the
service may be updated without notice, and the outputs may vary across
regions, times, and account tiers. The manifest records what the
provider reported at execution time, but it cannot guarantee that the
same call would produce the same response in the future.

**Temperature zero does not imply determinism.**
The toolkit uses `temperature=0` where supported. This reduces
variation but does not eliminate it. Repeatability is measured through
the baseline run agreement metric, not assumed.

**No request-id archival.**
The manifest does not embed provider-side request identifiers. It
records whether such identifiers were preserved in the private run
log, but it does not publish them. A reader who wants to verify an
individual call with the provider must reproduce the run rather than
retrieve a specific response.

**Cache changes the observed cost, not the result.**
The local cache avoids duplicate requests. A cached run and an
uncached run with identical inputs produce the same records, provided
the provider is deterministic. When the provider is not
deterministic, the cache preserves the first response observed and
does not re-sample.

**Small-sample bootstrap intervals are wide.**
With 24 items, the bootstrap interval around the agreement rate is
wide. A point estimate of 0.92 with an interval of [0.88, 0.96] should
be read as "high agreement on this corpus", not as a precise estimate.
When the interval collapses to a single value, the card labels it as
degenerate.

---

## What these limitations are not

These limitations are not defects of v0.1. They are the boundary of
what can be delivered without paid human review, independent
replication, and dedicated funding. Each limitation is matched by an
extension track in [`roadmap.md`](roadmap.md).

The purpose of this document is to make the boundary visible, so that
a reader does not mistake the toolkit for something it is not.

---

## Companion documents

- [`../README.md`](../README.md) — project overview and short non-claims
- [`methodology.md`](methodology.md) — measurement protocol and metrics
- [`roadmap.md`](roadmap.md) — funded extension tracks
- [`../data/README.md`](../data/README.md) — corpus de-risking criteria