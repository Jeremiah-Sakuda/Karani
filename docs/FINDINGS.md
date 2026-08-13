# Findings

Appended every build day. Two kinds of entry: **measured numbers** (with the method that
produced them) and **Google-toolchain findings** (where the tools fit or fought this design).

Standing rule: if a measurement does not exist, this file says "not yet measured." A
plausible number is never a substitute for a measured one. Genuine failures are publishable
findings; polished fabrications are defects.

---

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
- What the Model Armor surface allows on this account tier — **not yet measured**
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
