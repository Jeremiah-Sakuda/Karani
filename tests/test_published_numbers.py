"""Published numbers must equal what the committed log actually says.

Two independent reviewers computed the histogram from `fixtures/recorded-run.jsonl` and got a
different answer from the one this repository published. The README said **90.5% (67/74)**
first-attempt acceptance; the log says **63**. The 67 counted observations *"not rejected on
attempt 1"*, which folds in the four that were **escalated to a human** rather than accepted.
"Accepted after bounded retry: 7" was the count of attempt-2 *drafts*, two of which also
escalated; the real figure is 5.

The docket had been displaying 63 on screen the entire time. A judge who ran `make demo` and
did the arithmetic would have found the measurement contract broken by the project that
invented it — which is worse than having no contract.

`scripts/release_check.py` could not catch it: it checks that numbers are *present*, not that
they are *true*. These tests close that gap by recomputing from the log and comparing.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "fixtures" / "recorded-run.jsonl"
METRICS = json.loads((REPO / "docs" / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def histogram() -> dict[str, int]:
    """The truth, recomputed from the committed log on every run."""
    accepted: collections.Counter[int] = collections.Counter()
    escalated = absent = 0
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        step = event["step"]
        if step == "ObservationAccepted":
            accepted[int(event["payload"]["observation"].get("attempts", 1))] += 1
        elif step == "NeedsHumanReview":
            escalated += 1
        elif step == "NoEvidenceRecorded":
            absent += 1
    return {
        "first": accepted[1],
        "retried": accepted[2],
        "escalated": escalated,
        "absent": absent,
        "cited": accepted[1] + accepted[2] + escalated,
    }


def test_first_attempt_rate_matches_the_log(histogram):
    """Property: the headline rate is derived, not asserted."""
    published = METRICS["validation"]["first_attempt_acceptance_rate"]["value"]
    actual = histogram["first"] / histogram["cited"]
    assert abs(published - actual) < 0.0005, (
        f"metrics.json publishes {published:.1%}; the log says "
        f"{histogram['first']}/{histogram['cited']} = {actual:.1%}"
    )


def test_accepted_after_retry_counts_acceptances_not_drafts(histogram):
    """Property: "accepted after retry" means accepted, not attempted.

    The original error: counting attempt-2 *drafts*. Two of them escalated, so the published
    7 described work done rather than work that succeeded.
    """
    assert METRICS["validation"]["accepted_after_retry"]["value"] == histogram["retried"]


def test_escalations_are_not_counted_as_acceptances(histogram):
    """Property: the two categories are disjoint.

    This is the exact conflation that produced 67. An observation that reached a human is not
    an observation the system accepted, and folding them together inflates the one number the
    whole measurement contract exists to keep honest.
    """
    accepted_total = (
        METRICS["validation"]["accepted_first_attempt"]["value"]
        + METRICS["validation"]["accepted_after_retry"]["value"]
    )
    assert accepted_total + histogram["escalated"] == histogram["cited"]
    assert METRICS["validation"]["escalated_needs_human"]["value"] == histogram["escalated"]


@pytest.mark.parametrize("doc", ["README.md", "docs/FINDINGS.md", "docs/RUNBOOK.md"])
def test_no_document_publishes_a_stale_rate(doc, histogram):
    """Property: every published copy of the rate agrees with the log.

    Numbers get corrected in one file and left stale in three. This checks every percentage
    that appears next to the phrase "first-attempt" across the public documents.
    """
    text = (REPO / doc).read_text(encoding="utf-8")
    actual = f"{histogram['first'] / histogram['cited']:.1%}"

    # Bounded by comma and newline on purpose. A looser window matched the *entailment*
    # percentage in "85.1% first-attempt (63/74), 6.8% entailment disagreement" and failed on
    # a number that was never claiming to be this one.
    patterns = (
        r"(\d{1,3}\.\d)%[^,\n]{0,20}?first-attempt",
        r"first-attempt[^,\n]{0,20}?(\d{1,3}\.\d)%",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            assert match.group(1) + "%" == actual, (
                f"{doc} publishes {match.group(1)}% as the first-attempt rate; "
                f"the log says {actual}"
            )


# --- the fold must not show an instructor a citation the validator refused ---------------


def test_a_twice_rejected_draft_never_renders_its_citation():
    """Property: the sheet shows no citation the validator refused.

    The attempt-cap escalation event carries no observation, so the fold used to fall back to
    the rejected draft — putting a span that does not exist and a quote appearing nowhere in
    the submission onto the instructor's sheet, in a blockquote, styled as the student's own
    words. That falsified "every evidence observation cites a real span" on the one screen
    where it matters, and `rejected_criteria` had been computed for exactly this and never read.

    The escalation still renders — the instructor is being asked to look at it — but as an
    absence, with notes saying nothing passed.
    """
    from datetime import UTC, datetime

    from karani.render import render
    from karani.schema.events import Event, Step

    ts = datetime(2026, 8, 31, tzinfo=UTC)
    bad = {
        "observation_id": "obs-s01-c3-a2",
        "run_id": "r",
        "student_id": "s01",
        "criterion_id": "c3",
        "kind": "evidence",
        "text": "The submission addresses this criterion.",
        "citation": {
            "span_id": "sp-9999",
            "quote": "invented text that appears nowhere",
            "quote_hash": "0" * 64,
            "prefix": "",
            "suffix": "",
        },
        "attempts": 2,
    }
    events = [
        Event.build(
            run_id="r",
            step=Step.SUBMISSION_INGESTED,
            item_id="s01",
            ts=ts,
            payload={"student_id": "s01"},
        ),
        Event.build(
            run_id="r",
            step=Step.OBSERVATION_DRAFTED,
            item_id="s01::c3",
            ts=ts,
            attempt=2,
            payload={"student_id": "s01", "observation": bad},
        ),
        Event.build(
            run_id="r",
            step=Step.OBSERVATION_REJECTED,
            item_id="s01::c3",
            ts=ts,
            attempt=2,
            payload={
                "student_id": "s01",
                "criterion_id": "c3",
                "failed_layer": "referential",
                "reason": "no such span",
            },
        ),
        Event.build(
            run_id="r",
            step=Step.NEEDS_HUMAN_REVIEW,
            item_id="s01::c3",
            ts=ts,
            attempt=2,
            payload={
                "student_id": "s01",
                "criterion_id": "c3",
                "observation_id": "obs-s01-c3-a2",
                "anomaly_kind": "attempt_cap_reached",
                "reason": "citation validation failed on 2 attempts",
            },
        ),
    ]

    rendered = render("r", events)
    shown = [o for s in rendered.sheets for o in s.observations]
    assert shown, "the escalation should still be visible to the instructor"

    for obs in shown:
        assert obs.get("citation") is None, (
            f"a refused citation reached the sheet: {obs.get('citation')}"
        )
        assert "sp-9999" not in json.dumps(obs), "the invented span id is still on the sheet"
        assert "invented text" not in json.dumps(obs), "the invented quote is still on the sheet"
