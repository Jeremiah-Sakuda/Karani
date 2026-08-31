# What only you can do

**Updated 2026-08-31, deadline day.** Ordered by urgency. Everything a script can do has been
done; what is left needs your account, your voice, or your judgement.

Six independent review passes ran against this repository. The last one scored it 2/5 and
named the pattern exactly: nearly every remaining defect was in the **narration** — README
prose, diagram captions, blog and social copy, metric method strings — and the copy
over-claimed hardest on the mechanisms that were weakest. Those are fixed; the detail is in
the commit log. Two are worth knowing about because they change what you film:

- `karani verify` passed a tampered artifact. It compared a hash of the events against a hash
  of the events and never looked at the artifact body — so a file with every observation
  rewritten to "this paper earns an A" verified clean, exit 0. If you demo `verify`, it now
  works; before today it was a false assurance, which is worse than not shipping one.
- **Beat 6 told you to film a disagreement with a correct observation.** Read §Beat 6 in the
  run-book before recording. Use `s01 c2`, not `s09`.

Test count went 169 → 256 today, all five gates green.

---

## Already closed

| Was on this list | Now |
|---|---|
| Enable billing | Switched to **`asili-xprize-2026`**, which already has it. `asili-61171` is untouched |
| `gcloud auth application-default login` | Not needed. Karani falls back to the gcloud CLI's own token when ADC is absent — same identity, obtained differently, nothing stored |
| Record the offline demo cache | **Done.** 187 responses from two real 16-submission runs (`p1` 93, `p2` 94), committed. `make demo` replays `p2` offline, 94 of 94 calls from cache — 21 analysis, 73 entailment |
| Confirm the pinned model IDs resolve | **Done.** `gemini-3.6-flash` and `gemini-3.5-flash-lite` both verified against live Vertex AI |
| Measure the entailment disagreement rate | **Done.** 13.5% → the one permitted revision cycle → 6.8%. Accept branch. Recorded in FINDINGS and metrics.json |

---

## 0. Re-run bootstrap before anything else — the IAM model changed

An external review found the grades boundary did not hold: the append-only role was bound at
project scope, and `datastore.entities.create` cannot be scoped to a collection. Grades now
live in a **separate Firestore database** with the events binding IAM-conditioned.

If you already ran `bootstrap_gcp.sh` before this change, run it again — it is idempotent, and
it now creates two databases and binds with a condition.

**Do not record the `PERMISSION_DENIED` beat until `pytest -m deployed` passes.** The old beat
would have filmed a `.set()`, which can be denied for the wrong reason while a `.create()`
still succeeds — a denial that proves nothing.

## 1. Start the Scheduler execution-history clock — **tonight**

KAR-410's acceptance criterion is *"execution history shows ≥7 nightly runs by recording day."*
That clock starts only when the schedule exists. A schedule created on the 23rd cannot show
seven nights of history on the 24th, and no amount of later effort recovers it. The job body
does not have to be real yet.

```bash
./scripts/bootstrap_gcp.sh asili-xprize-2026
```

**Read this before running it.** `bootstrap_gcp.sh` creates **two named Firestore databases**
in `asili-xprize-2026` — `karani-events` and `karani-grades` — and **creating a Firestore
database is effectively irreversible**. That project currently has no Firestore and three live
Cloud Run services (`asili-agents`, `asili-web`, `eleza-gemini-proxy`). Karani never touches
those, and `teardown.sh` only removes resources named `karani-*`. Named databases rather than
`(default)` both because the IAM condition is a string match on the resource name and because
it leaves `(default)` free for anything else that project ever wants.

Then start the clock:

```bash
./scripts/deploy.sh asili-xprize-2026 --scheduler-only
```

## 2. Deploy the Firestore rules — Firebase CLI, not gcloud

There is no `gcloud firestore rules` command. The rules guard the **browser** write path; the
IAM condition plus the separate database guard the **service-account** path. Neither
substitutes for the other — a service account never evaluates rules, and a browser session is
not covered by IAM conditions on service accounts.

```bash
npm i -g firebase-tools && firebase login
firebase deploy --only firestore:rules --project asili-xprize-2026
```

*Why not me:* `firebase login` is a browser OAuth flow.

## 3. Arm the budget alerts

$25 / $50 / $100 / $140 at https://console.cloud.google.com/billing/budgets. Alerts lag up to
24 hours, so read actual billing daily during recording week rather than trusting them.

*Why not me:* needs billing-account-level permissions.

## 4. Read the actual cost of the runs so far

Two full 16-submission live runs have executed (~40 model calls). `docs/metrics.json` records
the call count and deliberately leaves the **dollar figure** at "not yet measured", because
`gemini-3.6-flash` bills thinking tokens — 222 on a 32-token prompt in one smoke test — so
token arithmetic would understate it. Read it from the console and write it in, or leave it
absent. Do not estimate.

## 5. Answer the Startup Excellence eligibility questions

Recorded as **OPEN** in `docs/compliance.md`. Three questions:

1. Does the Asili mailbox receive mail? *(MX propagation has a 1–2 day tail — time-critical.)*
2. Does Devpost enforce the corporate-email condition at **account** or **submission** level?
3. Does entering as a company foreclose the Individual/Hobbyist pool for this entry?

Your Devpost account is on `jsakuda@bu.edu`, an educational domain. Until question 2 is
answered, Startup Excellence eligibility is unproven and no submission copy asserts it.

## 6. Book the friction measurement (KAR-205)

The README's headline claim is falsifiable only if it is measured. Stopwatch sessions with the
pilot instructor on their real rubric, n ≥ 3. Disclosed fallback if the sessions don't happen:
self-time yourself grading the fixture set under the same rubric, and label it as
self-measurement in both the README and `metrics.json`. **Disclose the fallback; don't
substitute it silently.**

---

## Before recording

### 7. Deploy for real, then run once at scale

```bash
./scripts/deploy.sh asili-xprize-2026
gcloud run jobs execute karani-run --region=us-central1
make scale
```

The scale run costs a few dollars. Run it **once**, cache everything, capture the
class-overview frame. Every number it produces goes into `docs/metrics.json`.

### 8. Run the deployed-path negative tests

```bash
GOOGLE_CLOUD_PROJECT=asili-xprize-2026 .venv/bin/pytest -m deployed -v
```

This is what licenses the phrase *"structurally impossible."* Until it passes, the language
discipline holds and the README says the hedged version.

### 9. Verify the hosted docket logged out

Private window, different network, not signed in. `https://<service>.run.app` and `/challenge`.
"It worked while I was signed in" is not the check.

### 10. Fill the remaining metrics, then check nothing is unsourced

`docs/metrics.json` now carries real validation numbers. Still absent: cost, every
deployed-path timing, the scale-run stats, and the KAR-205 friction numbers. The Devpost copy
uses `[MEASURED: …]` placeholders — replace each from a real run, or **delete the sentence.**

---

## Recording and publishing

### 11. Record the video

Follow `docs/RUNBOOK.md` beat by beat. **Hard cap 4:00, target 3:45.** Non-negotiable: the
burned-in lower third from second 1, the live `--now` trigger with Scheduler history visible,
the six-outcome divergence tour, and the `PERMISSION_DENIED` denial in the live console. Upload
**public** (not unlisted) to YouTube or Vimeo, in English.

Say no number that is not in `metrics.json`.

### 12. Publish the blog

`docs/submission/blog.md` is written and depends on nothing unfinished. Must be **public, not
unlisted**, and must keep the sentence *"I created this piece of content for the purposes of
entering the All Things Agentic Hackathon."* Worth +0.2.

### 13. Publish the social posts

`docs/submission/social.md` has a teaser and a launch post. Both **public**, both carrying
**`#AllThingsAgenticHackathon`**. Worth +0.2.

### 14. Submit on Devpost

Category: **The Taskmaster**. Paste `docs/submission/devpost.md` with placeholders filled.
Attach both architecture diagrams. Include the hosted URL, repo URL, video URL, blog URL, and
social URLs. The repository is public, so no access grant is needed.

**Deadline: Aug 31 2026, 5:00 PM PT.** Submit Aug 30. Aug 31 is slack, not schedule.

---

## Optional

**Install Ollama** for a genuinely local Gemma tier, worth **+0.2** as an additional Google
AI model:

```bash
brew install ollama && ollama serve &
ollama pull gemma3:4b          # ~3.3 GB
make demo                       # the tier now reports gemma_available: true
```

Budget the download, not a flag: **Gemma is not a managed publisher model on Vertex.**
`generate_content` against `gemma-3-4b-it`, `gemma-3-12b-it`, `gemma-3n-e4b-it` and
`google/gemma-3-4b-it` all return 404 in both `global` and `us-central1` (measured
2026-08-31). The Vertex route means a Model Garden GPU endpoint — real cost, ~20 minutes, and
something teardown then has to remove. Local Ollama is the cheaper of the two.

This entry previously read as a one-liner *and* pointed at the wrong model name: `config.py`
defaulted to the Vertex name `gemma-3-4b-it` while Ollama registers `gemma3:4b`, so following
this checklist exactly still produced `gemma_available: false` on all 15 submissions with the
model sitting in `ollama list`. The default is fixed. If you skip this, triage runs its
deterministic fallback and says so on every `TriageDecided` event, under its own name — never
Gemma's.

**Do not add Veo or Lyria.** The judging panel suggested it for +0.4 of bonus; both would be
gratuitous in a grading-evidence tool, and gratuitous integration costs more in Architectural
Discipline than the bonus returns.

---

## What is already done

Repository public and pushed · 154 tests green with no credentials · all five CI steps green ·
compliance checker passing on 72 enumerated requirements · 16 fixtures with every planted
behaviour verified **on a live run** · both architecture diagrams · README with measured
numbers · deploy, bootstrap and teardown scripts · Firestore rules, custom IAM role and the
negative-test matrix · the recording run-book · Devpost, blog and social drafts.
