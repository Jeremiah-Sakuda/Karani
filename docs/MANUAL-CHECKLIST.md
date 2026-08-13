# What only you can do

**Updated 2026-08-13.** Ordered by urgency. Item 1 is first because it is the only thing here
that cannot be recovered by working harder later.

---

## Already closed

| Was on this list | Now |
|---|---|
| Enable billing | Switched to **`asili-xprize-2026`**, which already has it. `asili-61171` is untouched |
| `gcloud auth application-default login` | Not needed. Karani falls back to the gcloud CLI's own token when ADC is absent — same identity, obtained differently, nothing stored |
| Record the offline demo cache | **Done.** 187 responses from a real 16-submission run, committed. `make demo` runs the whole pipeline offline, 21 of 21 calls from cache |
| Confirm the pinned model IDs resolve | **Done.** `gemini-3.6-flash` and `gemini-3.5-flash-lite` both verified against live Vertex AI |
| Measure the entailment disagreement rate | **Done.** 13.5% → the one permitted revision cycle → 6.8%. Accept branch. Recorded in FINDINGS and metrics.json |

---

## 1. Start the Scheduler execution-history clock — **tonight**

KAR-410's acceptance criterion is *"execution history shows ≥7 nightly runs by recording day."*
That clock starts only when the schedule exists. A schedule created on the 23rd cannot show
seven nights of history on the 24th, and no amount of later effort recovers it. The job body
does not have to be real yet.

```bash
./scripts/bootstrap_gcp.sh asili-xprize-2026
```

**Read this before running it.** `bootstrap_gcp.sh` creates a Firestore `(default)` database in
`asili-xprize-2026`, and **creating a Firestore database is effectively irreversible** — you
cannot delete it, and it fixes the project's Firestore mode permanently. That project currently
has no Firestore and three live Cloud Run services (`asili-agents`, `asili-web`,
`eleza-gemini-proxy`). Karani never touches those, and `teardown.sh` only removes resources
named `karani-*`. But the Firestore decision is one-way, so make it deliberately.

Then start the clock:

```bash
./scripts/deploy.sh asili-xprize-2026 --scheduler-only
```

## 2. Deploy the Firestore rules — Firebase CLI, not gcloud

There is no `gcloud firestore rules` command. The rules guard the **browser** write path to
`grades/`; the custom IAM role guards the **service-account** path. Neither substitutes for the
other, and skipping this leaves `grades/` writable from a browser session.

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

**Install Ollama** for a genuinely local Gemma tier: `brew install ollama && ollama pull gemma3:4b`.
Triage currently runs its deterministic fallback and records that honestly on every
`TriageDecided` event. Gemma is worth +0.2 as an additional Google AI model.

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
