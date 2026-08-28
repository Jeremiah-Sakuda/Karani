# Build log

One entry per working session, appended at the end of that session. The log is a
deliverable, not bookkeeping.

**A note on this log's shape, stated plainly because a judge can check it against the commit
timestamps.** PRD §6 lays out a ten-session calendar running Aug 11–30. This build did not
follow that calendar; it was compressed into a smaller number of long sessions starting
Aug 12. The entries below record the sessions that actually happened, on the dates they
actually happened. No entry has been backdated and no session has been invented to make the
authorship trail look longer than it was. All work falls inside the Aug 3–31 Submission
Period, which is what the contest rules require; the twenty-day appearance was a planning
artifact, not a requirement.

---

### 2026-08-12 — Phase 0: foundations, compliance tooling, and a model that does not exist

**Prompt (verbatim):**
> Here we have a new repo and project. I want you to complete it end to end, ending wth a final list of things I need to do by hand.  This is for this hackathon, so at the end, run a judging panel against these rules, and implement any improvements that are worthwhile to maximize winning probability

*(followed by the full text of the All Things Agentic Hackathon Official Eligibility and Rules)*

**Course corrections:**
- > "You should have access to the google cloud cli, use the asili project for this"
- > "The repo is brand new at https://github.com/Jeremiah-Sakuda/Karani I want frequent commits as you proceed, do not list claude as a contributor or co author of any commits"

**Outcome:** Repository skeleton per AGENTS.md, with the compliance tooling, gates, and
measurement contract in place before any application logic. `.gitignore`, `gitleaks` config,
`.env.example` documenting every variable the system will ever read, `Makefile`, and the
docs scaffolding all landed.

The session's real result was a finding rather than a feature: **`gemini-3.5-pro`, which the
PRD pins for analysis, does not exist.** The Gemini 3.5 family is Flash and Flash-Lite; the
newest Pro-tier model is `gemini-3.1-pro-preview`, which is *older* than the contest's
mandatory "Gemini 3.5 or newer" bar. Building to the PRD's letter would have produced a
submission that failed Stage One on its most load-bearing requirement, and would have failed
silently until the first live call.

Also surfaced: `make compliance` fails against the PRD itself. `KAR-330` is cited in §2's
infrastructure row and defined nowhere in §4, and §2 uses the range notation its own preamble
forbids. The checker built to catch orphans caught three on its first run, in the source
document.

No acceptance criteria pass yet — no application logic exists by design (K0's own
instruction). Nothing is measured; `docs/metrics.json` is entirely "not yet measured", which
is the correct state for it today.

**Key decisions:**

1. **Analysis pinned to `gemini-3.6-flash`, not to the newest Pro model.** Rejected
   `gemini-3.1-pro-preview`, which was the intuitive repair once 3.5 Pro turned out not to
   exist — it satisfies the PRD's "Pro tier" intent and fails the contest's version bar, and
   only one of those two is graded pass/fail. Rejected `gemini-3.5-flash` as well: compliant
   and adequate, but 3.6 Flash is strictly newer and carries the 1M context window that the
   no-vector-database argument in §1.4 leans on.

2. **`make demo` runs on a file-backed store rather than the Firestore emulator.** The
   emulator needs Java, which is absent here and on most judges' machines, so the PRD's
   `make demo` would fail on README line 1 — the worst possible place for a failure. Rejected
   emulator-only-with-a-documented-Java-requirement: maximally faithful, minimally likely to
   run. The emulator survives as `make demo-emulator` and still carries KAR-102's
   client-surface assertion. This weakens nothing: KAR-103 already required the replay path
   to run with no emulator and no credentials.

3. **The PRD's defects were fixed in the PRD, not tolerated in the checker.** Rejected
   relaxing `compliance.py` to accept range notation. A checker edited until it passes is
   worth less than no checker, and the ranges are exactly the "coverage asserted rather than
   enumerated" pattern §2's preamble exists to forbid.

**Requirements touched:** KAR-001, KAR-002, KAR-005, KAR-006, KAR-007, KAR-008, KAR-020

### 2026-08-12 — The whole build, and a panel that falsified it

**Prompt (verbatim):**
> Here we have a new repo and project. I want you to complete it end to end, ending wth a final list of things I need to do by hand.  This is for this hackathon, so at the end, run a judging panel against these rules, and implement any improvements that are worthwhile to maximize winning probability

**Course corrections:**
- > "You should have access to the google cloud cli, use the asili project for this"
- > "The repo is brand new at https://github.com/Jeremiah-Sakuda/Karani I want frequent commits as you proceed, do not list claude as a contributor or co author of any commits"

**Outcome:** Phases 0 through 6 built and pushed: the spine, the fixtures, the analysis path,
the docket, delivery, the deploy scripts, both architecture diagrams, the README, the
recording run-book, and the submission drafts. 154 tests; all five CI steps green.

The session's real value was the closing judging panel. Seven judges scored the submission
against the contest rubric with a mandate to falsify its claims, and they earned their keep:
they proved three runtime invariants false *by execution* and found that the deployed path
could not start at all, because `store/firestore.py` did not exist while `deploy.sh` set
`KARANI_STORE_BACKEND=firestore`. Every manual step could have been performed perfectly and
the Cloud Run Job would still have died before writing one event.

Three defects shared a shape worth naming: **working code with no caller.** ADK, Gemma triage,
and delivery were each well-implemented and unreachable. A reader checking "is ADK used?"
finds a file that uses ADK; only a grep for callers reveals that nothing invokes it. The
mandatory Agent Framework requirement was being satisfied by a module the program never ran.

Nothing is measured. `docs/metrics.json` carries offline measurements labelled `surface:
local` and leaves every deployed and cost figure at "not yet measured", because the project
has no billing and no model call has ever executed.

**Key decisions:**

1. **Analysis pinned to `gemini-3.6-flash` after finding the PRD's model does not exist.**
   Rejected `gemini-3.1-pro-preview`, the intuitive repair once 3.5 Pro turned out to be
   fictional: it satisfies the "Pro tier" intent and fails the contest's "3.5 or newer" bar,
   and only one of those is graded pass/fail.

2. **The offline demo refuses to fabricate model output.** Rejected a stub client that would
   have made `make demo` succeed today. A stubbed response makes the offline demo a different
   system from the one in the video, and a judge who ran both and compared would be right to
   distrust everything else in the repository. It explains itself and falls back instead.

3. **The panel's Veo/Lyria recommendation was rejected.** It offered +0.4 of bonus for
   integrating additional Google AI models. Both would be gratuitous in a grading-evidence
   tool, and gratuitous integration costs more in Architectural Discipline than the bonus
   returns.

**Requirements touched:** KAR-001, 002, 005, 006, 007, 008, 020, 101, 102, 103, 104, 105,
201, 202, 203, 204, 206, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 313, 314,
315, 316, 318, 319, 330, 401, 402, 404, 405, 406, 412, 413, 501, 502, 503, 504, 505, 506

### 2026-08-28 — Submission credibility hardening

**Prompt (verbatim):**
> This is a submission for this hackathon [https://allthingsagentichackathon.devpost.com/](https://allthingsagentichackathon.devpost.com/) [https://allthingsagentichackathon.devpost.com/rules](https://allthingsagentichackathon.devpost.com/rules) evaluate it as a judge, and score it. Present your findings the way you would to a panel of judges, be thorough and very detailed, then suggest improvements to the team

**Course corrections:**
- > When done, implement all the improvements yourself
- > proceed

**Outcome:** The panel assessment found a technically strong but submission-incomplete entry:
the local system and its evidence trail are credible, while hosted deployment, deployed-path
IAM proof, scale evidence, user-friction measurement, video, and public links remain absent.
The repository now mechanically distinguishes those states. `make release-check` protects
local, judge-facing claims; `make submission-check` deliberately fails until the required
live measurements and publication evidence exist.

Corrected every submission-facing reference to the former shared-collection IAM model: grades
are in a separate Firestore database, which is the actual boundary. Corrected a second
credibility defect: the deployment creates one Cloud Run Job with an internal bounded worker
pool, not a 15-task Cloud Run grid. Deployment now explicitly configures 15 workers, and the
architecture and recording plan name that shape precisely. The documented static-docket
command also had a relative-output-path crash after writing its files; it is fixed and
regression-tested.

Local evidence: 162 tests passed (five cloud-dependent tests deselected), Ruff and mypy
passed, compliance enumerated all 72 requirements, and the static docket rendered from the
recorded log. The strict submission check remains red for real missing evidence; it was not
relaxed.

**Key decisions:**

1. **Correct the Cloud Run story to a 15-worker pool, not a fictitious task grid.** Rejected
   changing Cloud Run `--tasks` to 15 without a sharding and cross-task terminal join, which
   would duplicate input or render partial artifacts. The existing dispatcher safely owns the
   join inside one Job, so the deploy configuration and video should show that truth.
2. **Make unperformed deployed proof a failing release gate.** Rejected replacing Devpost
   placeholders or compliance entries with plausible values. `submission-check` names the
   missing hosted URL, video, scale, timing, and instructor-friction evidence instead.
3. **Do not provision cloud resources in this session.** Read-only cloud inspection confirmed
   the project and billing account are available, but Cloud Scheduler is disabled. Bootstrap
   would enable APIs and create two Firestore databases, an effectively irreversible external
   change; the authenticated action remains explicitly gated rather than inferred from a
   repository-hardening request.

**Requirements touched:** KAR-205, KAR-306, KAR-312, KAR-317, KAR-320, KAR-410, KAR-411,
KAR-412, KAR-501, KAR-503, KAR-505, KAR-603, KAR-607, KAR-624
