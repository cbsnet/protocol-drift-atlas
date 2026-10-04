# Methodology

This document describes the measurement protocol of Protocol Drift Atlas
v0.1. It states what the toolkit measures, how the measurement is
constructed, and what the resulting numbers can and cannot support.

The document is deliberately descriptive rather than normative. It does
not prescribe how an evaluation should be run. It documents how this
toolkit runs its own measurement, so that a reader can decide whether the
result is usable for a given purpose.

---

## The problem the toolkit addresses

LLM safety evaluations increasingly rely on LLM judges: a model
classifies another model's response as safe, unsafe, or indeterminate
under a stated policy. The resulting verdict is often treated as a
property of the response.

It is not. The verdict is a property of the whole measurement pipeline:
the response, the policy, the judge, the prompt that carries the
policy, the order in which the response and the policy appear, the
label wording, and the evaluator instruction.

When the pipeline changes, the verdict can change even though the
underlying response, policy, and decision criterion are intended to
remain identical. If such changes are not measured, a single favorable
evaluation can be read as a stronger claim than it supports.

Protocol Drift Atlas v0.1 measures one specific aspect of this problem:
the **declared sensitivity** of a judge's verdict to a small set of
declared changes to the evaluation protocol.

---

## The measurement unit

The toolkit issues calls of the form:
