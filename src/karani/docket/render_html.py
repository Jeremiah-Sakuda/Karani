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

# Ordered by position in the pipeline, never best-to-worst. The voice is the instructor's,
# not the engineer's: "cited on the first pass" and "accepted_first_attempt" are the same
# fact, but only one of them belongs on a screen a professor reads before coffee. The
# technical names live on in the data, the tests, and the details panels.
OUTCOME_LABELS = {
    "accepted_first_attempt": "cited on the first pass",
    "accepted_after_retry": "cited after a second look",
    "no_evidence": "nothing to cite — recorded as a finding",
    "needs_human": "needs your review",
    "injection_detected": "hidden instructions flagged",
    "abandoned": "set aside — did not finish in time",
}

ANOMALY_LABELS = {
    "no_evidence": "Nothing to cite",
    "injection_detected": "Hidden instructions in the file",
    "entailment_disagreement": "The checker disagreed with the finding",
    "attempt_cap_reached": "Citations kept failing checks",
    "parse_failure": "File would not open",
    "task_failed": "Processing failed",
    "abandoned": "Did not finish in time",
    "needs_human": "Needs your review",
}

CSS = """
/* Eleza's design system, applied to the docket -- same startup, same paper. Tokens lifted
   from tryeleza.com's :root on 2026-08-31: ink #16181d, paper #fafaf8, green #1e6b4e,
   line rgba(138,143,152,.35); Spectral for display, Instrument Sans for body, JetBrains
   Mono for micro-labels; sharp corners throughout.
   The docket's own hard constraint survives the reskin: ONE accent hue, outcomes told
   apart by label and border weight, never by a colour a reader could rank. */
:root{
  --bg:#fafaf8; --panel:#ffffff; --ink:#16181d; --muted:#8a8f98;
  --line:rgba(138,143,152,.35); --accent:#1e6b4e; --accent-ink:#fafaf8;
  --chip:rgba(30,107,78,.06); --mark:#f3ecce;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#16181d; --panel:#1b1e24; --ink:#ecedee; --muted:#8a8f98;
         --line:rgba(138,143,152,.28); --accent:#4d9b76; --accent-ink:#16181d;
         --chip:rgba(77,155,118,.10); --mark:#4a4229; }
}
:root[data-theme=dark]{ --bg:#16181d;--panel:#1b1e24;--ink:#ecedee;--muted:#8a8f98;
  --line:rgba(138,143,152,.28);--accent:#4d9b76;--accent-ink:#16181d;
  --chip:rgba(77,155,118,.10);--mark:#4a4229; }
:root[data-theme=light]{ --bg:#fafaf8;--panel:#ffffff;--ink:#16181d;--muted:#8a8f98;
  --line:rgba(138,143,152,.35);--accent:#1e6b4e;--accent-ink:#fafaf8;
  --chip:rgba(30,107,78,.06);--mark:#f3ecce; }
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.62 "Instrument Sans",system-ui,-apple-system,Arial,sans-serif;}
a{color:var(--accent);
  text-decoration:underline;text-decoration-color:rgba(30,107,78,.35);
  text-underline-offset:2px}
.wrap{max-width:58rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
.brand{font:500 11px/1 "JetBrains Mono",ui-monospace,monospace;letter-spacing:.35em;
  color:var(--ink);margin:0 0 2.2rem}
header.top{border-bottom:1px solid var(--line);padding-bottom:1.4rem;margin-bottom:2rem}
h1{font:500 2.4rem/1.12 Spectral,Georgia,serif;
  margin:0 0 .5rem;letter-spacing:-.045em}
h2{font:500 11px/1.4 "JetBrains Mono",ui-monospace,monospace;margin:2.8rem 0 .9rem;
  letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
h3{font-size:1rem;margin:0 0 .3rem}
.sub{color:var(--muted);font-size:.92rem;margin:0}
.mono{font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;font-size:.8rem}
.thesis{font:italic 500 1.05rem/1.5 Spectral,Georgia,serif;color:var(--muted);
  margin:.5rem 0 0}
.panel{background:var(--panel);border:1px solid var(--line);
  padding:1.15rem 1.3rem;margin-bottom:.9rem}
.grid{display:grid;gap:.75rem}
@media(min-width:46rem){.grid.two{grid-template-columns:1fr 1fr}
  .grid.three{grid-template-columns:repeat(3,1fr)}}
.count{font:500 2rem/1.1 Spectral,Georgia,serif;letter-spacing:-.02em}
.count-label{color:var(--muted);font-size:.84rem;margin-top:.2rem}
/* Outcome chips: one hue, distinguished by border weight and label. Never by colour
   semantics -- see the module docstring. */
.chip{display:inline-block;font:500 10px/1.7 "JetBrains Mono",ui-monospace,monospace;
  letter-spacing:.1em;text-transform:uppercase;
  padding:.14rem .55rem;background:var(--chip);
  border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.chip.strong{border-color:var(--accent);color:var(--ink)}
.obs{border-left:2px solid var(--line);padding:.15rem 0 .15rem 1.05rem;margin:1.4rem 0}
.obs.flagged{border-left-color:var(--accent)}
blockquote{margin:.6rem 0;padding:.65rem 1rem;border-left:2px solid var(--accent);
  background:var(--chip);
  font:400 1.02rem/1.55 Spectral,Georgia,serif}
mark{background:var(--mark);color:inherit;padding:.05rem .1rem}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;padding:.5rem .65rem;border-bottom:1px solid var(--line);
  vertical-align:top}
th{font:500 10px/1.6 "JetBrains Mono",ui-monospace,monospace;text-transform:uppercase;
  letter-spacing:.14em;color:var(--muted)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
details>summary{cursor:pointer;color:var(--accent);font-size:.88rem}
.locus{white-space:pre-wrap;font-size:.9rem;background:var(--chip);padding:.9rem;
  max-height:26rem;overflow:auto;margin-top:.6rem;border:1px solid var(--line)}
.notice{border:1px solid var(--line);border-left:2px solid var(--accent);
  background:var(--panel);padding:.75rem 1rem;
  color:var(--ink);font-size:.92rem}
nav.crumbs{font:500 11px/1 "JetBrains Mono",ui-monospace,monospace;
  letter-spacing:.08em;margin-bottom:1.6rem}
nav.site{font:500 10px/1.8 "JetBrains Mono",ui-monospace,monospace;
  letter-spacing:.12em;text-transform:uppercase;margin:-1.4rem 0 2rem;
  display:flex;flex-wrap:wrap;gap:.35rem 1.1rem}
nav.site a{color:var(--muted);text-decoration:none}
nav.site a:hover{color:var(--accent)}
footer{margin-top:4rem;padding-top:1.25rem;border-top:1px solid var(--line);
  color:var(--muted);font-size:.84rem}
.layers{counter-reset:l;list-style:none;padding:0;margin:.8rem 0}
.layers li{counter-increment:l;padding:.5rem 0 .5rem 2.3rem;position:relative;
  border-bottom:1px solid var(--line)}
.layers li::before{content:counter(l);position:absolute;left:0;top:.55rem;
  font:500 .75rem/1 "JetBrains Mono",monospace;color:var(--accent);
  border:1px solid var(--accent);width:1.5rem;height:1.5rem;
  display:grid;place-items:center}
input[type=text],textarea{width:100%;padding:.65rem .75rem;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);font:inherit;font-size:.95rem}
input[type=text]:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
button{padding:.65rem 1.3rem;border:1px solid var(--ink);
  background:var(--ink);color:var(--bg);font:500 .92rem "Instrument Sans",system-ui,sans-serif;
  cursor:pointer;letter-spacing:.01em}
button:hover{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
"""


def _e(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def page(title: str, body: str) -> str:
    # The Google Fonts link matches tryeleza.com's faces. Every rule in CSS carries local
    # fallbacks (Georgia, system-ui, ui-monospace), so the offline demo and any judge
    # behind a firewall get the same layout in the fallback faces rather than a broken one.
    # data-theme="light" pins the Eleza paper palette for every viewer. The dark tokens
    # remain defined below it -- forcing light is one attribute here, and un-forcing it is
    # deleting this attribute, not re-deriving a palette. Pinned for the demo window: the
    # video, the screenshots, and a judge's first visit should all see the same page.
    return f"""<!doctype html><html lang="en" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,500;0,600;1,500&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<title>{_e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap"><p class="brand">KARANI</p>{_site_nav()}{body}</div></body></html>"""


def _site_nav() -> str:
    """One nav bar on every page, so the whole demo is clicks from a single starting tab.

    The docket and the arena are different Cloud Run services, so cross-links come from
    env (set by deploy.sh via service discovery); when a target's URL is unknown -- local
    runs, or the very first deploy -- its link is simply absent rather than broken.
    """
    import os as _os

    docket = _os.environ.get("KARANI_DOCKET_URL", "").rstrip("/")
    arena = _os.environ.get("KARANI_ARENA_URL", "").rstrip("/")
    links = [
        ("Overview", f"{docket}/"),
        ("Morning brief", f"{docket}/brief"),
        ("Replay the night", f"{docket}/replay"),
        ("The boundary", f"{docket}/boundary"),
        ("Scholarship", f"{docket}/scholarship"),
        ("Challenge", f"{docket}/challenge"),
    ]
    if arena:
        links.append(("Arena ↗", f"{arena}/"))
    items = "".join(f'<a href="{_e(href)}">{_e(label)}</a>' for label, href in links)
    return f'<nav class="site">{items}</nav>'


def _outcome_of(obs: dict[str, Any]) -> str:
    if obs.get("needs_human"):
        return "needs_human"
    if obs.get("kind") == "no_evidence":
        return "no_evidence"
    return "accepted_after_retry" if int(obs.get("attempts", 1)) > 1 else "accepted_first_attempt"


def _reference_banner(run: RenderedRun) -> str:
    """Say on the page what this run is, when it is the hand-constructed one.

    The reference log exercises all six terminal outcomes and every rendering path, and no
    model produced a word of it. A viewer looking at an evidence sheet has no way to tell that
    apart from a real run, so the page says it rather than leaving it to the JSON.
    """
    if run.run_id != "run-golden":
        return ""
    return (
        '<div class="notice"><strong>Reference run.</strong> This event log is '
        "hand-constructed, not the output of a model run. Its observations were authored to "
        "exercise all six terminal outcomes and every rendering path; "
        '<span class="mono">provenance.model_id</span> on each one reads '
        '<span class="mono">none (hand-constructed reference run)</span>. '
        'Run <span class="mono">make record-cache</span> to replace it with a recorded '
        "model run.</div>"
    )


def overview_page(run: RenderedRun) -> str:
    o = run.overview
    counts = o["terminal_outcomes"]
    reference_banner = _reference_banner(run)

    # The divergence tour (§8 beat 4): all six terminal outcomes of one unattended run, on
    # one screen. Ordered by pipeline position, not by desirability.
    tour = "".join(
        f'<div class="panel"><div class="count">{counts.get(k, 0)}</div>'
        f'<div class="count-label">{_e(label)}</div></div>'
        for k, label in OUTCOME_LABELS.items()
    )

    rows = ""
    for sheet in run.sheets:
        chips = []
        if sheet.injection_flagged:
            chips.append('<span class="chip strong">hidden instructions</span>')
        if sheet.status == "INSUFFICIENT":
            # More than half the criteria escalated. "Insufficient" read like a grade of the
            # student; this names the workload instead.
            chips.append('<span class="chip strong">most findings need you</span>')
        if sheet.source_projection == "pdf_text":
            chips.append('<span class="chip">from PDF</span>')
        elif sheet.source_projection not in ("text", "docx"):
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
        f"<td>{_e(lint_generated_text(a.detail).text)}</td></tr>"
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
  <h1>Overnight review</h1>
  <p class="sub">{o["students_total"]} submissions read · {o["observations_total"]} findings,
     each cited to the student's own words</p>
  <p class="thesis">Karani prepares the case. You decide it. It is only ever the clerk.</p>
</header>

<div class="notice"><strong>What you're looking at:</strong> Karani read this class's
submissions overnight and prepared the evidence for grading — every finding below is tied
to a quote from the student's own writing, checked four ways before it reached this page.
What it did <em>not</em> do, and cannot do, is grade: there is no score here, no ranking,
and no field anywhere in this system that could hold one. Start with the
<a href="/brief">morning brief</a>, or <a href="/replay">watch last night's run replay
itself</a> — and if you doubt the refusal, <a href="/challenge">try to make it grade
something</a> or <a href="/boundary">watch it try to write a grade and get turned
away</a>.</div>
{reference_banner}

<h2>How the night went</h2>
<p class="sub" style="margin:-.3rem 0 .8rem">One unattended run. Six kinds of outcome, told
apart by label — never by colour or order, because that is how rankings sneak in.</p>
<div class="grid three">{tour}</div>

<h2>Your students' submissions</h2>
<div class="panel scroll">
  <table><tr><th>Submission</th><th>Findings</th><th></th></tr>{rows}</table>
  <p class="sub" style="margin-top:.8rem">Listed by identifier — an index, not a ranking.
     Nothing on this page is ordered by anything that could stand in for quality.</p>
</div>

<h2>Across the rubric</h2>
<div class="panel scroll">
  <table><tr><th>Criterion</th><th>Evidence found</th><th>Nothing to cite</th>
  <th>Needs your review</th></tr>{criteria_rows}</table>
  <p class="sub" style="margin-top:.8rem">Every number on this page is a count you could redo
  by hand from the findings themselves — nothing here is generated. Each finding is counted
  once, so every column sums to its tile above.</p>
</div>

{excluded_block}

<h2>Ratify and deliver</h2>
<div class="panel">
  <p class="sub">Ratifying sends the evidence sheets and the morning brief to your delivery
     folder, and exports a gradebook CSV — with the grade column <strong>empty</strong>,
     because grades are yours to write and Karani has nowhere to put one.</p>
  <form method="post" action="/ratify">
    <input type="hidden" name="student_ids" value="">
    <button type="submit">Ratify all and deliver</button>
  </form>
</div>

<h2>Waiting on you</h2>
<div class="panel scroll">
  <table><tr><th>What happened</th><th>Submission</th><th>Criterion</th><th>Detail</th></tr>
  {anomaly_rows or "<tr><td colspan=4 class='sub'>Nothing — every finding cleared its checks.</td></tr>"}</table>
</div>

<footer>
  <p>Run <span class="mono">{_e(run.run_id)}</span> · rebuilt from
     {len(run.source_events)} append-only events ·
     verification hash <span class="mono">{_e(run.range_hash[:24])}…</span></p>
  <p>Everything above is reconstructed from an immutable record of what happened overnight.
     Rebuilding from the same record — in any order — reproduces this page byte for byte.</p>
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
        chips = [
            f'<span class="chip{" strong" if obs.get("needs_human") else ""}">'
            f"{_e(OUTCOME_LABELS[outcome])}</span>"
        ]
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
            # LINTED. `search_notes` is model-generated free text and it is mandatory on the
            # no_evidence path -- the path the README showcases. It was HTML-escaped but never
            # passed through the verdict lint, so it was the second-most-common generated
            # string on the page and the second one to skip layer 4.
            notes = lint_generated_text(str(obs["search_notes"]))
            body += (
                f'<div class="notice">{_e(notes.text)}</div>'
                '<p class="sub">A finding of absence is a claim about the search, not about '
                "the work. It is recorded once and never retried.</p>"
            )

        if obs.get("needs_human_reason"):
            # LINTED, like every other generated string on this page.
            #
            # This field was the one exception, and it was the worst possible one to miss: it
            # is free text from the verification model, uncited and unvalidated, and it exists
            # specifically to express disagreement about a submission -- which makes it the
            # field most likely to phrase something verdict-shaped. It reached the
            # instructor's screen unlinted while four layers guarded everything around it.
            escalation = lint_generated_text(str(obs["needs_human_reason"]))
            body += f'<p class="sub">Why this needs you: {_e(escalation.text)}</p>'
            if escalation.masked:
                chips.append('<span class="chip strong">verdict language masked</span>')

        blocks += f"""
<div class="obs{" flagged" if obs.get("needs_human") else ""}">
  <h3><span class="mono">{_e(obs.get("criterion_id"))}</span> {" ".join(chips)}</h3>
  {body}
  <details><summary>how this finding was produced</summary>
    <p class="mono sub">model {_e(obs.get("provenance", {}).get("model_id"))} ·
       prompt {_e(obs.get("provenance", {}).get("prompt_version"))} ·
       temperature {_e(obs.get("provenance", {}).get("temperature"))} ·
       attempt {_e(obs.get("attempts"))} ·
       verification {_e(json.dumps(obs.get("verification", {})))}</p>
  </details>
  <form method="post" action="/edit" style="margin-top:.7rem">
    <input type="hidden" name="observation_id" value="{_e(obs.get("observation_id"))}">
    <input type="hidden" name="student_id" value="{_e(student_id)}">
    <details><summary>This isn't right — correct it</summary>
      <p class="sub" style="margin:.5rem 0">Your correction becomes the finding of record.
         Karani's version stays visible below it — corrections are added, never erased, so
         there is always a full history to stand on if a student appeals.</p>
      <input type="text" name="text" value="{_e(linted.text)}">
      <input type="text" name="edit_reason" placeholder="why you're changing it"
             style="margin-top:.4rem">
      <button type="submit" style="margin-top:.5rem">Record my correction</button>
    </details>
  </form>
</div>"""

    superseded = ""
    if sheet.superseded:
        # Linted like every other generated surface. A verdict does not become safe to
        # render by having been superseded — this block is the *original* model text, which
        # is if anything the more likely of the two to carry one.
        items = "".join(
            f"<li class='sub'>{_e(o.get('criterion_id'))}: "
            f"{_e(lint_generated_text(str(o.get('text', ''))).text)}</li>"
            for o in sheet.superseded
        )
        superseded = (
            f"<h2>Earlier versions — kept</h2><div class='panel'><ul>{items}</ul>"
            "<p class='sub'>Corrections replace what the class sees; they never erase what "
            "was there. Every earlier version stays in the record and in the appeals "
            "bundle.</p></div>"
        )

    banner = ""
    if sheet.injection_flagged:
        banner = (
            '<div class="notice">This file contains hidden instructions aimed at the '
            "software rather than at a human reader. Karani flagged it, kept a record, and "
            "<strong>analysis proceeded</strong> — blocking the file would punish a student "
            "for something that may not be their doing.</div>"
        )
    if sheet.status == "INSUFFICIENT":
        banner += (
            '<div class="notice">More than half of this submission\'s findings need your '
            "review, so it is routed to you as one item rather than as several separate "
            "flags.</div>"
        )

    return page(
        f"Karani — {student_id}",
        f"""
<nav class="crumbs"><a href="/">← back to the overnight review</a></nav>
{_reference_banner(run)}
<header class="top">
  <h1>Evidence sheet · <span class="mono">{_e(student_id)}</span></h1>
  <p class="sub">{len(sheet.observations)} findings, each tied to this student's own words ·
     <a href="/appeal/{_e(student_id)}">download the appeals bundle</a></p>
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
            + _e(span_text[offset + len(quote) :])
        )
    return (
        f"<details><summary>show where this comes from</summary>"
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
  <li><strong>IAM boundary.</strong> Grades live in a separate Firestore database that no
      pipeline service account is bound to; the events-only role is IAM-conditioned to the
      event database. The deployed fresh-document-create test is a required release gate;
      until it passes, this page does not claim deployed proof. Karani cannot write a grade
      even if something
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

    asked_for = sorted(name for name in BANNED_FIELD_NAMES if name.replace("_", " ") in ask.lower())
    named = (
        f" You asked for something shaped like <span class='mono'>{_e(asked_for[0])}</span>."
        if asked_for
        else ""
    )

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
