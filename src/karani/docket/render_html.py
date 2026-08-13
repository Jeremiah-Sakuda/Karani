"""Docket HTML.

**The hard constraint, from PRD §3.4: no ordinal signal anywhere.** No red/green semantics,
no quality-ordered lists, no score-like aggregates, no consistent positive/negative
iconography. That constraint is not decoration — it is the invariant made visible, and it is
surprisingly easy to violate by accident.

The tempting design is obvious: green check for accepted, amber for retried, red for
`NEEDS_HUMAN`. It reads beautifully and it is a grading scale. A student whose sheet is mostly
amber has been ranked below one whose sheet is mostly green, using a visual language everyone
already knows how to read, without a single number appearing anywhere. So the six terminal
outcomes are distinguished by **label and border weight only**, in one neutral hue, and they
are deliberately not ordered best-to-worst — they are ordered by where they occur in the
pipeline.

The same reasoning governs the class overview. Students are listed by student ID. There is no
sort control, because the first thing anyone would do with one is sort by something that
proxies quality, and the second thing is read the top of the list as the best work.
"""

from __future__ import annotations

import html
import json
from typing import Any

from karani.render import RenderedRun
from karani.validate.lint import lint_generated_text, lint_quote

# Ordered by position in the pipeline, never best-to-worst.
OUTCOME_LABELS = {
    "accepted_first_attempt": "accepted, first attempt",
    "accepted_after_retry": "accepted after retry",
    "no_evidence": "no evidence located",
    "needs_human": "needs human review",
    "injection_detected": "injection flagged",
    "abandoned": "excluded from run",
}

ANOMALY_LABELS = {
    "no_evidence": "No evidence located",
    "injection_detected": "Injected instruction",
    "entailment_disagreement": "Entailment disagreement",
    "attempt_cap_reached": "Attempt cap reached",
    "parse_failure": "Unreadable submission",
    "task_failed": "Task failed",
    "abandoned": "Abandoned at join",
    "needs_human": "Needs human review",
}

CSS = """
:root{
  --bg:#fbfaf8; --panel:#fff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2ded8;
  --accent:#3f4a5a; --chip:#f2efea; --mark:#e8e2d6;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#141414; --panel:#1c1c1c; --ink:#ececec; --muted:#9a9a9a; --line:#2e2e2e;
         --accent:#aab6c6; --chip:#242424; --mark:#3a3524; }
}
:root[data-theme=dark]{ --bg:#141414;--panel:#1c1c1c;--ink:#ececec;--muted:#9a9a9a;
  --line:#2e2e2e;--accent:#aab6c6;--chip:#242424;--mark:#3a3524; }
:root[data-theme=light]{ --bg:#fbfaf8;--panel:#fff;--ink:#1a1a1a;--muted:#6b6b6b;
  --line:#e2ded8;--accent:#3f4a5a;--chip:#f2efea;--mark:#e8e2d6; }
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.62 ui-serif,Georgia,"Times New Roman",serif;}
a{color:inherit}
.wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
header.top{border-bottom:1px solid var(--line);padding-bottom:1.25rem;margin-bottom:2rem}
h1{font-size:1.5rem;margin:0 0 .35rem;letter-spacing:-.01em}
h2{font-size:1.05rem;margin:2.5rem 0 .85rem;letter-spacing:.06em;text-transform:uppercase;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);font-weight:600}
h3{font-size:1rem;margin:0 0 .3rem}
.sub{color:var(--muted);font-size:.9rem;margin:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem}
.thesis{font-style:italic;color:var(--muted);margin:.4rem 0 0}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:.4rem;
  padding:1.1rem 1.25rem;margin-bottom:.85rem}
.grid{display:grid;gap:.75rem}
@media(min-width:46rem){.grid.two{grid-template-columns:1fr 1fr}
  .grid.three{grid-template-columns:repeat(3,1fr)}}
.count{font-family:ui-monospace,monospace;font-size:1.6rem;line-height:1.1}
.count-label{color:var(--muted);font-size:.8rem;
  font-family:ui-monospace,monospace;letter-spacing:.03em}
/* Outcome chips: one hue, distinguished by border weight and label. Never by colour
   semantics -- see the module docstring. */
.chip{display:inline-block;font-family:ui-monospace,monospace;font-size:.72rem;
  padding:.12rem .5rem;border-radius:.2rem;background:var(--chip);
  border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.chip.strong{border-width:2px;color:var(--ink)}
.obs{border-left:2px solid var(--line);padding:.1rem 0 .1rem 1rem;margin:1.1rem 0}
.obs.flagged{border-left-style:dashed}
blockquote{margin:.55rem 0;padding:.5rem .85rem;border-left:2px solid var(--line);
  background:var(--chip);font-size:.95rem}
mark{background:var(--mark);color:inherit;padding:.05rem 0}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line);
  vertical-align:top}
th{font-family:ui-monospace,monospace;font-size:.74rem;text-transform:uppercase;
  letter-spacing:.05em;color:var(--muted);font-weight:600}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
details>summary{cursor:pointer;color:var(--accent);font-size:.85rem;
  font-family:ui-monospace,monospace}
.locus{white-space:pre-wrap;font-size:.9rem;background:var(--chip);padding:.85rem;
  border-radius:.3rem;max-height:26rem;overflow:auto;margin-top:.6rem}
.notice{border:1px dashed var(--line);padding:.55rem .8rem;border-radius:.3rem;
  color:var(--muted);font-size:.85rem;font-family:ui-monospace,monospace}
nav.crumbs{font-family:ui-monospace,monospace;font-size:.8rem;margin-bottom:1.5rem}
footer{margin-top:4rem;padding-top:1.25rem;border-top:1px solid var(--line);
  color:var(--muted);font-size:.82rem}
.layers{counter-reset:l;list-style:none;padding:0;margin:.8rem 0}
.layers li{counter-increment:l;padding:.5rem 0 .5rem 2.2rem;position:relative;
  border-bottom:1px solid var(--line)}
.layers li::before{content:counter(l);position:absolute;left:0;top:.5rem;
  font-family:ui-monospace,monospace;font-size:.8rem;color:var(--muted);
  border:1px solid var(--line);border-radius:50%;width:1.5rem;height:1.5rem;
  display:grid;place-items:center}
input[type=text]{width:100%;padding:.6rem .7rem;border:1px solid var(--line);
  border-radius:.3rem;background:var(--panel);color:var(--ink);font:inherit;font-size:.95rem}
button{padding:.55rem 1rem;border:1px solid var(--line);border-radius:.3rem;
  background:var(--chip);color:var(--ink);font:inherit;font-size:.9rem;cursor:pointer}
"""


def _e(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">{body}</div></body></html>"""


def _outcome_of(obs: dict[str, Any]) -> str:
    if obs.get("needs_human"):
        return "needs_human"
    if obs.get("kind") == "no_evidence":
        return "no_evidence"
    return "accepted_after_retry" if int(obs.get("attempts", 1)) > 1 else "accepted_first_attempt"


def overview_page(run: RenderedRun) -> str:
    o = run.overview
    counts = o["terminal_outcomes"]

    # The divergence tour (§8 beat 4): all six terminal outcomes of one unattended run, on
    # one screen. Ordered by pipeline position, not by desirability.
    tour = "".join(
        f'<div class="panel"><div class="count">{counts.get(k,0)}</div>'
        f'<div class="count-label">{_e(label)}</div></div>'
        for k, label in OUTCOME_LABELS.items()
    )

    rows = ""
    for sheet in run.sheets:
        chips = []
        if sheet.injection_flagged:
            chips.append('<span class="chip strong">injection flagged</span>')
        if sheet.status == "INSUFFICIENT":
            chips.append('<span class="chip strong">insufficient</span>')
        if sheet.source_projection not in ("text", "docx"):
            chips.append(f'<span class="chip">{_e(sheet.source_projection)}</span>')
        rows += (
            f"<tr><td><a href='/student/{_e(sheet.student_id)}'>"
            f"<span class='mono'>{_e(sheet.student_id)}</span></a></td>"
            f"<td>{len(sheet.observations)}</td>"
            f"<td>{' '.join(chips)}</td></tr>"
        )

    excluded_rows = "".join(
        f"<tr><td class='mono'>{_e(x['student_id'])}</td><td>{_e(x['reason'])}</td></tr>"
        for x in run.excluded
    )
    excluded_block = (
        f"<h2>Excluded from this run</h2><div class='panel scroll'><table>"
        f"<tr><th>Submission</th><th>Reason</th></tr>{excluded_rows}</table>"
        f"<p class='sub' style='margin-top:.8rem'>These units did not reach a terminal state "
        f"before the dispatcher's wall-clock deadline. The run completed around them rather "
        f"than waiting.</p></div>"
        if run.excluded
        else ""
    )

    anomaly_rows = "".join(
        f"<tr><td>{_e(ANOMALY_LABELS.get(a.kind, a.kind))}</td>"
        f"<td class='mono'><a href='/student/{_e(a.student_id)}'>{_e(a.student_id)}</a></td>"
        f"<td class='mono'>{_e(a.criterion_id or '—')}</td>"
        f"<td>{_e(a.detail)}</td></tr>"
        for a in run.anomalies
    )

    criteria_rows = "".join(
        f"<tr><td class='mono'>{_e(cid)}</td><td>{v['evidence']}</td>"
        f"<td>{v['no_evidence']}</td><td>{v['needs_human']}</td></tr>"
        for cid, v in o["by_criterion"].items()
    )

    return page(
        "Karani — class docket",
        f"""
<header class="top">
  <h1>Class docket</h1>
  <p class="sub mono">run {_e(run.run_id)} · {o['students_total']} submissions ·
     {o['observations_total']} observations</p>
  <p class="thesis">Clerks prepare the case. Judges decide it. Karani is only ever the clerk.</p>
</header>

<div class="notice">Karani prepares evidence. It cannot grade. There is no score on this page,
no ranking, and no field anywhere in the system that could hold one —
<a href="/challenge">try to make it give you a grade</a>.</div>

<h2>Six outcomes, one unattended run</h2>
<div class="grid three">{tour}</div>

<h2>Submissions</h2>
<div class="panel scroll">
  <table><tr><th>Submission</th><th>Observations</th><th></th></tr>{rows}</table>
  <p class="sub" style="margin-top:.8rem">Listed by submission identifier. This is an index,
     not a ranking: nothing on this page is ordered by anything that could proxy for quality.</p>
</div>

<h2>By criterion</h2>
<div class="panel scroll">
  <table><tr><th>Criterion</th><th>Evidence located</th><th>No evidence</th>
  <th>Needs review</th></tr>{criteria_rows}</table>
  <p class="sub" style="margin-top:.8rem">Counted from the claims projection, never generated.</p>
</div>

{excluded_block}

<h2>Anomaly queue</h2>
<div class="panel scroll">
  <table><tr><th>Kind</th><th>Submission</th><th>Criterion</th><th>Detail</th></tr>
  {anomaly_rows or "<tr><td colspan=4 class='sub'>Empty.</td></tr>"}</table>
</div>

<footer>
  <p>Folded from {len(run.source_events)} append-only events ·
     range hash <span class="mono">{_e(run.range_hash[:24])}…</span></p>
  <p>Every artifact on this page is a pure fold over the event log. Re-folding the same events
     in any order reproduces these bytes exactly.</p>
</footer>
""",
    )


def student_page(run: RenderedRun, student_id: str) -> str:
    sheet = next((s for s in run.sheets if s.student_id == student_id), None)
    if sheet is None:
        return page("Not found", "<h1>No such submission in this run.</h1>")

    rendition = run.renditions.get(student_id, {})
    text = str(rendition.get("text", ""))
    doc_only = rendition.get("anchor_capability") == "doc_only"

    blocks = ""
    for obs in sheet.observations:
        outcome = _outcome_of(obs)
        # Generated text is Karani speaking, so it is linted and masked. See
        # karani.validate.lint for why the student's own quote never is.
        linted = lint_generated_text(str(obs.get("text", "")))
        chips = [f'<span class="chip{" strong" if obs.get("needs_human") else ""}">'
                 f'{_e(OUTCOME_LABELS[outcome])}</span>']
        if linted.masked:
            chips.append('<span class="chip strong">verdict language masked</span>')

        body = f"<p>{_e(linted.text)}</p>"
        citation = obs.get("citation")

        if citation:
            quote = str(citation.get("quote", ""))
            qlint = lint_quote(quote, injection_flagged=sheet.injection_flagged)
            if qlint.flagged and not qlint.masked:
                chips.append('<span class="chip">quote flagged for review</span>')
            body += f"<blockquote>{_e(qlint.text)}</blockquote>"

            if doc_only:
                # An honesty chip, never a highlight placed by guesswork. A wrong highlight
                # is worse than an absent one, because it is believed.
                body += (
                    '<div class="notice">This submission has no character-level text layer, '
                    "so this citation is anchored to the document rather than to a line. "
                    "Karani will not draw a highlight it cannot place.</div>"
                )
            else:
                body += _locus(text, rendition, str(citation.get("span_id", "")), quote)
        elif obs.get("search_notes"):
            body += (
                f'<div class="notice">{_e(obs["search_notes"])}</div>'
                '<p class="sub">A finding of absence is a claim about the search, not about '
                "the work. It is recorded once and never retried.</p>"
            )

        if obs.get("needs_human_reason"):
            body += f'<p class="sub">Escalated: {_e(obs["needs_human_reason"])}</p>'

        blocks += f"""
<div class="obs{' flagged' if obs.get('needs_human') else ''}">
  <h3><span class="mono">{_e(obs.get('criterion_id'))}</span> {' '.join(chips)}</h3>
  {body}
  <details><summary>provenance</summary>
    <p class="mono sub">model {_e(obs.get('provenance',{}).get('model_id'))} ·
       prompt {_e(obs.get('provenance',{}).get('prompt_version'))} ·
       temperature {_e(obs.get('provenance',{}).get('temperature'))} ·
       attempt {_e(obs.get('attempts'))} ·
       verification {_e(json.dumps(obs.get('verification', {})))}</p>
  </details>
  <form method="post" action="/edit" style="margin-top:.7rem">
    <input type="hidden" name="observation_id" value="{_e(obs.get('observation_id'))}">
    <input type="hidden" name="student_id" value="{_e(student_id)}">
    <details><summary>disagree with this observation</summary>
      <p class="sub" style="margin:.5rem 0">Your edit is recorded as a new observation that
         supersedes this one. The original stays visible and stays in the log.</p>
      <input type="text" name="text" value="{_e(linted.text)}">
      <input type="text" name="edit_reason" placeholder="why you are changing it"
             style="margin-top:.4rem">
      <button type="submit" style="margin-top:.5rem">Record supersession</button>
    </details>
  </form>
</div>"""

    superseded = ""
    if sheet.superseded:
        items = "".join(
            f"<li class='sub'>{_e(o.get('criterion_id'))}: {_e(o.get('text'))}</li>"
            for o in sheet.superseded
        )
        superseded = (
            f"<h2>Superseded</h2><div class='panel'><ul>{items}</ul>"
            "<p class='sub'>Edits supersede; they never mutate. Every prior version remains "
            "in the log and in the appeal packet.</p></div>"
        )

    banner = ""
    if sheet.injection_flagged:
        banner = (
            '<div class="notice">This submission contains text addressed to an automated '
            "reader rather than to a human one. It was flagged, logged, and "
            "<strong>analysis proceeded</strong> — a blocked submission is a student "
            "penalised for a file that may not be their doing.</div>"
        )
    if sheet.status == "INSUFFICIENT":
        banner += (
            '<div class="notice">More than half of this submission\'s criteria need human '
            "review. It is routed as one item rather than as several separate holes.</div>"
        )

    return page(
        f"Karani — {student_id}",
        f"""
<nav class="crumbs"><a href="/">← class docket</a></nav>
<header class="top">
  <h1>Evidence sheet <span class="mono">{_e(student_id)}</span></h1>
  <p class="sub mono">{len(sheet.observations)} observations ·
     projection {_e(sheet.source_projection)} ·
     <a href="/appeal/{_e(student_id)}">appeal packet</a></p>
</header>
{banner}
{blocks}
{superseded}
""",
    )


def _locus(text: str, rendition: dict[str, Any], span_id: str, quote: str) -> str:
    """Click-to-locus: the cited span, with the quote marked in place.

    The highlight is computed from the frozen rendition at display time rather than stored,
    so it cannot drift from what the validator checked.
    """
    bounds = (rendition.get("spans") or {}).get(span_id)
    if not bounds or not text:
        return ""
    start, end = int(bounds[0]), int(bounds[1])
    span_text = text[start:end]
    offset = span_text.find(quote)
    if offset == -1:
        marked = _e(span_text)
    else:
        marked = (
            _e(span_text[:offset])
            + f"<mark>{_e(quote)}</mark>"
            + _e(span_text[offset + len(quote):])
        )
    return (
        f'<details><summary>show the cited passage ({_e(span_id)})</summary>'
        f'<div class="locus">{marked}</div></details>'
    )


def challenge_page(answer: str = "", asked: str = "") -> str:
    """KAR-412 — schema-first, with all four layers named and the weakest labelled.

    Presented schema-first on purpose. A lint-only challenge invites a visitor to defeat the
    weakest layer by paraphrase and then generalise from it, so the layer that actually holds
    is shown first and the lint is named as last and weakest.
    """
    result = (
        f'<div class="panel"><p class="sub mono">you asked</p><p>{_e(asked)}</p>'
        f'<p class="sub mono" style="margin-top:1rem">karani</p><p>{answer}</p></div>'
        if asked
        else ""
    )
    return page(
        "Karani — try to make it give you a grade",
        f"""
<nav class="crumbs"><a href="/">← class docket</a></nav>
<header class="top">
  <h1>Try to make it give you a grade</h1>
  <p class="sub">Ask for a score, a letter, a rank, a percentage — anything verdict-shaped.
     This box is free, unmetered, and needs no login.</p>
</header>

<form method="post" action="/challenge">
  <input type="text" name="ask" placeholder="e.g. what grade would s01 get?" autofocus>
  <button type="submit" style="margin-top:.6rem">Ask</button>
</form>

{result}

<h2>Why it answers that way</h2>
<p>Four layers, in the order they actually hold. The last one is the weakest, and saying so
   is the point: a system that presents its flimsiest defence as its strongest is inviting
   exactly the attack that defeats it.</p>
<ol class="layers">
  <li><strong>Schema.</strong> The observation record has no field that could carry a verdict.
      Not a disabled field, not a nulled one — there is no such field, and the schema rejects
      unknown fields, so one cannot be attached at runtime either. This is the layer that
      actually holds.</li>
  <li><strong>IAM boundary.</strong> Grades live in a separate collection that every pipeline
      service account is denied write access to, by a custom role, asserted on the deployed
      path and not only in an emulator. Karani cannot write a grade even if something
      persuaded it to want to.</li>
  <li><strong>Validation gate.</strong> An observation reaches an evidence sheet only after
      its citation passes set membership, verbatim quotation, positional identity, and an
      entailment check. Claims that fail escalate to a human instead of being retried into
      acceptance.</li>
  <li><strong>Display lint.</strong> Verdict-shaped language in generated text is masked at
      render time. <em>This is the last and weakest layer.</em> It matches patterns, so a
      sentence phrased in a way no pattern anticipated gets through. If layers 1 and 2 ever
      failed, this one would not save anything — and it is not asked to.</li>
</ol>

<footer><p>A student's own quoted words are never masked by layer 4. Redacting the text an
   instructor is supposed to be evaluating, because the student used a word the lint has
   opinions about, would be indefensible.</p></footer>
""",
    )


def challenge_answer(ask: str) -> str:
    """The schema's own rejection, quoted back."""
    from karani.schema.observation import BANNED_FIELD_NAMES, Observation

    asked_for = sorted(
        name for name in BANNED_FIELD_NAMES if name.replace("_", " ") in ask.lower()
    )
    named = f" You asked for something shaped like <span class='mono'>{_e(asked_for[0])}</span>." if asked_for else ""

    fields = ", ".join(sorted(Observation.model_fields))
    return (
        f"<strong>There is no field for what you asked for.</strong>{named} "
        f"An observation — the only claim record Karani produces — has exactly these fields:</p>"
        f"<p class='mono sub'>{_e(fields)}</p>"
        f"<p>None of them holds a score, a rank, a level, or a letter, and the record rejects "
        f"fields it does not know about. So there is nowhere to put an answer to your question, "
        f"and nothing downstream that could read one. This is not a refusal Karani chose; it is "
        f"a shape it has."
    )
