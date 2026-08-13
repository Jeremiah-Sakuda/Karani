# Runtime framework decision (KAR-020)

**Status:** adopted, not re-run. **Date:** 2026-08-12.

## Decision

Runtime orchestration is **Google ADK from day one**. The **GenAI SDK** is dual-listed as
the model-access surface.

## Why this was not re-verified

The headless multi-agent assertion failed under verification on **2026-08-08** in the sibling
entry. That experiment has already been run and has already returned an answer. Re-running a
decided experiment spends a day that this calendar does not have, and would produce the same
result for the same reason.

Antigravity is therefore **not the runtime surface** for Karani. This is disclosed in the
README under `## Relationship to my other submissions` rather than left for a judge to infer
from its absence.

## Compliance consequence

The hackathon requires at least one Google Agent Framework. Karani lists two, deliberately:

- **Google ADK** — runtime orchestration: dispatcher, analyst workers, citation validator,
  anomaly triage
- **GenAI SDK** — model access

Dual-listing is not padding. It means the mandatory requirement survives if either surface
changes shape between now and judging, which on a four-week contest against a model family
that shipped a new member three weeks ago is not a hypothetical.

## Fallback, pre-committed

If any ADK surface fails headless — the exact failure mode already observed once in the
sibling entry — Karani falls back to plain GenAI SDK calls structured as agent roles. The
role boundaries, the typed schemas, and the validation gate are properties of Karani's own
design, not of the framework, so the fallback costs orchestration ergonomics and nothing
architectural.

Compliance is unaffected by the fallback: the GenAI SDK independently satisfies the
Agent Framework requirement.

## What is *not* claimed

Karani does not claim ADK is load-bearing for its invariants. The append-only log, the span
registry, the citation validator, and the IAM verdict boundary are enforced by Firestore
rules, custom IAM roles, and pure functions — none of which ADK provides or could withdraw.
A framework that can be swapped in an afternoon is not carrying the argument.
