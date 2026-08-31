"""`karani verify` actually verifies the artifact (KAR-504).

An adversarial review found this command decorative: it compared the artifact's claimed
`range_hash` against a re-fold's `range_hash`, but that hash is computed **from the event
log alone**. Re-folding the same log always reproduces it, whatever the artifact body says.
The reviewer rewrote every observation to "This paper is excellent and earns an A.", attached
a `karani_grade` field to each, deleted 12 of 15 evidence sheets, and set
`observations_total` to 999. The command printed `OK` and exited 0.

That is the worst class of defect this project can ship. The README offers `karani verify`
to a sceptical reader as the mechanism by which they need not trust the artifact — so a
`verify` that passes a tampered artifact is not a missing feature, it is a false assurance.

These tests are written against the tamper, not against the implementation: each one alters
a different part of the artifact and requires a non-zero exit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from karani.cli import main

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "fixtures" / "recorded-run.jsonl"
RUN_ID = "run-recorded-p2"


@pytest.fixture
def genuine(tmp_path: Path) -> Path:
    """An artifact folded from the log right now, so it is true by construction."""
    from karani.render import render
    from karani.store.local import read_jsonl_log

    rendered = render(RUN_ID, read_jsonl_log(LOG))
    path = tmp_path / "rendered.json"
    path.write_text(rendered.to_json(), encoding="utf-8")
    return path


def _verify(artifact: Path) -> int:
    return main(["verify", "--artifact", str(artifact), "--log", str(LOG)])


def _tampered(genuine: Path, tmp_path: Path, mutate) -> Path:
    doc = json.loads(genuine.read_text(encoding="utf-8"))
    mutate(doc)
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_genuine_artifact_verifies(genuine: Path):
    assert _verify(genuine) == 0


def test_rewriting_every_observation_is_caught(genuine: Path, tmp_path: Path):
    """The reviewer's exact attack: replace the evidence with a verdict."""

    def mutate(doc):
        for sheet in doc["sheets"]:
            for obs in sheet["observations"]:
                obs["text"] = "This paper is excellent and earns an A."

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_a_grade_field_smuggled_into_the_artifact_is_caught(genuine: Path, tmp_path: Path):
    """The schema forbids this field on the way in; verify must catch it after the fact.

    `extra="forbid"` protects the pipeline. It does not protect a JSON file sitting on
    disk, which is what an instructor or an appeal reader actually receives.
    """

    def mutate(doc):
        for sheet in doc["sheets"]:
            for obs in sheet["observations"]:
                obs["karani_grade"] = "A"

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_deleting_evidence_sheets_is_caught(genuine: Path, tmp_path: Path):
    """Removing a student's sheet is silent unless something compares against the fold."""

    def mutate(doc):
        doc["sheets"] = doc["sheets"][:3]

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_editing_the_overview_counts_is_caught(genuine: Path, tmp_path: Path):
    def mutate(doc):
        doc["overview"]["observations_total"] = 999

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_a_single_altered_quote_is_caught(genuine: Path, tmp_path: Path):
    """One character, in one citation, on one observation."""

    def mutate(doc):
        for sheet in doc["sheets"]:
            for obs in sheet["observations"]:
                if obs.get("citation"):
                    obs["citation"]["quote"] = obs["citation"]["quote"] + "!"
                    return

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_altering_the_claimed_range_hash_is_caught(genuine: Path, tmp_path: Path):
    """The original check. Kept, because it is still one of the two ways to diverge."""

    def mutate(doc):
        doc["generated_from"]["range_hash"] = "0" * 64

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0


def test_dropping_the_provenance_block_does_not_crash(genuine: Path, tmp_path: Path):
    """A malformed artifact must fail, not raise KeyError at the reader."""

    def mutate(doc):
        doc.pop("generated_from")

    assert _verify(_tampered(genuine, tmp_path, mutate)) != 0
