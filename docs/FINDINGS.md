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
