"""The video run-book may only tell you to film things the recorded run contains."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from karani.render import render
from karani.store.local import read_jsonl_log

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "RUNBOOK.md"


@pytest.fixture(scope="module")
def escalations() -> set[tuple[str, str]]:
    run = render("run-recorded-p2", read_jsonl_log(REPO / "fixtures" / "recorded-run.jsonl"))
    return {
        (s.student_id, str(o["criterion_id"]))
        for s in run.sheets
        for o in s.observations
        if o.get("needs_human")
    }


def test_beat_six_names_an_observation_that_was_actually_escalated(escalations):
    """The run-book told the operator to film an instructor disagreeing with `s09` — an
    over-read the fixture manifest predicted and the run never produced. `s09`'s observations
    are correct. Filming an override of a right answer, narrated as the system being wrong,
    would have staged the one thing this project cannot afford to fake.
    """
    beat = RUNBOOK.read_text(encoding="utf-8").split("## Beat 6")[1].split("## Beat 7")[0]
    named = set(re.findall(r"`(s\d\d)` ?,? ?(?:criterion )?`(c\d)`", beat))
    assert named, "Beat 6 names no submission/criterion pair to film"
    unreal = named - escalations
    assert not unreal, f"Beat 6 tells the operator to film escalations that do not exist: {unreal}"
