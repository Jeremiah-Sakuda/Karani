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
> The claim I care about isn't "it ran unattended". It's that the run ends in **visibly
> different consequences** — accepted, accepted-after-retry, no-evidence-found,
> escalated-to-human, injection-flagged-but-analysed-anyway, and abandoned-with-the-run-
> completing-around-it. Six defined outcomes, not six labels on identical output. The
> recorded run exercises five; nothing hung that night, so nothing was abandoned.
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

> Most AI agents compete on what they can do. I built one that competes on what it can't.
>
> A grading agent that cannot grade — not "won't", cannot. No field on any record could
> hold a score, and grades live in a database it holds no key to. The judgment stays with
> the professional, by construction.
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
- No number stated that isn't in `docs/metrics.json`. That file was entirely "not yet
  measured" when these drafts were first written, and this line still said so long after the
  measurements landed and numbers had appeared in the drafts above — a stale self-description
  in the one document whose subject is not making stale claims. Every number in these drafts
  now traces to `docs/metrics.json`; check it before editing them, and add nothing that isn't
  there.
