"""KAR-101 — the schemas, and the invariant that lives in what they cannot express.

The central claim of this project is that Karani is *architecturally* incapable of issuing a
grade. That claim is only worth anything if it is enforced somewhere a reader can check. It
is enforced here: the observation schema has no field that could carry a verdict, and it
forbids extras, so one cannot be attached at runtime either.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from karani.config import TEMPERATURE
from karani.schema.observation import (
    BANNED_FIELD_NAMES,
    Observation,
    Provenance,
)
from karani.schema.rendition import compute_rendition_id
from karani.schema.spans import SpanRegistry

from .factories import T0, demo_rendition, provenance


def _base(**overrides):
    payload = {
        "observation_id": "obs-1",
        "run_id": "run-1",
        "student_id": "s01",
        "criterion_id": "c1",
        "kind": "evidence",
        "text": "The submission addresses this criterion.",
        "provenance": provenance(),
        "created_at": T0,
    }
    payload.update(overrides)
    return payload


# --- KAR-101's three stated acceptance criteria --------------------------------------


def test_evidence_without_citation_fails_validation():
    """Property: an uncited claim cannot exist as a valid record.

    This is the failure this whole system is built to prevent, so it is prevented at the
    narrowest point — construction — rather than at a review step something could skip.
    """
    with pytest.raises(ValidationError, match="must carry a citation"):
        Observation(**_base(kind="evidence", citation=None))


def test_no_evidence_with_null_citation_passes():
    """Property: absence is a first-class finding, not a degenerate error case.

    `no_evidence` is a valid, complete, uncited record. Making it representable is what
    lets it be excluded from the retry loop (KAR-308) — and that exclusion is what keeps
    the attempt cap from becoming pressure to invent a citation for something that is
    genuinely not there.
    """
    obs = Observation(
        **_base(
            kind="no_evidence",
            citation=None,
            text="No passage addressing this criterion was located.",
            search_notes="Scanned all registered spans; no passage located.",
        )
    )
    assert obs.kind == "no_evidence"
    assert obs.citation is None


def test_record_missing_prompt_version_fails_validation():
    """Property: an observation always knows what produced it.

    Provenance has to land with the first schema rather than be retrofitted, because
    retrofitting it after the analysis phase means re-running every fixture — and an
    observation whose prompt version is unknown cannot participate in `diff_runs.py` or in
    any reproducibility claim.
    """
    with pytest.raises(ValidationError):
        Provenance(model_id="gemini-3.6-flash", temperature=TEMPERATURE, ts=T0)  # type: ignore[call-arg]


# --- The invariant: no field can carry a verdict --------------------------------------


def test_observation_has_no_verdict_shaped_field():
    """Property: there is no field for what the challenge box says there is no field for.

    KAR-412's public challenge answers *"there is no field for what you asked for."* This
    test is what makes that sentence checkable rather than rhetorical. If someone adds
    `score` to the observation schema, this fails — before the claim reaches a judge.
    """
    present = Observation.banned_fields_present()
    assert present == set(), f"verdict-shaped field(s) on the observation schema: {sorted(present)}"


def test_observation_rejects_extra_fields():
    """Property: the absence cannot be routed around at runtime.

    Without `extra="forbid"`, a caller could attach `score=0.8` to an observation and the
    schema would accept it — and every downstream consumer would then have a number to sort
    by. The structural claim depends on this setting.
    """
    with pytest.raises(ValidationError):
        Observation(**_base(score=0.8))


@pytest.mark.parametrize("field_name", sorted(BANNED_FIELD_NAMES))
def test_each_banned_field_name_is_rejected_individually(field_name):
    """Property: every name on the banned list is actually rejected.

    Parametrised so the failure names the specific field rather than reporting that "a test
    failed", and so the banned list cannot silently become decorative.
    """
    with pytest.raises(ValidationError):
        Observation(**_base(**{field_name: 1}))


def test_no_evidence_requires_search_notes():
    """Property: a finding of absence says what was searched.

    `search_notes` is a claim about the search — "scanned all registered spans, located
    nothing" — and never about the work. The distinction is the difference between reporting
    what Karani did and passing judgement on the student.
    """
    with pytest.raises(ValidationError, match="search_notes"):
        Observation(**_base(kind="no_evidence", citation=None, search_notes=None))


def test_no_evidence_cannot_carry_a_citation():
    """Property: the XOR holds in both directions.

    A `no_evidence` record that could carry a citation could be retried into one, which
    would defeat the exclusion that makes the attempt cap survivable.
    """
    rendition, registry = demo_rendition()
    from karani.validate.citation import build_citation

    citation = build_citation(
        span_id="sp-0000",
        quote="The author opens by narrowing the question to a single decade.",
        registry=registry,
        rendition_text=rendition.text,
    )
    with pytest.raises(ValidationError, match="must not carry a citation"):
        Observation(**_base(kind="no_evidence", citation=citation, search_notes="none found"))


# --- Renditions and spans --------------------------------------------------------------


def test_identical_content_yields_an_identical_rendition_id():
    """Property (KAR-304): the same content through the same pipeline is the same artifact."""
    assert compute_rendition_id("hello world", "md1") == compute_rendition_id("hello world", "md1")


def test_different_extractor_version_yields_a_different_rendition_id():
    """Property: an extractor change produces a visibly different artifact.

    Whitespace handling changes between parser versions. If the version did not participate
    in the identity, the same ID would silently cover subtly different text and every stored
    offset would be suspect without anything announcing it.
    """
    assert compute_rendition_id("hello world", "md1") != compute_rendition_id("hello world", "pdf1")


def test_every_span_hash_matches_the_rendition_slice():
    """Property (KAR-305): the registry and the rendition agree, span by span.

    Checked exhaustively rather than sampled. A single disagreeing span is a citation that
    resolves to text the model never saw.
    """
    rendition, registry = demo_rendition()
    assert registry.spans, "empty registry"
    for span in registry.spans.values():
        assert span.verify_against(rendition.text), f"{span.span_id} does not match its slice"


def test_interleaved_text_names_every_span_the_model_may_cite():
    """Property: the closed vocabulary is visible in the prompt the model actually receives.

    The model is told it may cite only IDs present in its input. That instruction is only
    enforceable if every citable ID is in fact present.
    """
    rendition, registry = demo_rendition()
    interleaved = registry.interleaved_text(rendition.text)
    for span_id in registry.spans:
        assert f"[[{span_id}]]" in interleaved


def test_empty_span_is_rejected():
    """Property: a span with no extent is not citable."""
    from karani.canon import sha256_text
    from karani.schema.spans import Span

    with pytest.raises(ValidationError):
        Span(
            span_id="sp-0000",
            rendition_id="r",
            doc_id="d",
            para_index=0,
            char_start=10,
            char_end=10,
            sha256=sha256_text(""),
        )


def test_span_registry_skips_empty_paragraphs():
    """Property: blank lines do not become citation targets."""
    text = "First paragraph.\n\n\n\nSecond paragraph."
    registry = SpanRegistry.build("r", "d", text, [(0, 16), (17, 17), (20, 37)])
    assert all(s.char_end > s.char_start for s in registry.spans.values())


def test_provenance_records_temperature_zero():
    """Property (KAR-301): temperature is recorded, and it is zero.

    Recorded on the record itself rather than in a config file, because a run's provenance
    has to travel with the observation it describes — a config file states what the
    temperature is *now*, not what it was when this observation was drafted.
    """
    obs = Observation(**_base(citation=None, kind="no_evidence", search_notes="none"))
    assert obs.provenance.temperature == 0.0


def test_created_at_is_timezone_aware():
    """Property: timestamps are comparable.

    Naive datetimes and ISO string sorting have both produced real ordering bugs in sibling
    systems. Every timestamp here carries an offset so comparisons are on instants.
    """
    obs = Observation(**_base(citation=None, kind="no_evidence", search_notes="none"))
    assert obs.created_at.tzinfo is not None
    assert obs.created_at.utcoffset() is not None
    assert datetime.now(UTC) > obs.created_at
