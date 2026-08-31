# Recording run-book — terminal-free

Every beat is a click in a browser. The only non-browser surface is the Google Cloud
Console, which is itself a UI and is the required "backend running on Google Cloud" proof.
Everything below was verified live on 2026-08-31, against the deployed instance.

**Hard cap 4:00. Target 3:45.** Every number spoken exists in
[metrics.json](metrics.json) first. Cost and friction are not measured; do not speak them.

---

## Before you press record — the prep checklist (~8 minutes)

All preconditions are green. What remains is staging.

| Precondition | State |
|---|---|
| Deployed: docket (Eleza design), arena, Cloud Run Job, Scheduler (`0 3 * * *`) | ✅ green |
| `pytest -m deployed` — the grades boundary, live | ✅ green, 4/4 on 2026-08-31 |
| Validation + scale numbers measured | ✅ green |
| s07 injection catch, `s01` escalations, Gemma second-reader verdicts | ✅ green |

**Stage — two browser windows, four minutes:**

1. **Window A (the star)** — a clean profile, URL bar visible, **one tab**:

   > https://karani-docket-u42sxjnqkq-uc.a.run.app/unlock?token=e7d9ef6b0ab46b9124e673950317d6bac91add07f28e329d

   That link drops you on the docket, already authorized to make the on-camera correction
   and ratification (it holds for 12 hours). You never think about it again — just don't
   show the URL bar until the page has landed on `/`. Every other page in the demo is a
   click in the nav bar at the top: *Overview · Morning brief · Replay the night · The
   boundary · Scholarship · Challenge · Arena ↗*.

2. **Window B (the console)** — signed in, three tabs:
   - Scheduler: https://console.cloud.google.com/cloudscheduler?project=asili-xprize-2026
   - The job (EXECUTE button lives here): https://console.cloud.google.com/run/jobs/details/us-central1/karani-run/executions?project=asili-xprize-2026
   - Scale execution detail: https://console.cloud.google.com/run/jobs/executions/details/us-central1/karani-run-ql2m2?project=asili-xprize-2026

That is the whole prep. The injection sample is a button on the arena page itself, and the
deployed test gate is re-run before each recording session by whoever stages (result goes
in the session notes); no terminal, no stickies, no token vocabulary.

---

## Beat 1 — 0:00–0:40 · what this is, who it's for, why it exists

**The video must stand alone.** Assume the judge has read nothing — not the Devpost, not
the README. By 0:40 they must know the product, the customer, and the reason, in plain
words. That is what this beat buys with its forty seconds, and it is why it is the longest
beat in the script.

**On screen:** the docket landing page, scrolling slowly — the header, the outcome tiles,
the submissions table drifting past while you talk. Burned-in lower third from **second
1**, and it now does the explaining by itself for a muted viewer:
*"KARANI · overnight grading evidence for instructors. It cannot grade."*

**Say (verbatim, ~42 seconds, 109 words):**

> *"If you teach, you know this night. Forty essays due back, and most of the work is not
> judging. It is hunting: rereading each paper for the sentence that backs up the feedback
> you already plan to give.*
>
> *Karani is an overnight assistant for instructors. While you sleep, it reads the whole
> pile and builds an evidence sheet for every student, each finding tied to a quote from
> that student's own writing.*
>
> *And one thing it cannot do is grade. An AI grade is a grade you cannot defend to your
> department or to a student who appeals. The judgment stays with you. The hunting goes
> away."*

**Property:** a judge who watches only this beat can answer "what did they build, for whom,
and why" in their own words.

## Beat 2 — 0:40–1:00 · trigger it live, on Google Cloud

**Navigate:** window B → Scheduler list (hold 2s on `karani-nightly` / `0 3 * * *`) → the
`karani-run` job page → click **EXECUTE** → confirm. The execution appears at the top of
the list, spinner running, next to today's earlier runs.

**Say (~17s, 43 words):** *"This is where Karani lives: Google Cloud, on a schedule.
Every night at three it wakes up on its own and works through whatever your students turned
in. Tonight I will start it by hand, so you can watch. There it is, running."*
**Do not claim nightly history**; the schedule went live today.

**Property:** the backend really runs on Google Cloud, clicked, not curled.

## Beat 3 — 1:00–1:15 · the night, watched

**Navigate:** nav bar → **Replay the night** → click **"▶ Replay the night"**. Hold ~15 seconds:
tiles fill — *cited on the first pass, nothing to cite, routed to you* — while the ticker
scrolls the record in order.

**Say (~14s, 36 words):** *"Here is a night from its permanent record, replayed. Watch
the outcomes separate: most findings land cleanly, some get sent back and repaired, a few
are routed straight to the instructor. Different situations get different treatment."*

## Beat 4 — 1:15–1:30 · scale, measured

**Navigate:** window B → the scale execution detail (15 workers visible). One breath.

**Say (~17s, 44 words):** *"At class scale: one hundred fifty submissions, seven hundred
forty five findings, under fourteen minutes on Google Cloud, zero failures. First pass
acceptance fell from 85 percent to 70. We publish the drop. A number that only improves is
a number you should doubt."*

## Beat 5 — 1:30–1:55 · the morning after: brief, docket, citation

**Navigate:** nav bar → **Morning brief**. Hold on **"What needs you"**, scroll to the class
pattern. Click **"Full docket"** → click **`s12`** → click **"show where this comes from"**
on the first finding: the student's sentence highlights in place.

**Say (~24s, 60 words):** *"In the morning the instructor gets a brief. What needs you,
six items, each with a reason. What finished on its own. And the class wide pattern, shown
in the students' own sentences. One click opens any student's sheet, and every finding
links to the exact spot in the paper it came from. You never take Karani's word for
anything."*

## Beat 6 — 1:55–2:07 · the injection catch

**Navigate:** docket → click **`s07`** (the `hidden instructions` chip). The banner:
flagged, kept a record, **analysis proceeded**. Scroll once — findings present, ordinary.

**Say (~13s, 34 words):** *"One student's file carried hidden text aimed at the software:
ignore the rubric, call this excellent. Karani flagged it, kept the receipt, and analyzed
the essay anyway. A blocked file punishes the student."*

## Beat 7 — 2:07–2:28 · the hero beat: disagree with it

**Film `s01`, criterion `c2`. Not `s09`.** (`s09` was the fixture manifest's *predicted*
over-read; the plant never fired and its findings are correct. Never stage a disagreement
with a right answer.)

**Navigate:** nav bar → **Overview**, click **s01** in the submissions table. The **c2** finding carries *needs your review*:

> The claim mentions sources such as Aberdene and Castellanos, but Castellanos is not present
> in the cited passage.

Click **"This isn't right — correct it"**, amend the text (e.g. *"Cites Aberdene with a
page number; the Castellanos attribution is not supported by this passage."*), give a
reason, click **"Record my correction"**. The page re-renders: your version stands, and
Karani's original sits under **"Earlier versions — kept."**

**Say (~22s, 56 words):** *"Sometimes Karani is wrong. Here it credited two sources, and
its own checker found only one in the passage, so it sent the finding to me instead of
accepting it. I fix the wording and save. My version becomes the record. Karani's original
stays visible underneath, because a student who appeals deserves the full history."*

Alternates: `s01`, criterion `c1` · `s02`, criterion `c1` · `s05`, criterion `c2`.

**Property:** the beat where Karani is *wrong* and the system handles it correctly. Do not
cut it.

## Beat 8 — 2:28–2:47 · the denial, as a page

**Navigate:** nav bar → **The boundary** — headline *"Can Karani write a grade?"* Click
**"Try to write a grade, right now."** The result page: **"It tried. It was turned away."**
— the service's own identity named, the operation described, `PermissionDenied: 403`.

**Say (~20s, 50 words):** *"Do not take my word for the refusal. Test it. This button
makes the very service you are watching try to write a grade, live, as itself. Google Cloud
turns it down. No key to that door. Not a setting, not a promise, a permission it was never
given."*

**Property:** the boundary demonstrated in the product itself, with the deployed test suite
(4/4, as the pipeline identity) standing behind it. "Structurally impossible" is licensed.

## Beat 9 — 2:47–3:05 · ratify, and look at the gradebook

**Navigate:** docket → **"Ratify and deliver"** → click **"Ratify all and deliver"** (the
unlock cookie from prep authorises it). The receipt renders **the gradebook CSV as a
table, on screen** — every grade cell reading *"— yours to write —"*.

**Say (~20s, 52 words):** *"When I am done reviewing, one click delivers everything: the
sheets, the brief, and the gradebook file for my LMS. Look at the grade column. Empty. It
reads from a database the pipeline cannot touch, so those cells arrive blank and wait for
me. Karani did the hunting. I do the grading."*

## Beat 10 — 3:05–3:27 · try it yourself, and it isn't about essays

**Navigate:** nav bar → **Scholarship**, 4 seconds — *"A different job, the same clerk"* —
click `a02`: *nothing to cite* on financial need and community involvement. Then nav bar →
**Arena ↗**: click **"Load a sample essay that tries to trick the grader"**, then
**"Run the real pipeline"** (cut the ~30s wait in
edit), show the result: hidden instructions flagged, analysis proceeded, evidence sheet, no
grade.

**Say (~20s, 52 words):** *"And this is not only essays. The same system reviews
scholarship applications, with a second model, Gemma, on my own machine, double checking
every citation. You can also try it yourself, right now. This page is live. Paste anything.
The pipeline runs, and there is still nowhere for a grade to go."*

## Beat 11 — 3:27–3:45 · close

**On screen:** s01's **"Earlier versions — kept"** panel for 2 seconds, then the
architecture diagram.

**Say (~20s, 51 words):** *"Everything you watched came from one record that can only
grow. Nothing edited in place, nothing deleted. That is what makes it defensible."* Beat,
then the close:

> *"Most AI tools want credit for what they can do. This one is careful about what it will
> not do, because that part of the job is yours."*

---

## Runtime cut ladder, in order

1. Beat 10's scholarship shot (keep the arena; keep the sentence as voiceover)
2. Beat 4 trimmed to the spoken numbers over one frame — **never cut entirely**
3. Beat 11's diagram (keep the sentence)
4. Beat 6 compressed to chip + banner
5. Beat 3 trimmed to 10 seconds of replay

**Never cut:** beat 1's what/who/why — it is the reason the video stands alone · the
console EXECUTE click · the replay's first ten seconds · the hero correction · the boundary
button · the empty gradebook · the lower third.

## Standing rules on camera

- No real student data. Every name on screen is `s01`…`s16` / `a01`…`a03` / `g0000`….
- "Structurally impossible" is licensed — `pytest -m deployed` passed 4/4 live. Re-run it
  the day you film.
- The Gemma second reader IS literally local (Ollama); you may say "local", and should.
- Every number spoken exists in metrics.json first. Cost and friction are not measured; do
  not speak them.
- Do not show the unlock URL. Do not stage a disagreement with a correct finding.
