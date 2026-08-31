"""Editing the same observation twice (KAR-412).

The docket's central interaction is an instructor disagreeing with an observation. The
second-most-likely thing they do is disagree with it again — correct a wording, read it back,
correct it once more.

That returned a **500**. Event IDs are derived from `(run_id, step, item_id, attempt)`, and
none of those four changes between two edits of the same observation, so the second edit
minted an ID that already existed carrying different content and raised `EventIdCollision`.
The determinism that makes retries safe made a legitimate human action crash.

An instructor cannot be expected to know that their second correction is the one the system
cannot represent. These tests drive the endpoint the way a person would.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from karani.docket.server import build_app
from karani.render import render
from karani.store.local import LocalEventStore, read_jsonl_log

REPO = Path(__file__).resolve().parent.parent
RECORDED = REPO / "fixtures" / "recorded-run.jsonl"
RUN_ID = "run-recorded-p2"


@pytest.fixture
def client(tmp_path: Path):
    """A real store seeded with the recorded log, so edits append to genuine history."""
    store = LocalEventStore(tmp_path / "events")
    for event in read_jsonl_log(RECORDED):
        store.create(event)
    app = build_app(render(RUN_ID, store.read_run(RUN_ID)), store=store)
    return TestClient(app, follow_redirects=False)


def _first_observation(client) -> tuple[str, str]:
    run = client.app.state.karani["run"]
    for sheet in run.sheets:
        for obs in sheet.observations:
            return str(obs["observation_id"]), sheet.student_id
    raise AssertionError("the recorded run has no observations")


def _edit(client, observation_id: str, student_id: str, text: str):
    return client.post(
        "/edit",
        data={
            "observation_id": observation_id,
            "student_id": student_id,
            "text": text,
            "edit_reason": "instructor edit",
        },
    )


def test_a_single_edit_is_recorded(client):
    oid, sid = _first_observation(client)
    assert _edit(client, oid, sid, "First correction.").status_code == 303


def test_editing_the_same_observation_twice_does_not_500(client):
    """The regression. The second call raised EventIdCollision."""
    oid, sid = _first_observation(client)
    assert _edit(client, oid, sid, "First correction.").status_code == 303

    run = client.app.state.karani["run"]
    edited = next(
        o
        for s in run.sheets
        if s.student_id == sid
        for o in s.observations
        if o.get("supersedes") == oid
    )
    assert (
        _edit(client, str(edited["observation_id"]), sid, "Second correction.").status_code == 303
    )


def test_three_edits_produce_three_distinct_events(client):
    """Each correction is its own fact and keeps its own identity in the log."""
    oid, sid = _first_observation(client)
    current = oid
    for n in range(3):
        assert _edit(client, current, sid, f"Correction {n + 1}.").status_code == 303
        run = client.app.state.karani["run"]
        current = str(
            next(
                o
                for s in run.sheets
                if s.student_id == sid
                for o in s.observations
                if o.get("supersedes") == current
            )["observation_id"]
        )

    store = client.app.state.karani["store"]
    edit_events = [e for e in store.read_run(RUN_ID) if e.step.value == "ObservationEditedByHuman"]
    assert len(edit_events) == 3
    assert len({e.event_id for e in edit_events}) == 3


def test_every_earlier_version_survives(client):
    """Supersession never discards. An edited observation whose original is gone cannot
    be appealed, which is the entire reason edits are events rather than updates."""
    oid, sid = _first_observation(client)
    _edit(client, oid, sid, "First correction.")

    run = client.app.state.karani["run"]
    sheet = next(s for s in run.sheets if s.student_id == sid)
    assert any(o.get("observation_id") == oid for o in sheet.superseded)


def test_editing_twice_in_the_same_second_produces_distinct_ids(client):
    """The observation ID used `int(now.timestamp())`, so two fast edits collided there too."""
    oid, sid = _first_observation(client)
    _edit(client, oid, sid, "First.")
    run = client.app.state.karani["run"]
    first = next(
        o
        for s in run.sheets
        if s.student_id == sid
        for o in s.observations
        if o.get("supersedes") == oid
    )
    _edit(client, str(first["observation_id"]), sid, "Second.")
    run = client.app.state.karani["run"]
    second = next(
        o
        for s in run.sheets
        if s.student_id == sid
        for o in s.observations
        if o.get("supersedes") == first["observation_id"]
    )
    assert first["observation_id"] != second["observation_id"]
