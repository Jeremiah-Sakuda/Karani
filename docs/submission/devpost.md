# Devpost submission copy

Ordered per PRD §1.3 — audience-validated, not preference-ordered. Paste into the Devpost
text description field.

**Category:** The Taskmaster

> **Before submitting:** the two remaining `[URL]` slots (video, blog) must be filled with
> the published links. Every number below already exists in `docs/metrics.json` with its
> measurement method attached; anything that was not measured has been deleted rather than
> estimated. This is the same rule the repository enforces on itself.

---

## Karani — evidence without verdicts

**Most AI agents are pitched on what they can do. Karani is built around what it
deliberately cannot: an autonomous overnight agent that prepares everything an instructor
needs to judge — and cannot judge, because the judgment is the professional's work, and we
kept it that way on purpose.**

Not "won't". Cannot. The restraint is architecture, not a system prompt: no field on any
record can hold a grade, and the database where grades live is one no part of the pipeline
holds a key to. We think this is where high-stakes agents are headed — competence at the
evidence, and a designed incapability at the verdict — and Karani is a working instance of
the pattern, deployed, with the incapability under test.

**What it is:** an overnight assistant that reads an entire class's essay submissions and
builds, for each student, an evidence sheet — every observation tied to a verbatim quote
from the student's own writing — plus a morning work-list of what needs the instructor's
attention.

**Who it's for:** instructors and TAs grading essay assignments. The person with forty
papers due back, whose grading time is mostly spent hunting for the sentence that justifies
the feedback they already know they'll give.

**Why the incapability is the product:** the reason AI hasn't already eaten this job is not
capability — it's that an AI's *grade* is indefensible. Departments ban it, students appeal
it, and they're right to. Karani removes the hunting and provably cannot touch the verdict,
which is exactly what makes it adoptable where AI graders are not.

One sentence for the skeptic who reads "batch LLM calls": the model calls are the cheapest
part of this system — the contribution is the **constraint system around them**, five
validation layers across two model families, an append-only event log a pure fold renders
from, and a verdict that has no field to land in. Grading is the first instance of a pattern
we think deserves a name — **verdict-incapable agents** — and the repository proves the
pattern generalizes by running a second domain (scholarship review) through the same
pipeline, unchanged.

**One unattended run, six kinds of consequence** (the recorded run exercises five; nothing
hung, so nothing was abandoned):

| Outcome | Recorded run (16 subs) | Deployed scale run (150 subs) |
|---|---|---|
| accepted, first attempt | 63 | 442 |
| accepted after bounded retry | 5 | 186 |
| `no_evidence` — recorded, never retried | 1 | 76 |
| `NEEDS_HUMAN` | 6 | 46 |
| injection flagged, analysis proceeded | 1 | 0 |
| abandoned, run completed around it | 0 | 0 |

The scale column is a real Cloud Run Job execution on the deployed project: 150 submissions,
745 observations, 2,451 events, 13.6 minutes on 15 workers, zero failures — and first-attempt
acceptance at 70.4%, *lower* than the small corpus's 85.1%. Published because it is true, and
because a metric that only improves with scale deserves suspicion.

### 1. The friction

Instructor grading time is dominated by evidence-gathering, not judgment: close-reading each
submission, locating the passages that justify feedback, writing that feedback, forty times
per assignment.

The friction reduction has **not been measured** — the planned stopwatch sessions (KAR-205)
did not happen before the deadline, and this project's own rule is that an unmeasured number
is deleted, not estimated. What *is* measured: the pipeline turns one submission into five
criterion-level observations with validated citations in a single unattended pass, and every
per-run figure below comes from `docs/metrics.json` with its measurement method attached.

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
5. **The cross-family second reader** — `gemma3:4b`, running locally via Ollama, re-answers
   the entailment question for every citation the Gemini tier accepted. Entailment is the
   one layer where the checker could share the generator's blind spots; a second model
   family narrows that class. **No single model's judgment turns a draft into evidence.**
   Unavailability is recorded as `second_reader: null` — not run, never a pass.

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

- **Try it on OUR corpus.** The hosted docket has a public challenge box — no login, no
  quota. Ask it for a grade. It answers with the observation schema: *there is no field for
  what you asked for.* (https://karani-docket-u42sxjnqkq-uc.a.run.app/challenge)
- **Try it on YOUR essay.** The arena runs the *genuine pipeline* — live Gemini analysis,
  the span registry, the injection scan, all five validation layers — on anything you paste,
  and returns the evidence sheet with no grade. Paste a prompt injection: it is flagged and
  analysis proceeds. Your text is analysed and not kept. (The arena's very first live test
  found a real bug — an injection wrapped across a soft line break evaded the scanner — which
  is the strongest argument for the page existing. The fix and the story are in the repo.)
- **Watch the night.** `/replay` steps the committed event log in fold order — tiles
  accumulating, escalations queueing — because "it ran unattended" is an assertion and forty
  seconds of watching consequences differ is the receipt.
- **Read the morning brief.** `/brief` is what the instructor actually receives: what needs
  them, what is done, and the class-level pattern ("N of M submissions drew no evidence on
  counterarguments," with cited examples) — delivered with every ratified Drive drop.
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

- **Hosted docket:** https://karani-docket-u42sxjnqkq-uc.a.run.app — challenge box at
  `/challenge`, morning brief at `/brief`, event-log replay at `/replay`
- **The arena (bring your own essay):** https://karani-arena-u42sxjnqkq-uc.a.run.app
- **Repository:** https://github.com/Jeremiah-Sakuda/Karani
- **Demo video:** `[URL]`
- **Blog:** `[URL]`

### Try it in one command

```bash
git clone https://github.com/Jeremiah-Sakuda/Karani && cd Karani && make demo
```

Zero credentials. Zero Java. Zero Docker.
