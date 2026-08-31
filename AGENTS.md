# AGENTS.md — Karani

You are the coding agent building Karani. Read `docs/PRD.md` (v1.2 — it governs over any other copy) before writing anything. This file is standing context for every session.

## What Karani is

An autonomous overnight batch agent that prepares grading **evidence** for instructors and is architecturally incapable of issuing grades. Clerks prepare the case; judges decide it; Karani is only ever the clerk. Pipeline: ingest → rendition freeze → triage → injection scan → analyst workers → citation validator → terminal-state join → `render()` → docket + delivery. One append-only event log drives every artifact. The instructor ratifies feedback and writes every grade personally into a collection no pipeline identity can touch.

## Repository layout

```
src/
  schema/        # Pydantic models: observation, rendition, span union, events — the authoritative shapes
  ingest/        # local_source.py behind a source interface; rendition freeze; span registry
  triage/        # Gemma tier (dev via local Ollama only)
  armor/         # injection scan on post-extraction bytes; honest fallback adapter
  analysis/      # ADK orchestration: dispatcher, analyst workers
  validate/      # citation validator: referential, positional, quote, entailment; verdict lint
  render/        # render(runId): pure fold; sole writer of sheets/overview/claims
  delivery/      # KAR-406: Drive folder write + CSV export (delivery SA only)
  docket/        # Cloud Run service: overview, evidence sheet, click-to-locus, anomaly queue, challenge box
scripts/         # bootstrap_gcp.sh, teardown.sh, gen_scale_corpus.py, diff_runs.py, verify_artifact.py, prompt_bench.sh
fixtures/        # 15 authored submissions + MANIFEST.md; dev/ (3); adversarial/ (lint set); cache/; golden-log.jsonl
docs/            # PRD.md, GATE.md, BUILD-LOG.md, FINDINGS.md, metrics.json, compliance.md, antigravity/decision.md
```

## Make targets

| Target | Meaning |
|---|---|
| `make demo` | Committed fixture cache + local source + Firestore emulator; **zero credentials**; README line 1 |
| `make demo-live` | Real Vertex path |
| `make docket-recorded` | Docket over `fixtures/recorded-run.jsonl` (real model output); no model call, no cloud |
| `make docket-golden` | Docket over `fixtures/golden-log.jsonl` (hand-constructed reference); no model, no cloud |
| `make dev-run` | Pipeline over `fixtures/dev/` (3 submissions) — the only set used for iteration |
| `make compliance` | Greps KAR-### from PRD §4, diffs against §2's matrix; nonzero on any orphan |
| `make test` | Full suite including the replay, misattribution, collision, kill, and IAM negative tests |

## Conventions

- Python 3.12, type hints everywhere, Pydantic for schema. Lockfile pinned.
- Iterate against `fixtures/dev/` (3 submissions), never the full 15 — the full set is for integration runs and the recording. The 150-scale corpus is run **once** (KAR-320), cached, and never re-run casually.
- The response cache is **shared and durable, never in-process**. Idempotency depends on it: a worker retried at the same attempt number must regenerate byte-identical text.
- Temperature pinned to 0, recorded in `provenance{}`. Model ID strings pinned, never aliases.
- Secrets never in the repo. `gitleaks` runs pre-commit.
- Commit continuously. Never squash, never rebase history — the public commit log is compliance evidence.
- Every runtime prompt (analysis, validator feedback, entailment question, lint assist) is iterated **against Gemini via `scripts/prompt_bench.sh`**, which runs a variant across the dev fixtures and writes first-attempt acceptance rate to `docs/metrics.json`. Runtime prompts are never tuned by feel or against any other model.
- No Anthropic or other third-party model API call exists in any execution path, in any environment, at any time. Runtime is Gemini 3.5 exclusively.

## Invariants you must never weaken (full table: PRD §3.4)

1. The event log is append-only: deterministic IDs, `create()`-only, custom IAM role + Firestore rules. A collision with a different payload raises `EventIdCollision` — never silent dedupe.
2. `render(runId)` is a pure fold and the only artifact writer. The CI replay test runs with no emulator and no credentials against a shuffled log.
3. Every `evidence` observation cites a registered span; validation is set membership + positional identity + `quote in span_text`; entailment on top. `no_evidence` is first-class ("cited XOR no_evidence") and never retried.
4. No field anywhere ranks, scores, or orders a student's work. No grade, no percentile, no meets/exceeds enum, no confidence float about the submission. `grades/` is written only by the instructor's session — every pipeline SA is denied, in the emulator and on the deployed path.
5. Verdict lint: **generated text** is masked with the visible redaction notice; **`citation.quote` is flagged, never masked** (a student's own words must never be redacted), unless the source span is injection-flagged.
6. Bounded autonomy: attempt cap 2 at observation granularity, then `NEEDS_HUMAN`; run-level circuit breaker; dispatcher-owned `T_max` join deadline; abandoned units land in `excluded[]`, never hang the run.
7. Least privilege: per-stage SAs with a negative-test matrix asserting `PERMISSION_DENIED` for every forbidden operation. Never widen a scope to unblock a deploy — if a permission is missing, stop and say so.

## Standing guardrails (defect classes already paid for once — do not repeat them)

- **Never present in-process timings as deployed measurements.** If it didn't run on Cloud Run, it isn't a deployment number.
- **Never display a hardcoded literal as a live count.** Every number on any surface is computed from data or absent.
- **Never widen IAM scope to unblock.** A failing deploy with correct permissions beats a passing deploy with wrong ones.
- **Timestamp comparisons use epoch or normalized UTC**, never ISO string sort — mixed offsets have already produced a real ordering bug in a sibling system.
- **Scheduler/system traffic must never be countable as external or organic activity** in any metric or log-derived claim.
- **If a managed API returns 403/404 on this account tier, pull the claim** and record the finding — never implement a lookalike under the product's name.
- **Never fabricate observations, fixtures-as-results, or plausible metrics.** If a measurement doesn't exist yet, write "not yet measured." Genuine failures are publishable findings; polished fabrications are defects.

## Non-goals — do not build these

No spreadsheet/`cell` anchors. No vector database (whole-document context is the *enabling condition* for a closed span registry; chunk retrieval would manufacture false `no_evidence` and fabrication pressure). No Pub/Sub. No Drive **ingest** (`drive_source.py` is cut; Drive **delivery** in `src/delivery/` is in scope and is write-only to one folder). No LMS integration beyond the CSV export. No multi-institution features. No `extraction_confidence` float. No real student data anywhere.

## Language discipline in docs, comments, and copy

- Do not write "structurally impossible" for verdict abstinence until KAR-312 passes on the deployed path. Interim: *"no field can carry a verdict into any downstream system, and no aggregate can be computed."*
- Do not call the validator an "auditor" until KAR-310 ships at 100%.
- Do not call the Gemma tier "local" unless it is literally local.
- Never claim a drafted observation was seeded. It never is.
- Never name a real company or person as a bad actor in fixtures, tests, comments, or copy.
- Fixtures are "adversarial" or "hostile," never "messy."
- Build tooling is described generically in any public-facing text; no authoring tool is named; nothing is misattributed.

## Session protocol

Every session ends with an entry appended to `docs/BUILD-LOG.md`:

```markdown
### YYYY-MM-DD — <session title>

**Prompt (verbatim):**
> <the opening prompt exactly as given, unedited; follow-up corrections as a "Course corrections" sub-list, exact wording>

**Outcome:** <what was built, which ACs now pass, what failed or was deferred, what surprised you>

**Key decisions:**
1. <decision> — <why, and what was rejected>
2. <decision> — <why, and what was rejected>
3. <optional third>

**Requirements touched:** KAR-###, KAR-###
```

Two or three decisions per session, not a changelog. A decision is a fork where the alternative was live. If nothing forked, write "No forks this session" rather than manufacturing decisions.

Separately, append to `docs/FINDINGS.md` at the end of every build day: measured numbers (cost per run against the $0.40 estimate, cache hit rate, retry distribution, entailment disagreement rate and which pre-committed branch was taken, which `source_projection` tier the PDFs actually settled at) and **Google-toolchain findings** — where ADK's session and orchestration patterns fit or fought this design, what the Armor surface allowed on this account tier, what the long-context passes got right and wrong. Admitting that PDF anchoring degraded to `doc_only` is more credible than claiming everything worked.

## Working pattern

For anything larger than an hour: produce an implementation plan, wait for correction, then execute. For every acceptance criterion, state the property it proves, then state how the design makes it impossible for the AC to pass while the property is false. If an AC names an artifact rather than a property, flag it and propose a replacement. Call out anything ambiguous in the PRD rather than choosing silently.
