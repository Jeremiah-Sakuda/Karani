# Recording run-book

Every beat with its exact commands, the tabs that must already be open, and the precondition
that has to be green before the camera rolls. Beats whose precondition is **not** currently
green are marked — a run-book that pretends everything is ready is a run-book that discovers
it isn't at 2 a.m. on recording night.

**Hard cap 4:00. Target 3:45.** Every number spoken on camera must exist in
[metrics.json](metrics.json) first. Validation numbers are now measured from a live run; cost,
deployed timings and the friction figures are not, and must not be spoken.

---

## Before you press record

| Precondition | State | How to make it green |
|---|---|---|
| Billing on the deploy project | ✅ green | `asili-xprize-2026` |
| Credentials for live Vertex calls | ✅ green | Karani borrows the gcloud CLI token when ADC is absent |
| Pinned model IDs resolve | ✅ green | both verified against live Vertex AI |
| Recorded run + offline cache | ✅ green | 187 responses committed; `make demo` replays 21/21 |
| Validation numbers measured | ✅ green | 85.1% first-attempt (63/74), 6.8% entailment disagreement — both derived from the committed log, not typed |
| s07 injection catch | ✅ green | fires on the live run |
| One escalated sheet for the hero edit | ✅ green | s01 and s02 both have escalations in the recorded run |
| **Grades boundary verified on the deployed path** | ❌ **not green** | `pytest -m deployed` — **beat 7 is blocked on this**; see below |
| Scheduler exists + execution history | ❌ **not green** | `./scripts/deploy.sh asili-xprize-2026`. **KAR-410's ≥7-nightly-runs AC is now unmeetable** — the clock needed to start ~Aug 24 and it is Aug 31. Film the schedule's existence and a live manual execution instead; that is what actually satisfies the contest's "demonstrate the backend is running on Google Cloud" requirement. Do not imply nightly history that does not exist. |
| Cloud Run Job + hosted docket | ❌ **not green** | `./scripts/deploy.sh asili-xprize-2026` |
| Scale-run overview frame | ❌ **not green** | one deployed run over `fixtures/scale/` |
| Cost figure | ❌ **not green** | read the billing console; do not estimate |
| Delivery folder empty | ⏸ manual | empty it so the drop is visible on camera |

Staging command for the local beats:

```bash
make docket-golden
```

---

## Beat 1 — 0:00–0:20 · the problem, and the refusal

**On screen:** the instructor's real folder of submissions. Burned-in lower third from
**second 1**: *"Karani prepares evidence. It cannot grade."*

**Say:** the friction in two sentences, then at 0:20 the thesis:
> *"Clerks prepare the case. Judges decide it. Karani is only ever the clerk."*

**Property:** the refusal is legible in the first 8 seconds to a viewer with no audio.

## Beat 2 — 0:20–0:45 · trigger it live, on Google Cloud

```bash
gcloud run jobs execute karani-run --region=us-central1
```

**Tabs already open:** the Cloud Scheduler job (schedule visible, `0 3 * * *`) and the Cloud Run
Job execution list showing this run.

**Do not claim nightly history.** KAR-410 wanted ≥7 prior nightly runs; the clock could only have
started a week ago and did not. Say *"scheduled nightly at 3 a.m., triggered here manually so you
can watch it"* — true, and it satisfies the requirement, which is proof the backend runs on Google
Cloud rather than proof of a specific run count.

**Property:** the backend really runs on Google Cloud, and the schedule is not a mock. This
is the beat that satisfies the contest's "must demonstrate the backend is running on Google
Cloud" requirement, and it is banked early because it depends on a clock nothing can rewind.

## Beat 3 — 0:45–1:10 · fan-out, then scale

**On screen:** the Cloud Run Job execution detail showing the 15-worker setting. Hard cut to the scale-run overview
frame — *"150 ingested · N analyzed · N abandoned · N unparseable"*.

**Say:** one sentence — same architecture, ten times the pile, measured.

**Property:** behaviour at 10× is measured, not asserted. Every count read from metrics.json.

## Beat 4 — 1:10–1:55 · the docket, and the divergence tour

**On screen:** the morning docket. Click one observation → the viewer lands on the cited line.
Then the **six outcomes on one screen**.

**Say:** *"Six different consequences. Zero hand-holding."*

**Property:** this is the autonomy claim. Not "it ran unattended" — six visibly different
consequences from one unattended run.

## Beat 5 — 1:55–2:15 · the injection catch

**On screen:** `s07`'s footnote payload, the `InjectionDetected` event, the anomaly item — and
then the observations for s07, present and normal.

**Say:** *"…and analysis proceeded, because a blocked file is a punished student."*

## Beat 6 — 2:15–2:40 · the hero beat: disagree with it

**On screen:** the instructor edits a drafted observation on `s09` — the one where the model
over-read an unanswered rhetorical question as engagement with counterarguments. The
supersession event appears; the original stays visible.

**Say:** one line on exemplars.

**Property:** this is the beat where Karani is *wrong* and the system handles it correctly. Do
not cut it to save time — a demo where the agent is never wrong is a demo nobody believes.

## Beat 7 — 2:40–2:55 · the denial

**Film the CREATE, not a `.set()`.** This is the single most important note in the run-book.

An external review found that the original beat would have demonstrated the wrong operation.
The pipeline role grants `datastore.entities.create`; a `.set()` on an existing document ID is
an upsert that can be denied for wanting *update* permission — so it would show
`PERMISSION_DENIED` on camera while the operation the role actually authorises still worked.
A denial that proves nothing is worse than no denial, because it is believed.

**On screen, live console, not a screenshot:**

```bash
gcloud config set account karani-analysis@<project>.iam.gserviceaccount.com

# The operation datastore.entities.create authorises: a FRESH document in the grades database.
python - <<'PY'
from google.cloud import firestore
db = firestore.Client(project="<project>", database="karani-grades")
db.collection("grades").document("probe-live-demo").create({"grade": "A"})
PY
# expect: PERMISSION_DENIED
```

**Say:** *"That's not a policy. That's IAM — and grades aren't even in the same database."*

**Precondition:** `pytest -m deployed` must pass first. It runs this exact attack plus a
create in a collection nobody has named, because the boundary is the database binding rather
than a collection's spelling.

**Property:** the boundary is enforced, not asserted. Until the deployed tests pass, the
language discipline holds: say *"no field can carry a verdict into any downstream system"* —
never "structurally impossible".

## Beat 8 — 2:55–3:15 · ratify, and it lands where they already work

**On screen:** ratification → sheets appear in the Drive folder, the CSV exports,
`ArtifactDelivered` in the log. Show the CSV's grade column **empty**, and say why.

## Beat 9 — 3:15–3:45 · close

**On screen:** the appeal packet, then the architecture diagram.

**Say:** defensibility in exactly one sentence. Then the thesis line again.

---

## Runtime cut ladder, in order

1. Beat 3's scale frame trimmed to 5s — **never cut entirely**
2. Beat 6's exemplar line
3. Beat 9's appeal-packet visual (keep the sentence)
4. Beat 8 compressed to the Drive folder only
5. Beat 5 compressed to the event + queue item

**Never cut:** the divergence tour · the denial · the live trigger · the lower third · the
thesis lines.

## Standing rules on camera

- No real student data. Every name on screen is `s01`…`s16`.
- Do not say "structurally impossible" until beat 7 passes on the deployed path.
- Do not call the validator an "auditor" unless entailment shipped at 100%.
- Do not call the Gemma tier "local" unless it is literally local.
- Every number spoken exists in metrics.json first. If it isn't measured, don't say it.
