# Compliance record

Answers to the contest's eligibility and submission questions, with evidence. Items marked
**OPEN** are unanswered and are carried on the manual checklist; an open item here is not a
passing item elsewhere.

---

## Mandatory technical requirements

| Requirement | Karani's answer | Status |
|---|---|---|
| Gemini 3.5 or newer, via Gemini API or Vertex AI | `gemini-3.6-flash` (analysis) and `gemini-3.5-flash-lite` (entailment, lint assist), via **Vertex AI**. Pinned ID strings, never aliases. Both are ≥3.5. See [DEVIATIONS.md](DEVIATIONS.md) D-001 for why the PRD's `gemini-3.5-pro` was not used — it does not exist — and why `gemini-3.1-pro-preview` would have **failed** this requirement | **VERIFIED.** Both IDs resolved against live Vertex AI, and 187 responses from two real 16-submission runs are committed in `fixtures/cache/` |
| ≥1 Google Agent Framework | **Google ADK** (orchestration) and **GenAI SDK** (model access), dual-listed | Pinned; see [antigravity/decision.md](antigravity/decision.md) |
| ≥1 Google Cloud infrastructure service | Cloud Run Jobs (analysis fan-out), Cloud Run service (docket), Firestore (event log + claims), Cloud Scheduler (nightly trigger) | Scripted and complete (`scripts/bootstrap_gcp.sh`, `scripts/deploy.sh`); **NOT YET DEPLOYED** — this is the one mandatory requirement still unapplied |

## Category

**The Taskmaster.** The Stage Two criteria are written against a differently-named set
("The Continuous Action Engine"); Karani's copy answers both readings. The Continuous Action
Engine bullets ask for a multi-step background workflow completed without human intervention
and for the Bring Your Own Friction mandate — Karani is an unattended overnight batch run
over one named instructor's real grading load.

## Project newly created in the Submission Period

- First commit: recorded in the README on the first push.
- History is unsquashed and never rebased; the public commit log is the evidence.
- `git log --before=2026-08-03` audit: **CLOSED for this repository.** All 33 commits
  fall inside the Submission Period; the first is dated 2026-08-12, and `git log
  --before=2026-08-03` returns 0 commits. Reproduce with:

  ```
  git log --before=2026-08-03 --oneline | wc -l    # expect 0
  git log --reverse --format='%ad' --date=short | head -1
  ```

  The scope of this check is what the tooling can establish: that no commit in *this*
  repository predates the period. Whether code was carried in from a repository not
  represented here is not something a git history can answer, and the entrant's declaration
  covers it. The row previously read "across every repository that might contribute code",
  which promised an audit no command in this repo can perform.
- Design lineage with the sibling entry is disclosed as **pattern, not code**, in the README
  under `## Relationship to my other submissions`.

## Startup Excellence eligibility — **NOT PURSUED** (decided 2026-08-31)

The prize requires submitting on behalf of an incorporated organization **and** providing a
corporate email address. Three questions, none yet answered in writing:

1. Does the Asili mailbox receive mail? (Remediation for MX propagation has a 1–2 day tail,
   so this is time-critical, not administrative.)
2. Does Devpost enforce the corporate-email condition at **account** level or at
   **submission** level?
3. Does entering as a company foreclose the Individual/Hobbyist pool for this entry?

The Devpost account on file uses an `@bu.edu` address, which is an educational domain and not
a corporate one.

**Decision, on submission day: this prize is not pursued.** None of the three questions can be
answered in the hours remaining, MX remediation alone has a 1–2 day tail, and question 3 is the
decisive one — entering as a company plausibly forecloses the Individual/Hobbyist pool, which is
a lane this entry is genuinely competitive in. Trading a lane we qualify for against one we
cannot document is the wrong trade. No submission copy asserts Startup Excellence eligibility.

## Budget and endpoint fencing

- Budget alerts at **$25 / $50 / $100 / $140**: **OPEN** — to be armed in the console.
- Deploy project: **`asili-xprize-2026`** (billing enabled). `asili-61171` was abandoned for lack of billing and is untouched.
- Split: **$95 dev / $40 recording / $15 Sept–Oct uptime**.
- Billing alerts lag up to 24 hours. Actual billing is read daily during recording week
  rather than trusted to alerts.
- Endpoint fencing (KAR-008): any billable endpoint created by script is torn down by script
  the same day. `bootstrap_gcp.sh` and `teardown.sh` ship as a pair, and the pair exists
  before any endpoint is created.

## Friction measurement (KAR-205) — **OPEN**

Pilot-instructor stopwatch sessions, n≥3, on a real rubric. Session dates: **OPEN**.
Disclosed fallback if the sessions do not happen: self-timed grading of the fixture set under
the same rubric, labelled as self-measurement in both the README and `metrics.json`. The
fallback is disclosed rather than substituted silently.

## Data provenance

No real student data appears anywhere — not in the repository, the fixtures, the video, or
the hosted instance. Every submission in `fixtures/` is synthetic and authored for this
project; the scale corpus is generated from a committed seed and disclosed as generated. No
real company or person is named as a bad actor in any fixture, test, comment, or line of copy.

## Submission checklist

| Item | Status |
|---|---|
| Hosted project URL, loads logged-out | **OPEN** |
| Public repository URL | https://github.com/Jeremiah-Sakuda/Karani |
| README with spin-up instructions, `make demo` on line 1 | **DONE** — verified from a clean clone |
| Architecture diagram | **DONE** — `docs/architecture/diagram_a_system.svg` (+ PNG) and `diagram_b_identity.svg`, both embedded in the README |
| Demo video ≤4:00, public on YouTube or Vimeo, English | **OPEN** |
| Text description in PRD §1.3 order | **OPEN** |
| Bonus: blog post with the created-for-this-hackathon language | **OPEN** |
| Bonus: social post carrying `#AllThingsAgenticHackathon` | **OPEN** |
| Bonus: additional Google AI model (Gemma triage tier) | **OPEN** |
