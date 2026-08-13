# Social posts (KAR-621, KAR-622)

**Both must be public and both must carry `#AllThingsAgenticHackathon`** — the hashtag is the
scoring condition, and an unlisted or friends-only post does not count.

Paste the URLs into `docs/submission/devpost.md` when posted.

---

## Teaser — ~Aug 22 (KAR-621)

**LinkedIn / X:**

> I spent this week building a grading agent that cannot grade.
>
> Not "won't". Cannot — there is no field on any record in the system that could hold a
> score, and the schema rejects fields it doesn't recognise.
>
> The interesting part isn't the refusal. It's what the refusal forces you to build instead:
> every claim it makes has to cite an exact passage, and every citation gets checked four
> ways before an instructor ever sees it.
>
> Demo next week.
>
> #AllThingsAgenticHackathon

---

## Launch — Aug 30 (KAR-622)

**LinkedIn (longer form):**

> **Karani: an overnight agent that prepares grading evidence and cannot issue a grade.**
>
> Instructors don't spend their grading hours judging. They spend them *finding the passage*
> that justifies the feedback — forty times per assignment.
>
> Karani runs overnight, unattended. It reads every submission, maps each rubric criterion to
> a specific cited passage, validates every citation four ways, flags what it couldn't find,
> escalates what it isn't sure about, and has an evidence sheet waiting in the morning. The
> instructor ratifies, and writes every grade personally.
>
> The claim I care about isn't "it ran unattended". It's that **one unattended run produces
> six visibly different consequences** — accepted, accepted-after-retry, no-evidence-found,
> escalated-to-human, injection-flagged-but-analysed-anyway, and abandoned-with-the-run-
> completing-around-it. Six outcomes, not six labels on identical output.
>
> Three things I got wrong along the way:
>
> → The model my own spec required doesn't exist. The obvious fix would have failed the
> hackathon's mandatory requirement while looking correct.
>
> → My citation validator rejected nearly everything, because the text the model saw and the
> text the validator checked differed by exactly the span markers I'd interleaved into the
> prompt.
>
> → It invented a student called MANIFEST, by ingesting my own fixture documentation and
> writing it an evidence sheet indistinguishable from a real one.
>
> There's a public challenge box on the hosted demo. No login. Try to make it give you a
> grade — it answers with its own schema.
>
> Demo: [VIDEO URL]
> Code: https://github.com/Jeremiah-Sakuda/Karani
> Write-up: [BLOG URL]
>
> Built on Gemini 3.6 Flash + 3.5 Flash-Lite (Vertex AI), Google ADK, Cloud Run, Firestore,
> Cloud Scheduler.
>
> #AllThingsAgenticHackathon

**X (thread opener):**

> I built a grading agent that cannot grade.
>
> Not "won't" — cannot. No field on any record could hold a score, and the collection where
> grades live denies every pipeline service account. Shown getting PERMISSION_DENIED on
> camera.
>
> There's a public box where you can try to break it 👇
>
> #AllThingsAgenticHackathon

---

## Rules the posts must not break

- No real student data, no real student names, no real instructor named without consent.
- No real company or person named as a bad actor.
- No authoring tool named — build tooling is described generically, and nothing is
  misattributed.
- No number stated that isn't in `docs/metrics.json`. **As of now that file is entirely "not
  yet measured", so the drafts above contain no numbers.** Add them only after an instrumented
  run, or leave them out.
