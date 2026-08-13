# What only you can do

Ordered by urgency, not by phase. Items 1–3 are time-critical: **item 3 gets worse every day
you wait and cannot be recovered by working harder later.**

Everything not on this list is done and committed.

---

## Today — these three block everything downstream

### 1. Enable billing on the deploy project

Nothing has been deployed and no model call has ever run, because `asili-xprize-2026` has billing
disabled. You have an open **Deployment Billing** account already powering `hodi-2026`.

```bash
gcloud billing projects link asili-xprize-2026 --billing-account=015ACB-BA3DCD-D7BD7F
```

*Why not me:* linking a billing account is a financial account change.

### 2. Grant application default credentials

The Vertex SDK needs ADC; a `gcloud` login is not the same thing.

```bash
gcloud auth application-default login
gcloud config set project asili-xprize-2026
```

*Why not me:* it is a browser OAuth flow.

### 3. Start the Scheduler execution-history clock — **do this first, tonight**

KAR-410's acceptance criterion is *"execution history shows ≥7 nightly runs by recording
day."* That clock starts only when the schedule exists. A schedule created on the 23rd cannot
show seven nights of history on the 24th, and no amount of later effort recovers it. The job
body does not have to be real yet.

```bash
./scripts/bootstrap_gcp.sh asili-xprize-2026
./scripts/deploy.sh asili-xprize-2026 --scheduler-only
```

*Why not me:* depends on items 1 and 2.

---

## This week

### 4. Record the offline demo cache — **this is what makes README line 1 work**

Right now `make demo` cannot replay model output, because no model call has ever executed. It
explains itself and falls back to the reference docket, but a judge running the first line of
your README should see the real pipeline. One live run fixes this permanently, for everyone.

```bash
make record-cache
git add fixtures/cache && git commit -m "chore: record the offline demo cache" && git push
```

Cost: roughly one run — single-digit dollars. **Highest-value item on this list after the
three above.**

### 5. Confirm the pinned model IDs resolve

```bash
make venv && PYTHONPATH=src .venv/bin/python -m karani.cli preflight
```

Expect `OK analysis gemini-3.6-flash` and `OK verify gemini-3.5-flash-lite`. If either fails,
the model was renamed or withdrawn — fix `src/karani/config.py` before deploying, and record
the finding in `docs/FINDINGS.md`. **Do not substitute a Gemini 3.1 model:** it is older than
3.5 and fails the contest's mandatory requirement. That trap is documented in
`docs/DEVIATIONS.md` D-001.

### 5b. Deploy the Firestore rules — needs the Firebase CLI, not gcloud

`bootstrap_gcp.sh` provisions everything else, but Firestore security rules are deployed by
the Firebase CLI; there is no `gcloud firestore rules` command. The rules guard the **browser**
write path to `grades/`; the custom IAM role guards the **service-account** path. Neither
substitutes for the other, and skipping this leaves `grades/` writable from a browser session.

```bash
npm i -g firebase-tools && firebase login
firebase deploy --only firestore:rules --project asili-xprize-2026
```

*Why not me:* `firebase login` is a browser OAuth flow.

### 6. Arm the budget alerts

$25 / $50 / $100 / $140, at https://console.cloud.google.com/billing/budgets. Alerts lag up to
24 hours, so read actual billing daily during recording week rather than trusting them.

*Why not me:* needs billing-account-level permissions.

### 7. Answer the Startup Excellence eligibility questions

Three questions, unanswered, recorded as **OPEN** in `docs/compliance.md`:

1. Does the Asili mailbox receive mail? *(MX propagation has a 1–2 day tail — this is
   time-critical, not administrative.)*
2. Does Devpost enforce the corporate-email condition at **account** level or **submission**
   level?
3. Does entering as a company foreclose the Individual/Hobbyist pool for this entry?

Your Devpost account is on `jsakuda@bu.edu`, an educational domain. Until question 2 is
answered, Startup Excellence eligibility is unproven and no submission copy asserts it.

### 8. Book the friction measurement (KAR-205)

The README's headline claim is falsifiable only if it is measured. Stopwatch sessions with the
pilot instructor on their real rubric, n ≥ 3. Disclosed fallback if the sessions don't happen:
self-time yourself grading the fixture set under the same rubric, and label it as
self-measurement in both the README and `metrics.json`. **Disclose the fallback; don't
substitute it silently.**

---

## Before recording

### 9. Deploy for real, then run once at scale

```bash
./scripts/deploy.sh asili-xprize-2026
gcloud run jobs execute karani-run --region=us-central1
make scale && KARANI_MODEL_BACKEND=vertex .venv/bin/python -m karani.cli run --source fixtures/scale --live
```

The scale run costs roughly $4–6. Run it **once**, cache everything, capture the class-overview
frame. Every number it produces goes into `docs/metrics.json`.

### 10. Fill in metrics.json, then check nothing is unsourced

Every number in the README, both diagrams, the Devpost copy, the blog, and the video must
exist in `docs/metrics.json` first. It currently reads **"not yet measured" throughout**, which
is correct for today and must not be true on submission day.

The Devpost copy uses explicit `[MEASURED: …]` placeholders. Replace each from a real run, or
**delete the sentence.** Never estimate.

### 11. Run the deployed-path negative tests

```bash
GOOGLE_CLOUD_PROJECT=asili-xprize-2026 .venv/bin/pytest -m deployed -v
```

This is what licenses the phrase *"structurally impossible."* Until it passes, the language
discipline holds: say *"no field can carry a verdict into any downstream system, and no
aggregate can be computed."*

### 12. Verify the hosted docket logged out

Private window, different network, not signed in. `https://<service>.run.app` and
`/challenge`. "It worked while I was signed in" is not the check.

---

## Recording and publishing

### 13. Record the video

Follow `docs/RUNBOOK.md` beat by beat — it has the exact commands, the tabs to have open, and
which precondition each beat depends on. **Hard cap 4:00, target 3:45.**

Non-negotiable: the burned-in lower third from second 1, the live `--now` trigger with
Scheduler history visible, the six-outcome divergence tour, and the `PERMISSION_DENIED` denial
in the live console. Upload **public** (not unlisted) to YouTube or Vimeo, in English.

Say no number that is not in `metrics.json`.

### 14. Publish the blog

`docs/submission/blog.md` is written. It must be **public, not unlisted**, and must keep the
sentence *"I created this piece of content for the purposes of entering the All Things Agentic
Hackathon."* Worth +0.2.

### 15. Publish the social posts

`docs/submission/social.md` has a teaser and a launch post. Both **public**, both carrying
**`#AllThingsAgenticHackathon`**. Worth +0.2.

### 16. Submit on Devpost

Category: **The Taskmaster**. Paste `docs/submission/devpost.md` with the placeholders filled.
Attach both architecture diagrams. Include the hosted URL, the repo URL, the video URL, the
blog URL, and the social URLs.

Repository is public, so no access grant is needed — but if you make it private, grant
`testing@devpost.com` and `cloudhackathons@google.com`.

**Deadline: Aug 31 2026, 5:00 PM PT.** Submit Aug 30. Aug 31 is slack, not schedule.

---

## Optional

### 17. Install Ollama for the local Gemma tier

```bash
brew install ollama && ollama pull gemma3:4b
```

Gemma is worth +0.2 as an additional Google AI model, and is deliberately not load-bearing —
a bonus item must never take a mandatory item hostage.

### 18. Consider whether more bonus models are worth it

Up to +0.6 is available for additional Google AI models. Gemma is a genuine fit. Veo and Lyria
would be gratuitous in a grading-evidence tool, and gratuitous integration is likely to cost
more in the Architecture score than the +0.4 gains. My recommendation is to stop at Gemma.

---

## What is already done

Repository public and pushed · 137 tests green with no credentials · compliance checker passing
on 72 enumerated requirements · 16 fixtures with every planted behaviour verified · both
architecture diagrams as SVG and PNG · README with every required section · deploy, bootstrap
and teardown scripts · Firestore rules, custom IAM role and the negative-test matrix · the
recording run-book · Devpost, blog and social drafts.
