"""The glass-box replay (KAR-416): the run watched, without a byte of generated text.

The replay dramatizes the committed log, and a dramatization of a record has one honest
form: the record's own order, its own timestamps, and none of its prose. Payloads carry
model-generated text; every generated-text surface in this project passes the verdict lint,
and the cheapest way to keep the replay lint-clean forever is for payloads never to reach it
at all. These tests hold that line.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from karani.docket.replay import replay_events_json
from karani.docket.server import build_app
from karani.render import render
from karani.store.local import read_jsonl_log

REPO = Path(__file__).resolve().parent.parent
RECORDED = REPO / "fixtures" / "recorded-run.jsonl"
RUN_ID = "run-recorded-p2"


@pytest.fixture(scope="module")
def events():
    return read_jsonl_log(RECORDED)


@pytest.fixture(scope="module")
def client(events):
    return TestClient(build_app(render(RUN_ID, events), events=events))


def test_replay_serves(client):
    response = client.get("/replay")
    assert response.status_code == 200
    assert "Replay the night" in response.text


def test_replay_data_is_every_event_in_fold_order(events):
    data = json.loads(replay_events_json(RUN_ID, events))
    ordered = sorted((e for e in events if e.run_id == RUN_ID), key=lambda e: e.sort_key)
    assert len(data["events"]) == len(ordered)
    assert [r["step"] for r in data["events"]] == [e.step.value for e in ordered]


def test_no_payload_field_ever_reaches_the_browser(events):
    """The load-bearing property: metadata only."""
    data = json.loads(replay_events_json(RUN_ID, events))
    for row in data["events"]:
        assert set(row) == {"step", "item", "attempt", "ts"}


def test_no_generated_text_appears_in_the_replay_payload(client, events):
    """Belt and braces: no observation text from the run occurs anywhere in the page.

    Checks actual model prose against the served bytes, so a future field addition that
    smuggles payload content in under a new name still fails here.
    """
    page = client.get("/replay").text
    rendered = render(RUN_ID, events)
    checked = 0
    for sheet in rendered.sheets:
        for obs in sheet.observations:
            text = str(obs.get("text", ""))
            if len(text) > 40:
                checked += 1
                assert text not in page
    assert checked > 10


def test_replay_without_events_is_a_404_not_a_crash():
    client = TestClient(build_app(render(RUN_ID, []), events=None))
    assert client.get("/replay").status_code == 404
