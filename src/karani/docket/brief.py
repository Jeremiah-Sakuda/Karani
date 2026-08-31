"""The morning brief (KAR-418): the run's work-list, delivered, not visited.

The docket answers questions when an instructor comes to it. The brief is the difference
between a filing clerk and a chief of staff: after the unattended run, Karani says — without
being asked — *here is what needs you, here is what is done, and here is the pattern across
the class you would otherwise have found by hand on submission twelve.* It ships with the
ratified delivery to Drive and serves at `/brief`, so the morning's first click lands on a
work-list instead of a data set.

The reteach section is the part with real leverage and real risk, so its rule is strict:
**aggregates of counts, and quotations of students — never characterizations of them.** "12
of 15 submissions drew no evidence on counterarguments" is a count over the claims
projection. Attaching three cited examples lets the instructor see the pattern in the
students' own words. What it must never become is "the class is weak at counterarguments" —
that is a judgment, it belongs to the instructor, and no sentence here is allowed to reach
for it. Generated text passes the verdict lint like every other surface; student quotes are
never linted, because redacting the writing under review is indefensible.

Everything on this page is a pure function of the fold. No model is consulted to write the
brief — a briefing that re-asked a model to summarize the run would be a second system with
its own failure modes, unvalidated by the four (now five) layers everything else passed.
"""

from __future__ import annotations

from typing import Any

from karani.docket.render_html import _e, page
from karani.render import RenderedRun
from karani.validate.lint import lint_generated_text


def _needs_you(run: RenderedRun) -> list[dict[str, Any]]:
    items = []
    for sheet in run.sheets:
        for obs in sheet.observations:
            if obs.get("needs_human"):
                items.append(
                    {
                        "student_id": sheet.student_id,
                        "criterion_id": obs.get("criterion_id"),
                        "reason": str(obs.get("needs_human_reason") or ""),
                    }
                )
    for anomaly in run.anomalies:
        if anomaly.kind == "parse_failure":
            items.append(
                {
                    "student_id": anomaly.student_id,
                    "criterion_id": None,
                    "reason": "submission could not be parsed; no rendition exists. "
                    "The file needs a human eye before anything else can.",
                }
            )
    return items


def _reteach_patterns(run: RenderedRun, examples_per: int = 3) -> list[dict[str, Any]]:
    """Criteria where absence or escalation concentrates, with cited examples.

    A pattern is worth the instructor's attention when it is not one student's problem:
    the bar is at least two submissions, or a third of the class, whichever is larger.
    """
    total = max(run.overview["students_total"], 1)
    threshold = max(2, -(-total // 3))
    patterns = []
    for cid, counts in run.overview["by_criterion"].items():
        affected = counts["no_evidence"] + counts["needs_human"]
        if affected < threshold:
            continue
        examples = []
        for obs in run.claims:
            if str(obs.get("criterion_id")) != cid:
                continue
            if obs.get("kind") == "no_evidence" or obs.get("needs_human"):
                examples.append(
                    {
                        "student_id": obs.get("student_id"),
                        "kind": obs.get("kind"),
                        "quote": (obs.get("citation") or {}).get("quote"),
                        "note": str(obs.get("search_notes") or obs.get("needs_human_reason") or ""),
                    }
                )
            if len(examples) >= examples_per:
                break
        patterns.append(
            {"criterion_id": cid, "affected": affected, "total": total, "examples": examples}
        )
    return patterns


def brief_page(run: RenderedRun) -> str:
    needs = _needs_you(run)
    patterns = _reteach_patterns(run)
    outcomes = run.overview["terminal_outcomes"]

    needs_rows = (
        "".join(
            f"<tr><td class='mono'>{_e(item['student_id'])}</td>"
            f"<td class='mono'>{_e(item['criterion_id'] or '—')}</td>"
            f"<td>{_e(lint_generated_text(item['reason']).text)}</td></tr>"
            for item in needs
        )
        or "<tr><td colspan='3' class='sub'>Nothing. Every unit of work reached a terminal outcome without escalation.</td></tr>"
    )

    done_bits = (
        f"{outcomes['accepted_first_attempt']} accepted first attempt · "
        f"{outcomes['accepted_after_retry']} after a bounded retry · "
        f"{outcomes['no_evidence']} findings of absence · "
        f"{outcomes['injection_detected']} injection flagged (analysis proceeded) · "
        f"{outcomes['abandoned']} abandoned at the join"
    )

    pattern_blocks = ""
    for p in patterns:
        examples = ""
        for ex in p["examples"]:
            if ex["quote"]:
                examples += (
                    f"<blockquote class='sub'>“{_e(ex['quote'])}”"
                    f"<span class='mono'> — {_e(ex['student_id'])}</span></blockquote>"
                )
            else:
                examples += (
                    f"<p class='sub mono'>{_e(ex['student_id'])}: "
                    f"{_e(lint_generated_text(ex['note']).text)}</p>"
                )
        pattern_blocks += f"""
  <div class="panel">
    <p><span class="mono">{_e(p["criterion_id"])}</span> — <strong>{p["affected"]} of
    {p["total"]}</strong> submissions drew no evidence or were escalated on this criterion.
    A count over the claims projection, not an assessment of anyone.</p>
    {examples}
  </div>"""
    if not pattern_blocks:
        pattern_blocks = (
            "<div class='panel'><p class='sub'>No criterion crossed the pattern threshold "
            "(a third of the class, minimum two). Class-level reteaching signals live here "
            "when they exist; today there are none.</p></div>"
        )

    body = f"""
<header class="top">
  <h1>Morning brief</h1>
  <p class="sub">{run.overview["students_total"]} submissions, reviewed overnight ·
     prepared unattended, delivered unasked · <span class="mono">run {_e(run.run_id)}</span></p>
  <p class="thesis">What needs you, what is done, and the pattern across the class.
     No judgments — those are yours.</p>
</header>

<h2>What needs you — {len(needs)} item{"s" if len(needs) != 1 else ""}</h2>
<div class="panel scroll">
  <table><tr><th>Submission</th><th>Criterion</th><th>Why it is in your queue</th></tr>
  {needs_rows}</table>
</div>

<h2>What is done</h2>
<div class="panel"><p>{done_bits}.</p>
<p class="sub">Every count is a length over the claims projection.
<a href="/">Full docket</a> · <a href="/replay">watch the run replay</a>.</p></div>

<h2>Across the class</h2>
{pattern_blocks}
<p class="sub">A criterion appears here when at least a third of submissions (minimum two)
drew no evidence or escalated on it — the pattern an instructor otherwise finds by hand on
submission twelve. Examples are the students' own words, cited; Karani characterizes
nobody.</p>
"""
    return page("Karani — morning brief", body)
