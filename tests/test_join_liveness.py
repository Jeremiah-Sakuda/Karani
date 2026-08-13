"""KAR-314 — the join, tested against the case it exists for.

Every test here was written because an adversarial review **falsified the invariant by
execution**. "No run hangs" was asserted in the README, drawn in the architecture diagram, and
false: with one worker blocked, `run_pipeline` waited for it indefinitely.

These are the tests that would have caught it. They use real blocking, real clocks, and real
worker failures, because a mocked hang is not the thing that was broken.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from karani.analysis.cache import ResponseCache
from karani.analysis.client import ModelResponse
from karani.analysis.dispatcher import run_pipeline
from karani.analysis.prompts import Criterion
from karani.armor.scan import LocalPatternScanner
from karani.ingest.source import LocalSource
from karani.render import render
from karani.store.local import LocalEventStore

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CRITERIA = [Criterion("c1", "Thesis", "A position is stated.")]


class HangingClient:
    """Blocks forever on the first submission it sees. Answers normally for the rest.

    A real hang, not a simulated one: the point of the test is that the dispatcher does not
    wait for a worker that will never return, and a mock that merely *reports* being stuck
    would not exercise that.
    """

    backend = "hanging"

    def __init__(self, hang_seconds: float = 30.0) -> None:
        self.hang_seconds = hang_seconds
        self.hung_one = False

    def generate(self, *, system: str, prompt: str, model_id: str, key) -> ModelResponse:  # noqa: ANN001
        if not self.hung_one:
            self.hung_one = True
            time.sleep(self.hang_seconds)
        return ModelResponse(text='{"observations": []}', model_id=model_id, cached=False)


class ExplodingClient:
    """Raises on every call. A worker crash must not stop the run."""

    backend = "exploding"

    def generate(self, *, system: str, prompt: str, model_id: str, key) -> ModelResponse:  # noqa: ANN001
        raise RuntimeError("worker exploded")


def test_a_hung_worker_does_not_hang_the_run(tmp_path):
    """Property: `T_max` bounds the RUN, not the gap between completions.

    The regression this pins: `as_completed(futures, timeout=None)` only evaluates the loop
    body when a future completes, so the deadline check inside the loop was unreachable while
    a worker was blocked. Measured before the fix — one worker sleeping 30s against
    `t_max_seconds=2` returned after 30 seconds.

    A run that hangs at 03:00 is a run the instructor finds at 08:00 with nothing to show, and
    it is the single failure an unattended system cannot have.
    """
    store = LocalEventStore(tmp_path / "store")
    cache = ResponseCache(tmp_path / "cache")

    started = time.monotonic()
    summary = run_pipeline(
        run_id="run-hang",
        source=LocalSource(FIXTURES / "dev"),
        criteria=CRITERIA,
        store=store,
        client=HangingClient(hang_seconds=30.0),
        cache=cache,
        scanner=LocalPatternScanner(),
        max_workers=3,
        t_max_seconds=2,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 15, f"run took {elapsed:.1f}s against a T_max of 2s; the join did not bound it"
    assert summary.abandoned, "the hung unit was not abandoned"

    rendered = render("run-hang", store.read_run("run-hang"))
    assert rendered.excluded, "the abandoned unit does not appear in excluded[]"
    assert rendered.overview["terminal_outcomes"]["abandoned"] >= 1


def test_every_dispatched_unit_reaches_a_terminal_state_even_when_one_hangs(tmp_path):
    """Property: the join accounts for everything, including what never answered."""
    store = LocalEventStore(tmp_path / "store")
    summary = run_pipeline(
        run_id="run-hang2",
        source=LocalSource(FIXTURES / "dev"),
        criteria=CRITERIA,
        store=store,
        client=HangingClient(hang_seconds=20.0),
        cache=ResponseCache(tmp_path / "cache"),
        scanner=LocalPatternScanner(),
        max_workers=3,
        t_max_seconds=2,
    )

    accounted = set(summary.completed) | set(summary.failed) | set(summary.abandoned)
    assert accounted == set(summary.dispatched)


def test_a_unit_is_abandoned_at_most_once(tmp_path):
    """Property: the dispatcher never writes two `TaskAbandoned` events for one unit.

    Two abandonments for the same student with different reasons — "run_aborted" then
    "join_timeout" — mint the same deterministic event ID with different content, which is a
    genuine `EventIdCollision`. The store was right to raise; the caller was wrong to ask.

    That crashed the run-level circuit breaker: the one mechanism whose entire job is to end a
    run cleanly was the mechanism that could not.
    """
    store = LocalEventStore(tmp_path / "store")
    summary = run_pipeline(
        run_id="run-once",
        source=LocalSource(FIXTURES / "dev"),
        criteria=CRITERIA,
        store=store,
        client=HangingClient(hang_seconds=20.0),
        cache=ResponseCache(tmp_path / "cache"),
        scanner=LocalPatternScanner(),
        max_workers=3,
        t_max_seconds=1,
    )

    assert len(summary.abandoned) == len(set(summary.abandoned)), (
        f"a unit was abandoned more than once: {summary.abandoned}"
    )

    abandon_events = [e for e in store.read_run("run-once") if e.step.value == "TaskAbandoned"]
    per_student = [e.item_id for e in abandon_events]
    assert len(per_student) == len(set(per_student)), "duplicate TaskAbandoned events"


def test_a_crashing_worker_does_not_stop_the_run(tmp_path):
    """Property: one worker's crash is that unit's problem, not the run's."""
    store = LocalEventStore(tmp_path / "store")
    summary = run_pipeline(
        run_id="run-boom",
        source=LocalSource(FIXTURES / "dev"),
        criteria=CRITERIA,
        store=store,
        client=ExplodingClient(),
        cache=ResponseCache(tmp_path / "cache"),
        scanner=LocalPatternScanner(),
        max_workers=3,
    )

    assert summary.failed, "the crashing workers were not recorded as failures"
    accounted = set(summary.completed) | set(summary.failed) | set(summary.abandoned)
    assert accounted == set(summary.dispatched)

    # And the run still rendered.
    rendered = render("run-boom", store.read_run("run-boom"))
    assert rendered.anomalies, "a crashed worker produced no anomaly item"


@pytest.mark.parametrize("t_max", [1, 2])
def test_render_fires_after_t_max_regardless_of_outstanding_work(tmp_path, t_max):
    """Property: the artifact exists even when the run did not finish cleanly.

    An unattended system that produces nothing when something goes wrong has not degraded --
    it has failed. The instructor should find a docket with holes in it, clearly marked, not
    an empty screen.
    """
    store = LocalEventStore(tmp_path / f"store{t_max}")
    run_pipeline(
        run_id=f"run-tmax{t_max}",
        source=LocalSource(FIXTURES / "dev"),
        criteria=CRITERIA,
        store=store,
        client=HangingClient(hang_seconds=20.0),
        cache=ResponseCache(tmp_path / f"cache{t_max}"),
        scanner=LocalPatternScanner(),
        max_workers=3,
        t_max_seconds=t_max,
    )

    rendered = render(f"run-tmax{t_max}", store.read_run(f"run-tmax{t_max}"))
    assert rendered.sheets or rendered.excluded, "the run produced no artifact at all"
