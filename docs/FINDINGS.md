# Findings

Appended every build day. Two kinds of entry: **measured numbers** (with the method that
produced them) and **Google-toolchain findings** (where the tools fit or fought this design).

Standing rule: if a measurement does not exist, this file says "not yet measured." A
plausible number is never a substitute for a measured one. Genuine failures are publishable
findings; polished fabrications are defects.

### 2026-08-12 — Model availability

**Finding: there is no `gemini-3.5-pro`.** The PRD (v1.2, §2 and KAR-301) pins analysis to
"Gemini 3.5 Pro." That publisher model does not exist. The Gemini 3.5 family ships as
`gemini-3.5-flash` and `gemini-3.5-flash-lite`. The newest Pro-tier model is
`gemini-3.1-pro-preview`.

This is the most consequential finding of the build so far, because the hackathon's
mandatory requirement is "Gemini 3.5 **or newer**." The intuitive repair — "Pro was
requested, use the available Pro" — pins a 3.1 model and fails the mandatory bar. Version
tier and capability tier point in opposite directions here, and only one of them is being
graded pass/fail.

Resolved in [DEVIATIONS.md](DEVIATIONS.md) D-001: analysis on `gemini-3.6-flash`
(released 2026-07-21), verification and entailment on `gemini-3.5-flash-lite`.

**Toolchain observation.** Neither the Vertex model-catalogue page nor the Gemini API models
page states the family in one enumerable place; the 3.5-Pro absence had to be established by
elimination across three sources plus a publisher-model listing. A build that had pinned the
model string from the PRD without checking would have been version-non-compliant while
looking, to its own author, entirely correct — the model ID would have 404'd only at the
first live call, which on this calendar is after the architecture is frozen.

**Consequence adopted into the build:** model IDs are not merely constants. `scripts/`
carries a preflight that resolves every pinned ID against the live publisher catalogue and
fails loudly on a miss, so a model that is renamed or withdrawn between now and judging
surfaces as a red check rather than a broken demo.

### 2026-08-12 — Measurements

Not yet measured. No instrumented run has executed. Every entry below is pending:

- Cost per 15-submission run against the §1.4 estimate — **not yet measured**
- First-attempt acceptance rate — **not yet measured**
- Entailment disagreement rate on `fixtures/dev/` and the pre-committed branch taken
  (≤8% accept; >8% one prompt-revision cycle; still >8% accept + report + "validator"
  language) — **not yet measured**
- Retry distribution — **not yet measured**
- Cache hit rate — **not yet measured**
- Which `source_projection` tier the PDFs actually settled at — **not yet measured**
- What the Model Armor surface allows on this account tier — **measured 2026-08-31, on the
  real bootstrap: not available.** The template create is refused on this tier, the probe
  reports unavailability, and triage runs `LocalPatternScanner` under its own name with an
  offline label on every detection — the exact honest-fallback path the adapter was built
  for, now exercised for real rather than by default. (Before today it was the default for
  the wrong reason: `google-cloud-modelarmor` was declared in neither `pyproject.toml` nor
  `requirements.lock`, so the `ImportError` branch fired in every environment and the
  managed path could not have run even where the tier allowed it. The dependency is
  declared; the tier is the remaining and honestly-reported limit.)
- Scale-run behaviour at N≈150 — **not yet measured**
- KAR-205 friction numbers — **not yet measured**

### 2026-08-12 — The positional layer, verified by removing it

The citation validator's third layer (positional identity) looks redundant beside the second
(quote containment), and the difference only shows up on one input: a real quote lifted from
span 12 and attributed to span 47, where the phrase genuinely occurs in both.

Rather than assert that the layer matters, it was removed and the suite re-run. Exactly one
test failed — the misattribution test. Restoring the layer restored the pass. That is the
evidence that the test is testing the mechanism rather than passing for an unrelated reason,
and it is cheap enough to be worth doing for every check whose necessity is not obvious.

**Design note this produced.** `build_citation()` computes prefix and suffix from the
rendition and is used only by fixtures, tests, and the appeal-packet exporter — never on the
analysis path. On the analysis path the *model* supplies the context it saw. If Karani
computed the context itself from the span the model named, layer 3 would be comparing the
rendition against itself and would pass unconditionally: a check that can never fail, sitting
in the position of the one that catches misattribution.

### 2026-08-12 — Fixture corpus: separate passes are not sufficient for divergence

PRD KAR-203 requires the fifteen submissions be generated "in separate passes… not
reconciled against each other," and that a blind skim of any three show visibly different
quality and voice. The first corpus was generated exactly that way — fifteen independent
passes, none able to see any other's output — and it still failed.

A blind reviewer, given the fifteen essays and told nothing about how they were made, found:

- All fifteen took the **same position**. A real class does not.
- Twelve of fifteen used the noun phrase "a 2024 municipal broadband study" **verbatim**.
- One aphorism (*"not a failure of effort but of arithmetic"*) appeared, restyled, in five.
- A twelve-word clause about a service appointment appeared **verbatim** in two essays that
  were supposed to be the two most stylistically distant in the set.
- Invented source surnames recombined from a pool of ten; the page number "41" anchored five
  different essays; the same fabricated author was male in one essay and female in another.

The sharpest observation was structural rather than lexical: *"each weak essay carries
exactly one engineered lesion. Real weak student writing fails on four axes at once and in
ways nobody designed."* Every paper had a locatable thesis, conceded the same objection in
the same slot, and committed no fallacy. The corpus tested register discrimination and
nothing else.

**What separate passes actually buy.** Independence of *context*, not independence of
*prior*. Fifteen blind passes over one prompt sample fifteen times from the same
distribution, and the mode is heavily favoured every time. The variation instruction was
being applied to style because style is where the instruction pointed; the argument
underneath was never asked to move.

**The fix, and it is not "more variety" in the brief.** Divergence had to be forced at the
level where convergence happened: each writer was assigned a **position** (six for, five
against, four qualified), a **disjoint source pool** with non-overlapping invented surnames
and page ranges, an explicit **ban list** of every shared phrase the reviewer found, a
distinct **structural template**, and — for the weak papers — instructions to fail on
several axes at once rather than carry one tidy defect. The second corpus's banned-token
sweep returns zero hits on every shared surname and shared phrase from the first.

**Worth generalising.** "Generate them independently" is a weaker guarantee than it sounds.
For any fixture corpus meant to represent a population, the axis of variation has to be
specified and allocated, not requested.

### 2026-08-12 — PDF extraction: page granularity destroys the span registry

First run over the real fixtures: the three PDF submissions produced **2, 2, and 1** spans,
against 6–12 for the same length of text in `.md` and `.docx`. An 1,164-word essay had two
citable regions.

`pypdf.extract_text()` returns one line per *typeset* line, and a PDF has no paragraphs to
recover — only glyphs at coordinates. Joining pages with a blank line therefore makes each
page a single paragraph, and the span registry silently degrades to page granularity. Nothing
errors. Citations still validate, quotes still match, `sha256` still agrees. Click-to-locus
just resolves to "somewhere on this page," which is the whole value of the registry gone
while every check stays green.

**The reconstruction now used:** a wrapped line runs nearly the full measure, so the last line
of a paragraph is the one that both ends a sentence and falls short of the column width.
Median line length per page supplies the measure, so it adapts to the document's own
typesetting rather than assuming one. Result: 8, 8, and 3 spans, with words-per-span for the
PDFs (151, 120, 116) now inside the range the other formats produce (49–197).

**The honest boundary**, since this is a heuristic and not a parse: a paragraph whose final
line happens to fill the measure merges with its successor, and a short line ending in an
abbreviation splits one paragraph in two. Both produce a span boundary wrong by a paragraph.
That is visible in the viewer and never silent — the citation still resolves to text
containing the quote. One span per page is wrong by a page, every time.

**Toolchain note:** the PDFs did *not* degrade to `doc_only`. The text layer was present and
exact; what degraded was structure, which is a quieter failure than a missing text layer
because every integrity check passes.

### 2026-08-12 — Positional identity was defined against the wrong text

The citation validator's third layer compares the context the model reports around its quote
against the context Karani computes from the source. The first end-to-end run over the real
fixtures rejected almost every citation at that layer.

The cause is a mismatch nobody would notice by reading either side alone. The analyst sees
the submission as `[[sp-0011]] <paragraph>\n\n[[sp-0012]] <paragraph>`. The validator computes
context from the **rendition**, which contains no span markers. For a quote in the middle of a
paragraph the two agree. For a quote near the *start* of one, the 32 characters the model saw
include `[[sp-0012]] ` and the tail of the previous paragraph, and the 32 the validator
computes do not. The citation is rejected, the retry produces the identical "mismatch", and
the observation escalates.

**Why this was worth stopping for.** The failure is quiet, systematic, and disguised: it fires
only near paragraph boundaries, it is indistinguishable from a genuine misattribution in the
logs, and it would have surfaced on the deployed path as an unexplained escalation rate
concentrated on first sentences — the sentences most likely to carry a thesis, which is the
one criterion an instructor most wants evidence for.

**Fix:** context is now **span-local**, bounded by the span being cited, and the prompt says so
explicitly ("do not read across into a neighbouring span, never include a `[[sp-NNNN]]`
marker"). Both sides now compute the same window from the same text. The misattribution
defence is unaffected: a phrase occurring in two spans is still separated by what precedes it
*within* each span, which the unit fixture confirms — the same-phrase-in-span-12-and-span-47
test still passes, and still fails when the layer is removed.

**Generalisable:** when a model is asked to report something that will be checked, the thing it
sees and the thing the checker sees must be the same artifact. Interleaving anything into the
prompt — markers, line numbers, annotations — silently makes them different.

### 2026-08-12 — The pipeline invented a student called MANIFEST

Running over the fixture directory dispatched **17** submissions where 16 exist. The
seventeenth was `MANIFEST.md`: it was ingested, frozen into a rendition, given a span registry,
analysed against all five criteria, and rendered into the class overview as a student.

Its evidence sheet looked exactly like every other evidence sheet.

This is not a fixture-directory quirk. A real instructor's submissions folder contains the
assignment sheet, the rubric, a syllabus excerpt, and whatever the LMS exported alongside the
student work — and every one of them would have become a student with observations and a place
in the roster. The overview's own counts would have been wrong while looking authoritative,
which is the failure mode this project's "never display a hardcoded literal as a live count"
rule exists to prevent, arriving from a direction the rule did not anticipate.

**Fix:** a deterministic name-based exclusion at the source (`readme`, `manifest`, `rubric`,
`syllabus`, `assignment`, `roster`, dotfiles, and similar), applied before ingest. Deterministic
rather than model-mediated, because ingest must not depend on a model call. The genuinely
ambiguous cases — a file that might be an essay, a submission in an unexpected language, a scan
of something that is not an essay — remain the triage tier's job (KAR-315).

**What made it findable:** the end-to-end test asserted `len(dispatched) == 16` against a hand
counted expectation. An assertion that had said "every dispatched unit reaches a terminal
state" alone would have passed — MANIFEST reached one.

### 2026-08-13 — The entailment disagreement rate, and the pre-committed branch we took

**First live run, 16 submissions, `gemini-3.6-flash` + `gemini-3.5-flash-lite` on Vertex AI at
temperature 0.** This is the measurement KAR-310 required be taken before anything was tuned,
with the response to it pre-committed *before* the number existed: ≤8% accept; >8% buys
exactly one prompt-revision cycle; still >8% means accept, report, and use "validator"
language everywhere.

**Measured on prompt_version p1: 10 disagreements over 74 cited observations = 13.5%.**
Above the bar. One revision cycle, and one only.

**What the number turned out to mean.** Seven of the ten disagreements were the same shape:

> **claim:** "States a position in the second paragraph and returns to it in the conclusion."
> **reason:** "The passage consists of only a single paragraph, so it cannot contain a
> concluding paragraph."

The checker was correct about what it had been shown. The analyst was correct about the
document. **The check was scoped wrong.** Entailment was being handed only the cited span,
and several rubric criteria — organization and coherence, thesis governance, engagement with
counterarguments — are *inherently document-level*. No single paragraph can entail "returns to
this in the conclusion". Those criteria were unfalsifiable by construction: they escalated
every time, and the anomaly queue filled with the system disagreeing with itself.

That is a much better problem than "the model is unreliable", and it is only visible because
the rate was measured before anything was tuned. Tuning first would have produced a lower
number and left the scoping error in place.

**The revision (the one permitted cycle).** The entailment checker now receives the cited
passage *and* the full submission, and is told which kinds of claim to check against which:
sentence-level claims against the passage, structural claims against the document, and to
answer "unsupported" only when the submission genuinely does not do what the claim says. The
quote's presence and position remain checked deterministically by layers 1–3; this layer only
ever judged support. Separately, the analyst is now told never to write span IDs into
observation prose — two claims had leaked `sp-0002` into text an instructor reads, which also
made them unverifiable against the document.

**Measured on prompt_version p2: 5 disagreements over 74 = 6.8%.** At or below the bar, so the
accept branch applies. No further tuning is permitted and none was done.

**The survivors are the layer working.** The five remaining escalations are genuine catches,
not noise:

- *"The submission cites both Grimaldi and Oyelaran with parenthetical page numbers, but
  Oyelaran supports arguments regarding urban density cost structures rather than
  administrative staffing."* — a real mischaracterisation of a source.
- *"The claim mentions sources such as Aberdene and Castellanos, but Castellanos is not
  present in the cited passage."* — a real precision failure in the citation.
- *"While the submission states the position in the opening section, it does not return to
  this claim in the conclusion."* — arguable, which is exactly why it goes to a human rather
  than being resolved by the system.

**Everything else measured on the same run:**

| | |
|---|---|
| observations | 75 across 15 submissions |
| first-attempt acceptance | 63 / 74 = **85.1%** |
| accepted after bounded retry | 5 |
| attempt cap reached → `NEEDS_HUMAN` | 1 |
| `no_evidence` | 1 (s12 c4, exactly as planted) |
| injection detected, analysis proceeded | 1 (s07, exactly as planted) |
| unparseable → `TaskFailed` | 1 (s16, exactly as planted) |
| model calls, cold cache | 21 |
| warm-cache hit rate | 21 / 21 = **100%** |

Every planted fixture behaved as its manifest entry predicted, on a live run, with no
special-casing anywhere in the pipeline.

**Still not measured:** the dollar cost. 21 live calls executed, but the figure has to be read
from the Cloud Billing console rather than derived from token counts — `gemini-3.6-flash` bills
thinking tokens (222 on a 32-token prompt in one smoke test), so a token-arithmetic estimate
would understate it. It stays "not yet measured" until someone reads the console.


### 2026-08-13 — Two invariants that were false, found by an external review

An external judge reviewed the repository against the contest rubric and falsified two claims
this README made. Both were real, both are fixed, and both were the kind of defect that local
tests cannot catch because local tests do not evaluate IAM and do not observe process exit.

**1. The grades boundary did not exist on the deployed path.**

The claim was "no pipeline identity can write `grades/`". The provisioning script bound the
custom append-only role at **project scope with `--condition=None`**, and that role grants
`datastore.entities.create`.

`datastore.entities.create` cannot be scoped to a collection. It authorises creating a
document anywhere in the database. And the Firestore **server SDK does not evaluate Security
Rules** — server clients are authorised by IAM alone, so `deploy/firestore.rules` was
protecting the browser path only. A pipeline service account could have run
`db.collection("grades").document(uuid).create({"grade": "A"})` and succeeded.

Worse, **the test could not have caught it.** It attempted `grades.document("s01").set({...})`
and expected `PermissionDenied`. A `.set()` with no precondition is an upsert and can require
*update* permission — which the role withholds — so it would be denied for a reason unrelated
to the boundary under test, while a `.create()` on a fresh document still succeeded. A green
check measuring the wrong operation.

*Fixed:* grades moved to a **separate Firestore database** (`karani-grades`) that no pipeline
identity is bound to at all, and the append-only binding now carries an IAM condition naming
the events database. The deployed test attempts a **fresh-document create**, plus a create in a
collection nobody has ever named — because the boundary is the database binding, not a
collection's spelling.

*The part that mattered most:* this had to be fixed **before** recording the
`PERMISSION_DENIED` camera beat. Filming the old operation would have shown a denial that
proved nothing and implied a guarantee the policy did not enforce.

**2. `T_max` bounded the run but not the process.**

Karani had already fixed one timeout defect and believed the liveness claim held. It did not,
and the reason is documented Python behaviour rather than a bug:

- `shutdown(wait=False, cancel_futures=True)` cancels *pending* futures. A **running** future
  cannot be cancelled — there is no way to interrupt a thread from outside it.
- `ThreadPoolExecutor` registers an atexit hook that joins its workers, so the interpreter
  will not exit while one is blocked.

The existing tests used a worker that slept and then returned, which is the realistic case and
not the hard one. With a worker that **never** returns, `run_pipeline` completes perfectly —
`TaskAbandoned` written, artifact rendered — and the process sits there until Cloud Run's task
timeout kills it.

*Fixed:* `karani/runtime.py` provides `hard_exit`, called by the entrypoint once the artifact
is durable. It lives outside the library because nothing importable into someone else's process
should call `os._exit`. Verified by mutation: with `hard_exit` disabled the subprocess test
times out at 25 seconds against a 2-second `T_max`; with it, the process exits cleanly.

**A detail worth keeping.** The suite now leaves blocked worker threads alive in pytest's own
interpreter, because `test_join_liveness.py` blocks them deliberately and Python cannot reap
them. That is not a test-hygiene problem to paper over — it is the production failure mode,
reproduced in miniature, in the very process asserting it does not happen.

**Also corrected from the same review:** the hosted docket was serving a committed fixture
while the Cloud Run Job wrote Firestore — two disconnected chains presented as one narrative.
The docket now folds the latest run from the configured store, with the committed run as an
explicitly-labelled fallback. And ratification now reads grades from the instructor's own
database rather than an empty dict, so "the instructor enters the grade and Karani exports it
without ever generating it" is a path that runs rather than a sentence.

---

### 2026-08-28 — Submission hardening: a correct local build is not deployed proof

**Measured local verification.** `make test` completed with **162 passed, 5 deselected** in
14.70 seconds on the local machine. `make lint`, `make compliance`, and the static-docket
render also passed. These are local measurements only; none is presented as deployed timing or
as evidence that Google Cloud execution succeeded.

**Cloud discovery.** The configured project is `asili-xprize-2026`; authenticated read-only
inspection found billing enabled and two unrelated Cloud Run services. Cloud Scheduler is not
enabled in that project. No Karani resource was created or modified in this session. Enabling
the API and creating the `karani-events` and `karani-grades` databases are external changes,
with named Firestore database creation effectively irreversible, so they remain a deliberate
release gate rather than an inferred action.

**Finding: the recording plan promised the wrong execution surface.** `deploy.sh` creates one
Cloud Run Job task (`--tasks=1`, `--parallelism=1`), while the runbook promised a 15-task Cloud
Run grid. The code's actual fan-out is a `ThreadPoolExecutor` owned by the dispatcher, because
that owner must write `TaskAbandoned` at the join deadline. Raising Cloud Run task count alone
would not make the claim true: each task would receive the whole source directory and would
render independently, without cross-task terminal-state joining.

*Fix:* the deployed command now passes `--workers 15`; diagrams, PRD, README alt text, and
the video runbook describe one Cloud Run Job with a bounded 15-worker analyst pool. This is not
a scale measurement. The scale metrics stay "not yet measured" until one deployed run records
them.

**Finding: the static-docket command crashed after successful output.** The documented
`--out out/static-docket` form wrote all pages, then called `Path.relative_to()` with a
relative path against an absolute repository root and exited nonzero while printing its final
line. The renderer now resolves output paths and prints either a repository-relative or
absolute path. A regression test invokes it from outside the repository with a relative output
argument.

**Finding: words about the grades boundary must be as exact as the IAM.** Several
submission-facing surfaces still said “separate collection,” even though the project had
already corrected the implementation to two Firestore databases. A collection cannot scope
`datastore.entities.create`; repeating that stale phrase would have undermined the strongest
architecture claim. README, PRD, Devpost draft, docket challenge page, and both diagrams now
say “separate Firestore database.” `make release-check` fails on a regression in those
surfaces.

## The Gemma bonus costs more than the checklist implied

**Measured 2026-08-31.** The bonus point for "an additional Google AI model" is scored on
Gemma actually running, and the manual checklist carried it as a short step: `ollama pull
gemma3:4b`, restart, done. Two things were wrong with that.

The first is fixed elsewhere: `config.py` defaulted `MODEL_TRIAGE` to `gemma-3-4b-it`, the
Vertex model-garden name, while the local tier talks to Ollama, which registers the model as
`gemma3:4b`. Following the checklist exactly still produced `gemma_available: false` on every
submission, with the operator looking at `ollama list` showing the model present.

The second is not fixable from here. **Gemma is not served as a managed publisher model on
Vertex.** `generate_content` against `gemma-3-4b-it`, `gemma-3-12b-it`, `gemma-3n-e4b-it` and
`google/gemma-3-4b-it` returns 404 `Publisher model not found`, in both `global` and
`us-central1`. Gemma on Vertex means deploying a Model Garden endpoint onto a GPU — real cost,
roughly twenty minutes, and a resource `teardown.sh` then has to remove.

So the bonus has two routes and neither is free:

- **Local:** install Ollama, `ollama pull gemma3:4b` (~3.3 GB), run with
  `KARANI_MODEL_TRIAGE=gemma3:4b`. Now that the default is correct, this works — but it is a
  download, not a flag.
- **Vertex:** deploy a Model Garden endpoint. Costs GPU-hours for as long as it exists.

Recorded because the checklist previously implied a one-liner, and an entrant reading it at
4pm on the deadline would have discovered otherwise at the worst possible moment. The tier
itself is real and tested; it reports `gemma_available: false` and falls back to deterministic
heuristics **under their own name**, never borrowing Gemma's.
