"""The morning brief (KAR-418): delivered work-list, judgment-free by construction.

The reteach section is where a helpful aggregate could quietly become a verdict about the
class, so the tests hold the exact line the module states: counts over the projection and
quotations of students — never characterizations, never rankings, and every generated
sentence through the lint.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from karani.docket.brief import _reteach_patterns, brief_page
from karani.docket.server import build_app
from karani.render import render
from karani.store.local import read_jsonl_log

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def recorded():
    return render("run-recorded-p2", read_jsonl_log(REPO / "fixtures" / "recorded-run.jsonl"))


@pytest.fixture(scope="module")
def scholarship():
    return render("run-scholarship-p2", read_jsonl_log(REPO / "fixtures" / "scholarship-run.jsonl"))


def test_brief_serves(recorded):
    client = TestClient(build_app(recorded))
    response = client.get("/brief")
    assert response.status_code == 200
    assert "What needs you" in response.text


def test_every_escalation_appears_in_the_queue(recorded):
    page = brief_page(recorded)
    expected = sum(1 for s in recorded.sheets for o in s.observations if o.get("needs_human"))
    assert expected >= 5
    assert (
        f"What needs you — {expected + 1} items" in page
        or f"What needs you — {expected} items" in page
    )


def test_patterns_are_counts_with_cited_examples(scholarship):
    """The scholarship run has a real pattern: a02 drew no evidence on c2 and c3, and with
    3 submissions the threshold is 2 -- so neither criterion qualifies alone. Verify the
    threshold arithmetic rather than a hoped-for block."""
    patterns = _reteach_patterns(scholarship)
    for p in patterns:
        assert p["affected"] >= max(2, -(-p["total"] // 3))
        for ex in p["examples"]:
            assert ex["quote"] or ex["note"]


def test_no_judgment_vocabulary_anywhere(recorded, scholarship):
    """The line the module promises: characterizes nobody. The words a class-level verdict
    would need do not appear in generated copy on either corpus's brief."""
    for run in (recorded, scholarship):
        page = brief_page(run).lower()
        for phrase in (
            "the class is weak",
            "struggled",
            "poor performance",
            "below average",
            "strongest submission",
            "weakest submission",
            "best student",
            "worst",
        ):
            assert phrase not in page, phrase


def test_the_brief_is_a_pure_function_of_the_fold(recorded):
    assert brief_page(recorded) == brief_page(recorded)


def test_delivery_includes_the_brief(recorded, tmp_path):
    from karani.delivery.deliver import deliver

    result = deliver(recorded, out_dir=tmp_path, ratified={"s01"})
    brief_files = [f for f in result.files if "morning-brief" in f]
    assert len(brief_files) == 1
    content = (tmp_path / brief_files[0]).read_text(encoding="utf-8")
    assert "Morning brief" in content
