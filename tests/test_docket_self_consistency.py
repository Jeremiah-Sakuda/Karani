"""The docket may not disagree with itself on one screen (KAR-404).

An adversarial review found the overview showing a tile reading "no evidence located: 1" and,
420 pixels below it, a by-criterion table summing to `no_evidence = 2` — both footnoted
"Counted from the claims projection, never generated."

Neither number was fabricated. The tile counted each observation's terminal outcome; the
table counted its `kind`; and an observation that located nothing *and* was escalated to a
human is `no_evidence` by kind and `needs_human` by outcome, so it appeared in a different
column of each. Two honest counts of two different units, presented as one.

For this project that is a serious defect rather than a cosmetic one. The docket's claim on
a reader is that every number on it is a count they could redo by hand from the projection
underneath. A page that contradicts itself falsifies that claim wherever a reader checks it,
and they have no way to tell which of the two numbers is the one they should trust.

These tests assert the identity that makes the page auditable: **one observation, one
terminal outcome, counted once**, so every column of the table sums to its tile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from karani.render import TERMINAL_OUTCOMES, render
from karani.store.local import read_jsonl_log

from .factories import golden_events

REPO = Path(__file__).resolve().parent.parent
RECORDED = REPO / "fixtures" / "recorded-run.jsonl"


def _rendered_recorded():
    return render("run-recorded-p2", read_jsonl_log(RECORDED))


def _rendered_golden():
    events = golden_events()
    return render(events[0].run_id, events)


@pytest.fixture(params=["recorded", "golden"])
def rendered(request):
    return _rendered_recorded() if request.param == "recorded" else _rendered_golden()


@pytest.mark.parametrize("column", ["evidence", "no_evidence", "needs_human"])
def test_each_table_column_sums_to_its_tile(rendered, column):
    """The identity the review's finding violated."""
    overview = rendered.overview
    table_total = sum(v[column] for v in overview["by_criterion"].values())

    if column == "evidence":
        tile_total = (
            overview["terminal_outcomes"]["accepted_first_attempt"]
            + overview["terminal_outcomes"]["accepted_after_retry"]
        )
    else:
        tile_total = overview["terminal_outcomes"][column]

    assert table_total == tile_total, (
        f"the by-criterion table says {column}={table_total} and the outcome tiles say "
        f"{tile_total}; the docket is contradicting itself on one screen"
    )


def test_every_observation_is_counted_exactly_once(rendered):
    """No observation appears in two columns, and none is dropped from all of them."""
    counted = sum(sum(v.values()) for v in rendered.overview["by_criterion"].values())
    assert counted == len(rendered.claims)


def test_the_tiles_cover_every_observation(rendered):
    """Every observation ends in one of the six terminal outcomes, so the tiles are total.

    Two outcomes are excluded from the identity, both for the same reason — they count a
    different unit than a claim does:

    - `injection_detected` is per *submission*. A flagged submission still produces
      observations, by design (KAR-311).
    - `abandoned` work produces no claim at all, which is precisely why the by-criterion
      table has no column for it.
    """
    outcomes = rendered.overview["terminal_outcomes"]
    per_observation = sum(
        outcomes[name]
        for name in TERMINAL_OUTCOMES
        if name not in ("injection_detected", "abandoned")
    )
    assert per_observation == len(rendered.claims)


def test_abandoned_work_is_absent_from_the_claims_projection(rendered):
    """The assumption the missing column rests on, asserted rather than believed.

    If abandoned work ever *did* reach the projection, the table would silently drop it —
    `_outcome_column` returns None for it — and `test_every_observation_is_counted_exactly
    _once` would start failing with no indication of why. This says why.
    """
    abandoned_ids = {
        oid for oid, name in rendered.outcome_by_observation.items() if name == "abandoned"
    }
    claim_ids = {str(o.get("observation_id", "")) for o in rendered.claims}
    assert not (abandoned_ids & claim_ids)


def test_the_golden_log_actually_exercises_abandonment(rendered, request):
    """Guard against the two tests above passing because nothing was ever abandoned."""
    if request.node.callspec.params["rendered"] != "golden":
        pytest.skip("only the golden log carries an abandoned unit of work")
    assert rendered.overview["terminal_outcomes"]["abandoned"] > 0
