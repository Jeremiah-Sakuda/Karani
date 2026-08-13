"""KAR-103 — `render(runId)` is a pure fold.

The environment this runs in is part of the test. `conftest.py` strips every Google
credential variable for the whole session, and this module additionally folds a *shuffled*
log. A `render()` that consulted a store, a clock, or the network would fail here rather
than succeed quietly on an inherited credential — which is the failure this test exists to
make impossible.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from karani.render import TERMINAL_OUTCOMES, render
from karani.store.local import read_jsonl_log

from .factories import golden_events

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden-log.jsonl"


def test_no_google_credentials_are_present():
    """Property: the replay path genuinely has no credentials available to fall back on.

    Asserted rather than assumed. If this repository's CI ever grew a service-account
    credential in the ambient environment, every other test in this file would keep passing
    while silently no longer proving that `render()` is offline.
    """
    for var in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "FIRESTORE_EMULATOR_HOST",
    ):
        assert not os.environ.get(var), f"{var} is set; the replay test is not running offline"


def test_shuffled_log_folds_to_byte_identical_output():
    """Property: the rendered artifact is a function of the event *set*, not of its order.

    Ten independent shuffles, each compared byte-for-byte against the in-order fold. Order
    independence is what makes the log the source of truth: workers finish in whatever order
    the scheduler gives them, and a fold that depended on arrival order would produce a
    different evidence sheet on every run over identical facts.
    """
    events = golden_events()
    baseline = render("run-golden", events).to_json()

    rng = random.Random(20260812)
    for i in range(10):
        shuffled = events[:]
        rng.shuffle(shuffled)
        assert shuffled != events or len(events) < 2, "shuffle was a no-op"
        assert render("run-golden", shuffled).to_json() == baseline, f"shuffle {i} diverged"


def test_committed_golden_log_folds_to_the_same_artifact():
    """Property: the committed log on disk and the in-code factory describe the same run.

    This is the check that catches drift. `fixtures/golden-log.jsonl` is what the docket
    serves, what `make docket-golden` renders, and what appears on camera; the factory is
    what the rest of the suite tests against. If they diverge, the demo stops being a
    demonstration of the tested system.
    """
    assert GOLDEN.exists(), "fixtures/golden-log.jsonl is missing; run scripts/make_golden_log.py"

    from_disk = read_jsonl_log(GOLDEN)
    from_code = golden_events()

    assert render("run-golden", from_disk).to_json() == render("run-golden", from_code).to_json()


def test_fold_is_independent_of_the_working_directory(tmp_path, monkeypatch):
    """Property: no path, config file, or relative lookup participates in the fold."""
    events = golden_events()
    baseline = render("run-golden", events).to_json()

    monkeypatch.chdir(tmp_path)
    assert render("run-golden", events).to_json() == baseline


def test_render_ignores_events_from_other_runs():
    """Property: `render(runId)` folds one run, not whatever happens to be in the log.

    Two runs share a store. A fold that ignored the run ID would mix them and produce an
    evidence sheet containing another run's observations.
    """
    events = golden_events("run-golden")
    other = golden_events("run-other")

    baseline = render("run-golden", events).to_json()
    assert render("run-golden", events + other).to_json() == baseline


def test_range_hash_changes_when_any_event_changes():
    """Property: divergence is detectable, not assumed.

    Every artifact carries a hash over the events it consumed. Dropping a single event has
    to change that hash, or `scripts/verify_artifact.py` would certify an artifact that no
    longer matches its log.
    """
    events = golden_events()
    full = render("run-golden", events)
    truncated = render("run-golden", events[:-1])

    assert full.range_hash != truncated.range_hash
    assert len(full.source_events) == len(events)


@pytest.mark.parametrize(
    "outcome",
    [
        "accepted_first_attempt",
        "accepted_after_retry",
        "needs_human",
        "no_evidence",
    ],
)
def test_golden_run_exercises_each_observation_outcome(outcome):
    """Property: the golden run really does diverge six ways.

    The divergence tour is the video's central claim (§8 beat 4). If the golden log only
    contained accepted observations, that beat would be a claim about a run that never
    happened.
    """
    result = render("run-golden", golden_events())
    assert result.overview["terminal_outcomes"][outcome] >= 1, (
        f"the golden run produces no {outcome} outcome"
    )


def test_all_six_terminal_outcomes_are_non_zero_in_the_golden_run():
    """Property (§1.2, §8 beat 4): the divergence tour is not showing a zero.

    The strongest claim this project makes is that ONE unattended run produces SIX visibly
    different consequences. The class overview renders that as six counts side by side, and
    the video points a camera at it.

    This test exists because that panel shipped reading "injection flagged: 0" on a run where
    the injection had been detected, flagged, and displayed with a chip two panels lower on
    the same page. The count came from a map keyed by observation, and injection is a terminal
    outcome of a *submission* — a flagged submission still produces observations, by design.
    So the headline claim was quietly contradicting the table underneath it.

    Asserting every outcome individually, so a regression names which one went to zero.
    """
    result = render("run-golden", golden_events())
    counts = result.overview["terminal_outcomes"]

    for name in TERMINAL_OUTCOMES:
        assert counts.get(name, 0) > 0, (
            f"the golden run reports 0 for '{name}'. The divergence tour is the central "
            f"claim of the demo; a zero there is the claim failing on camera."
        )


def test_golden_run_shows_injection_and_abandonment():
    """Property: the two outcomes that are not observation-shaped are also present.

    Injection is attached to a student and does not stop their analysis; abandonment removes
    a unit from the run without hanging it. Both are visible in the rendered artifact.
    """
    result = render("run-golden", golden_events())

    flagged = [s for s in result.sheets if s.injection_flagged]
    assert flagged, "no injection-flagged sheet in the golden run"
    # The whole point of KAR-311: a flagged submission is still analysed. A blocked file is
    # a student penalised for something they may not have written.
    assert flagged[0].observations, "injection-flagged student has no observations"

    assert result.excluded, "no abandoned unit in the golden run"
    assert result.overview["excluded_total"] == len(result.excluded)
