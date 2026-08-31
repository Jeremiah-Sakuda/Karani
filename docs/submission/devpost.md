# Devpost submission copy

Ordered per PRD §1.3 — audience-validated, not preference-ordered. Paste into the Devpost
text description field.

**Category:** The Taskmaster

> **Before submitting:** every bracketed `[MEASURED: …]` placeholder below must be replaced
> with a real number from `docs/metrics.json`. If a number was not measured, delete the
> sentence — do not estimate it. This is the same rule the repository enforces on itself.

---

## Karani — evidence without verdicts

**An autonomous overnight batch agent that prepares grading evidence for instructors and is
architecturally incapable of issuing a grade.**

### 1. The friction

Instructor grading time is dominated by evidence-gathering, not judgment: close-reading each
submission, locating the passages that justify feedback, writing that feedback, forty times
per assignment.

`[MEASURED: baseline min/submission]` → `[MEASURED: with Karani]`, measured on a real rubric
across `[MEASURED: n]` timed sessions. Method in the README.

Stated honestly: Karani applies to **essay-shaped assignments — two to five per instructor per
semester** — not to problem sets, exams, multiple choice, code, or quantitative work. The
honest semester figure is therefore tens of hours, not the hundreds an unqualified multiplier
would imply. Being the entrant with a smaller measured number beats being the entrant with a
larger asserted one.

**The incumbent, named rather than ignored:** every real grader already uses a comment bank.
Karani's claim is not "faster than typing from scratch" — a comment bank already solves that.
It is that a comment bank still requires the instructor to *find the evidence*, which is the
part Karani does.

### 2. The honesty invariants — enforced by structure, not prose

*(Insert the full invariant table from the README verbatim. It is not a summary of the
architecture; it is the product, and it must not live only in an internal document.)*

### 3. Citation identity: a closed vocabulary minted at ingest

Every submission is frozen once into an immutable rendition — normalized text plus a
paragraph→offset map, hashed under `sha256(normalizer_version ‖ extractor_versions ‖ text)`.
Spans are minted from that rendition and are **the only citation targets that exist**.

So "did the model make this citation up?" is not a judgement call. It is set membership.

Four layers, cheapest and most decisive first:

1. **Referential** — is this span in the registry? Set membership.
2. **Quote** — does this text occur in that span, verbatim?
3. **Positional** — does it occur *where the citation claims*? A phrase can appear in two
   different paragraphs; what separates them is the surrounding context, which the citation
   carries and the validator recomputes.
4. **Entailment** — does the passage actually support the claim? Disagreements route to a
   human and are **never retried**.

Layer 3 is the one that earns its keep. Given a real quote lifted from paragraph 12 and
attributed to paragraph 47, where the phrase genuinely occurs in both, layers 1 and 2 both
*pass* — and an instructor gets pointed at the wrong paragraph in a document where one
concedes a point and the other reverses it.

**This is also why there is no vector database.** Chunk retrieval hands the model a *subset* of
the spans and asks it to be exhaustive, manufacturing both false "no evidence" findings and
pressure to fabricate. Whole-document context is the enabling condition for a closed span
vocabulary, not a convenience.

### 4. Why the refusal is defensible — and checkable

Karani's output is designed to be **contestable**: supersession instead of mutation, diff
across runs, absence as a first-class value, escalation instead of guessing, and an appeal
packet that re-verifies against its own event range.

The refusal is not a promise. It is checkable, right now, three ways:

- **Try it.** The hosted docket has a public challenge box — no login, no quota. Ask it for a
  grade. It answers with the observation schema: *there is no field for what you asked for.*
- **Read the test.** A parametrised test asserts every verdict-shaped field name on the banned
  list is rejected by the schema individually — and asserts the *reason* each rejection fires,
  because an earlier version of it passed with the setting turned off.
- **Read the boundary.** `deploy/iam/negative-matrix.yaml` enumerates every identity ×
  operation × resource pair and the outcome each must produce. `pytest -m deployed` asserts
  those denials against the deployed databases, and passing it is a release gate.

And incumbents structurally cannot follow: **an auto-grader's revenue is the score.**

### The autonomy claim, precisely

Not "it ran unattended." The system defines **six terminal outcomes**, each with a distinct
downstream effect: accepted first attempt · accepted after bounded retry · `no_evidence`
recorded and never retried · `NEEDS_HUMAN` · injection flagged with analysis proceeding
anyway · abandoned at the join with the run completing around it.

The recorded 16-submission run exercises **five** of them. `abandoned` is 0 — nothing hung,
so nothing was abandoned. The sixth is exercised by the reference log and by a test that
blocks a real worker and asserts the run completes around it at `T_max`. Six outcomes, not
six labels on identical output; five of them on the run you can replay.

### Technologies

- **Gemini** — `gemini-3.6-flash` (analysis), `gemini-3.5-flash-lite` (entailment, lint
  assist), via **Vertex AI**. Pinned ID strings, never aliases. Temperature pinned to 0 in
  code and recorded in `provenance{}` on every observation.
- **Google ADK** — the agent topology, as a `SequentialAgent` of three nodes: `dispatcher`,
  `analyst_validator`, `anomaly_triage`. Roles separated by *what each is allowed to
  conclude*, not by task; the contract between them is a typed schema and a validated
  citation, not a conversation. Stated plainly: these nodes orchestrate, they do not
  deliberate — `analyst_validator` is one call into a bounded thread pool where the analysis
  and the four-layer citation check actually happen. The reasoning is in the workers and the
  validator, not in a conversation between agents.
- **GenAI SDK** — model access, routed through a durable shared cache.
- **Cloud Run Jobs** (analysis fan-out), **Cloud Run service** (docket), **Firestore**
  (append-only event log + claims), **Cloud Scheduler** (nightly trigger).
- **Gemma** — triage tier. Bonus, and deliberately not load-bearing.

### What we learned

**The model our own spec required does not exist.** The PRD pinned `gemini-3.5-pro` for
analysis. There is no such publisher model — the 3.5 family is Flash and Flash-Lite. The
intuitive repair is "Pro was specified, use the available Pro", which pins
`gemini-3.1-pro-preview`: capability tier satisfied, and the contest's mandatory "Gemini 3.5
or newer" bar *failed*. Version tier and capability tier pointed opposite directions and only
one was graded pass/fail. There is now a preflight that resolves every pinned ID against the
live catalogue and fails loudly.

**Positional identity was defined against the wrong text.** The analyst sees the submission
with span markers interleaved; the validator computed context from the rendition, which has
none. Quotes near a paragraph start disagreed by exactly the marker width, were rejected as
misattributions, and re-failed identically on retry. In production that would have looked like
an unexplained escalation rate concentrated on *first sentences* — the sentences most likely
to carry a thesis.

**Generating fixtures in independent passes is not enough to make them different.** Fifteen
blind passes still produced fifteen essays taking the same position, twelve sharing a noun
phrase verbatim, one aphorism restyled in five, and — the sharpest finding from a blind
reviewer — *"each weak essay carries exactly one engineered lesion. Real weak student writing
fails on four axes at once and in ways nobody designed."* Independence of context is not
independence of prior. Divergence has to be allocated, not requested.

**The pipeline invented a student called MANIFEST.** Every markdown file in the source
directory was treated as a submission, so the fixture manifest was ingested, analysed against
all five criteria, and rendered into the class overview with a sheet indistinguishable from a
real one. A real instructor's folder holds the rubric, the assignment sheet, and the syllabus.

**A lint that redacts a student's own words is worse than no lint.** An earlier verdict lint
flagged a student who wrote *"this policy is excellent"* — evaluating a policy, not their own
essay. The lint is now split by speaker: generated text is masked; a student's quote is never
masked, only flagged, and only when it evaluates their own work.

### Links

- **Hosted docket:** `[URL]` · public challenge box at `[URL]/challenge`
- **Repository:** https://github.com/Jeremiah-Sakuda/Karani
- **Demo video:** `[URL]`
- **Blog:** `[URL]`

### Try it in one command

```bash
git clone https://github.com/Jeremiah-Sakuda/Karani && cd Karani && make demo
```

Zero credentials. Zero Java. Zero Docker.
