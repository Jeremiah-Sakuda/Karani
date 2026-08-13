"""KAR-105 — event-ID collision semantics, and the append-only surface.

The two branches are the whole requirement, and they must not be conflated:

- **Identical payloads self-dedupe.** A worker retried at the same attempt number rewrites
  the same fact. That is normal, expected, and not an error.
- **Differing payloads raise.** Two different facts have claimed one identity. Silently
  keeping either one corrupts every artifact folded from this log, and the corruption is
  invisible downstream — the evidence sheet renders perfectly and is wrong.

A system that only implemented the first branch would look correct in every happy-path test
and would quietly drop real observations in production.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from karani.schema.events import Event, EventIdCollision, Step, make_event_id
from karani.store import EventStore
from karani.store.local import LocalEventStore

T = datetime(2026, 8, 12, 3, 0, 0, tzinfo=UTC)


def _event(payload: dict, *, attempt: int = 1) -> Event:
    return Event.build(
        run_id="run-1",
        step=Step.OBSERVATION_ACCEPTED,
        item_id="s01::c1",
        ts=T,
        attempt=attempt,
        payload=payload,
    )


def test_event_id_is_deterministic_from_its_coordinates():
    """Property: identity is derived from what the event is, not from when it was written.

    This is what makes writes idempotent by construction. If IDs were generated, a retry
    would create a second event and the dedupe would have to be a separate mechanism that
    could itself be wrong.
    """
    a = make_event_id("run-1", Step.OBSERVATION_ACCEPTED, "s01::c1", 1)
    b = make_event_id("run-1", Step.OBSERVATION_ACCEPTED, "s01::c1", 1)
    assert a == b

    assert a != make_event_id("run-1", Step.OBSERVATION_ACCEPTED, "s01::c1", 2)
    assert a != make_event_id("run-1", Step.OBSERVATION_ACCEPTED, "s01::c2", 1)
    assert a != make_event_id("run-1", Step.OBSERVATION_REJECTED, "s01::c1", 1)


def test_content_hash_excludes_the_timestamp():
    """Property: a legitimate retry is recognised as the same fact despite a moved clock.

    If `ts` participated in the content hash, every idempotent retry would raise
    `EventIdCollision`. The collision alarm would fire constantly, operators would learn to
    ignore it, and it would be useless on the one occasion it mattered.
    """
    first = Event.build(
        run_id="run-1",
        step=Step.OBSERVATION_ACCEPTED,
        item_id="s01::c1",
        ts=T,
        attempt=1,
        payload={"observation_id": "obs-1"},
    )
    later = Event.build(
        run_id="run-1",
        step=Step.OBSERVATION_ACCEPTED,
        item_id="s01::c1",
        ts=datetime(2026, 8, 12, 4, 30, tzinfo=UTC),
        attempt=1,
        payload={"observation_id": "obs-1"},
    )

    assert first.event_id == later.event_id
    assert first.content_hash == later.content_hash


def test_identical_payload_self_dedupes(tmp_path):
    """Property: writing the same fact twice is a no-op, not an error."""
    store = LocalEventStore(tmp_path)
    event = _event({"observation_id": "obs-1", "kind": "evidence"})

    assert store.create(event) is True, "first write should be accepted"
    assert store.create(event) is False, "identical rewrite should self-dedupe"
    assert len(store.read_run("run-1")) == 1


def test_differing_payload_raises_rather_than_deduping(tmp_path):
    """Property: two different facts under one ID stop the run.

    Note what is asserted after the raise: the *original* event is still the one on disk.
    Failing loudly is only half the guarantee — the log must also be unchanged, or the
    collision would have already done its damage before anyone saw the exception.
    """
    store = LocalEventStore(tmp_path)
    original = _event({"observation_id": "obs-1", "kind": "evidence"})
    conflicting = _event({"observation_id": "obs-1", "kind": "no_evidence"})

    assert store.create(original) is True

    with pytest.raises(EventIdCollision) as excinfo:
        store.create(conflicting)

    assert excinfo.value.event_id == original.event_id
    assert excinfo.value.existing_hash != excinfo.value.incoming_hash

    stored = store.read_run("run-1")
    assert len(stored) == 1
    assert stored[0].payload["kind"] == "evidence", "the existing event was overwritten"


def test_collision_is_detected_across_process_boundaries(tmp_path):
    """Property: collision detection survives a restart.

    A fresh store instance rebuilds its index from disk. If detection depended on in-process
    state, a worker restarted after a crash — precisely when retries happen — would write
    straight through the check.
    """
    first = LocalEventStore(tmp_path)
    first.create(_event({"observation_id": "obs-1", "kind": "evidence"}))

    second = LocalEventStore(tmp_path)  # simulates a new process
    with pytest.raises(EventIdCollision):
        second.create(_event({"observation_id": "obs-1", "kind": "no_evidence"}))


def test_store_interface_exposes_no_mutation_methods():
    """Property: the log's append-only shape is structural at the interface, not a habit.

    This is the weakest of the three append-only defences and is labelled as such: it binds
    callers that go through this interface and nothing else. The real enforcement is the
    custom IAM role (`create` + `get`, no `update`/`delete`) asserted on the deployed path
    by KAR-102's negative tests, plus Firestore rules for the browser surface.
    """
    for forbidden in ("update", "delete", "set", "merge", "overwrite", "replace"):
        assert not hasattr(EventStore, forbidden), f"EventStore exposes {forbidden}()"
        assert not hasattr(LocalEventStore, forbidden), f"LocalEventStore exposes {forbidden}()"


def test_local_store_never_rewrites_existing_lines(tmp_path):
    """Property: append-only on disk, not only in the API.

    The bytes already written are still there, unchanged, at the same offsets. A store that
    rewrote its file to stay tidy could lose the evidence of the very event that caused a
    crash.
    """
    store = LocalEventStore(tmp_path)
    store.create(_event({"observation_id": "obs-1"}, attempt=1))

    path = next(tmp_path.glob("*.jsonl"))
    first_bytes = path.read_bytes()

    store.create(_event({"observation_id": "obs-2"}, attempt=2))
    after = path.read_bytes()

    assert after.startswith(first_bytes)
    assert len(after) > len(first_bytes)


def test_unknown_step_is_rejected():
    """Property: the event vocabulary is closed.

    An invented event type would be silently ignored by `render()`, producing an artifact
    that is quietly missing something — the worst failure mode available to a log whose
    entire purpose is completeness.
    """
    with pytest.raises(ValueError):
        Event(
            event_id="x",
            run_id="run-1",
            step="ObservationApproved",  # type: ignore[arg-type]
            item_id="s01::c1",
            ts=T,
        )
