# Blog draft (KAR-620)

**Required language — must appear, verbatim, and must not be edited out:**

> *I created this piece of content for the purposes of entering the All Things Agentic
> Hackathon.*

Publish **publicly**, not unlisted. Then paste the URL into `docs/submission/devpost.md`.

---

## The grading agent that cannot grade, and the four bugs that taught me why that's hard

*I created this piece of content for the purposes of entering the All Things Agentic
Hackathon.*

Most AI agents are pitched on what they can do. This one is built around what it
deliberately leaves out.

I built an agent that reads student essays and prepares everything an instructor needs to
grade them — and cannot grade them itself. The judgment is the professional's work, and I
kept it that way on purpose, in the architecture, where a product update can't quietly take
it back.

Not "declines to". Cannot. There is no field on any record in the system that could hold a
grade, the schema rejects fields it doesn't recognise, and grades live in a **separate
Firestore database** that every pipeline service account is denied write access to.

A separate *collection*, which is what I built first, would not have done it: Firestore IAM
does not grant below the database, so a role scoped to "the events collection" is really a
role over everything beside it. A reviewer caught that. It is the single most useful piece
of feedback I got, and the fix — a second named database, with the binding conditioned on
the resource path — is the only part of this system where the security boundary is enforced
by the platform rather than by my code being correct.

That was the easy part. Here is what actually went wrong.

---

### 1. The model my own spec required does not exist

My design document pinned `gemini-3.5-pro` for the analysis tier. Reasonable-sounding. It
does not exist. The Gemini 3.5 family ships as Flash and Flash-Lite; the newest Pro-tier model
is `gemini-3.1-pro-preview`.

The intuitive repair is the trap. "Pro was specified, use the Pro that exists" pins a **3.1**
model — and the hackathon's mandatory requirement is *Gemini 3.5 or newer*. Capability tier
satisfied. Version bar failed. Only one of those was being graded pass/fail, and the failure
would have surfaced at the first live API call, which on my calendar was after the
architecture was frozen.

I pinned `gemini-3.6-flash` instead — newer, cheaper, and carrying the 1M context window my
no-vector-database argument depends on. Then I wrote a preflight that resolves every pinned
model ID against the live catalogue and fails loudly.

**A pinned model ID is a claim about the world. Check it like one.**

---

### 2. The validation layer that rejected everything, for a reason that took an hour to see

Every citation my agent produces carries the text immediately before and after the quote. That
sounds like metadata. It's the mechanism.

Consider: a quote genuinely lifted from paragraph 12, attributed to paragraph 47, where the
same phrase occurs in **both**. Is the span real? Yes. Does the quote occur in it? Yes. A
validator built from "does this span exist" and "does this text appear in it" — which is what
"check the citation" usually means — accepts that citation and points an instructor at the
wrong paragraph, in a document where one concedes a point and the other reverses it.

What separates them is context. So the citation carries it, and the validator recomputes it.

Then the first end-to-end run rejected almost everything.

The analyst sees the essay with span markers interleaved: `[[sp-0011]] <paragraph>`. The
validator computed context from the frozen rendition, which has **no markers**. For a quote in
the middle of a paragraph, both agree. For a quote near the *start* of one, the characters the
model saw include the marker and the tail of the previous paragraph — and the ones the
validator computed do not.

Every such citation was rejected as a misattribution. The retry produced the identical
mismatch. In production this would have appeared as an unexplained escalation rate
concentrated on **first sentences** — the sentences most likely to contain a thesis, which is
the criterion an instructor most wants evidence for.

**When a model reports something that will be checked, the thing it sees and the thing the
checker sees must be the same artifact.** Interleaving anything into a prompt silently makes
them different.

---

### 3. Fifteen independent writers produced one writer

I needed fifteen synthetic student essays that read like fifteen different people. My spec was
explicit: generate them in separate passes, never reconciled. I did exactly that — fifteen
independent generations, none able to see any other's output.

Then I handed all fifteen to a reviewer who knew nothing about how they were made.

- All fifteen took the same position on the prompt.
- Twelve of fifteen used the phrase "a 2024 municipal broadband study" **verbatim**.
- One aphorism appeared, restyled, in five.
- A twelve-word clause about a service appointment appeared verbatim in the two essays meant
  to be the most stylistically distant.
- Invented researcher surnames recombined from a pool of ten. The page number "41" anchored
  five different essays. The same fabricated author was male in one and female in another.

And the observation that actually mattered:

> *"Each weak essay carries exactly one engineered lesion. Real weak student writing fails on
> four axes at once and in ways nobody designed."*

Independent passes buy independence of **context**, not independence of **prior**. Fifteen
blind samples from one distribution land on the mode fifteen times. My variation instruction
pointed at style, so style is what varied; the argument underneath was never asked to move.

The fix was to allocate divergence rather than request it: assigned positions, disjoint
invented source pools with non-overlapping page ranges, an explicit ban list of every shared
phrase the reviewer found, distinct structural templates, and — for the weak papers —
instructions to fail several ways at once. A second blind review confirmed the fix and found a
third tier of collisions, which got repaired mechanically.

The residual homogeneity that remains is documented in the repository rather than hidden.
Nobody in my corpus makes a factual error or misreads a source without noticing. Real
composition classes produce both.

---

### 4. It invented a student called MANIFEST

Every markdown file in the submissions directory was a submission. So `MANIFEST.md` — my own
fixture documentation — was ingested, frozen into a rendition, given a span registry, analysed
against all five rubric criteria, and rendered into the class overview as a student.

Its evidence sheet was indistinguishable from a real one.

A real instructor's folder contains the assignment sheet, the rubric, a syllabus excerpt, and
whatever the LMS dropped in. Every one of them would have become a student, and the class
overview's counts would have been wrong while looking authoritative.

What caught it was a test asserting `len(dispatched) == 16` against a hand-counted
expectation. The more elegant assertion — "every dispatched unit reaches a terminal state" —
would have passed. MANIFEST reached one.

---

### The one I'd have shipped

The verdict lint masks grade-shaped language before it reaches the screen. An early version
flagged a student who wrote **"this policy is excellent."**

That student was evaluating a *policy*. Not their essay. The lint was about to put a review
chip on honest student prose for using an ordinary adjective about the thing they were
arguing about.

The lint is now split by speaker. Generated text — the system talking — gets masked. A
student's quoted words are **never** masked, only flagged, and only when the quality term
attaches to their own work rather than to their subject.

Its boundary is documented rather than discovered: paraphrase gets through. *"The writer has
done what the assignment asked, and done it well"* expresses a level of quality and matches no
pattern. The public challenge page says so, and there is a committed test asserting the known
misses are **still** missed — so widening the patterns without updating the published claim
fails CI.

That last part is the design principle underneath all four bugs. Four defensive layers, and
the honest thing is to name which one is weakest. The schema holds. The IAM boundary holds.
The lint is cosmetic, and a system that presents its flimsiest defence as its strongest is
inviting exactly the attack that defeats it.

---

**Code:** https://github.com/Jeremiah-Sakuda/Karani — `make demo` runs the whole pipeline with
zero credentials.

Built with Gemini 3.6 Flash and 3.5 Flash-Lite on Vertex AI, Google ADK, Cloud Run, Firestore,
and Cloud Scheduler.
