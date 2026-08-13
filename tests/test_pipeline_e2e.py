"""End-to-end: the full pipeline over the real fixtures, and the six terminal outcomes.

**About the stand-in model.** These tests use `ScriptedAnalyst`, and it is named for what it
is. It is not a simulation of Gemini and makes no claim to behave like one; it is a scripted
source of well-formed and deliberately malformed model output, used to drive the pipeline's
control flow deterministically and for free.

The important design choice: it reads span IDs and passage text **out of the prompt it was
handed**, exactly as a model must. It has no back-channel to the registry. So if the prompt
ever stopped interleaving span IDs into the rendition text, this stand-in would start
producing uncitable observations and these tests would fail — which makes them a real test of
the prompt contract, not just of the code beneath it.

This is also why `make demo` is *not* allowed to do this. A test may use a fake and say so; a
demo that fabricated model output would be a different system from the one in the video.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from karani.analysis.cache import CacheKey, ResponseCache
from karani.analysis.client import ModelResponse
from karani.analysis.dispatcher import run_pipeline
from karani.analysis.prompts import Criterion
from karani.armor.scan import LocalPatternScanner
from karani.config import CONTEXT_CHARS
from karani.ingest.source import LocalSource
from karani.render import render
from karani.store.local import LocalEventStore

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

CRITERIA = [
    Criterion("c1", "Thesis", "A position is stated and governs the essay."),
    Criterion("c2", "Evidence", "Sources are introduced, quoted, cited, and connected."),
    Criterion("c3", "Organization", "Paragraphs follow a trackable order."),
    Criterion("c4", "Counterarguments", "An objection is stated and responded to."),
    Criterion("c5", "Mechanics", "Sentence boundaries and punctuation are handled."),
]

SPAN_RE = re.compile(r"\[\[(sp-\d{4})\]\]\s*(.*?)(?=\n\n\[\[sp-|\Z)", re.DOTALL)


class ScriptedAnalyst:
    """Deterministic, scripted model output. Reads spans from the prompt, as a model must."""

    backend = "scripted"

    def __init__(self, cache: ResponseCache, *, plan: dict[str, str] | None = None) -> None:
        self.cache = cache
        # criterion_id -> behaviour. Default is an honest, citable observation.
        self.plan = plan or {}
        self.calls = 0

    def generate(self, *, system: str, prompt: str, model_id: str, key: CacheKey) -> ModelResponse:
        self.calls += 1

        if key.criterion_scope == "entailment":
            # The entailment tier. "unsupported" appears only where the plan asks for a
            # disagreement, so the escalation path is exercised without being ambient.
            unsupported = "ENTAIL_FAIL" in prompt
            return ModelResponse(
                text=json.dumps({"supported": not unsupported,
                                 "reason": "scripted entailment verdict"}),
                model_id=model_id, cached=False,
            )

        spans = SPAN_RE.findall(prompt)
        assert spans, "the prompt carried no [[sp-NNNN]] markers; the span contract is broken"

        requested = [c for c in key.criterion_scope.split(",") if c]
        observations = []

        for index, criterion_id in enumerate(requested):
            behaviour = self.plan.get(criterion_id, "cite")
            span_id, span_text = spans[index % len(spans)]
            span_text = span_text.strip()

            if behaviour == "no_evidence":
                observations.append({
                    "criterion_id": criterion_id, "kind": "no_evidence",
                    "text": "No passage addressing this criterion was located.",
                    "search_notes": f"Scanned {len(spans)} registered spans; none addressed it.",
                })
                continue

            if behaviour == "fabricate_span":
                observations.append({
                    "criterion_id": criterion_id, "kind": "evidence",
                    "text": "The submission addresses this criterion.",
                    "citation": {"span_id": "sp-9999", "quote": "invented",
                                 "prefix": "", "suffix": ""},
                })
                continue

            # An honest citation: quote a real sentence and report the context around it the
            # way the prompt instructs -- bounded by the span, never reading across into a
            # neighbour and never including a [[sp-NNNN]] marker.
            sentence = _first_sentence(span_text)
            at = span_text.find(sentence)
            prefix = span_text[max(0, at - CONTEXT_CHARS):at]
            suffix = span_text[at + len(sentence):at + len(sentence) + CONTEXT_CHARS]

            if behaviour == "misattribute" and len(spans) > 1:
                # Same quote and context, wrong span. Layers 1 and 2 pass; only positional
                # identity can reject it.
                other = spans[(index + 1) % len(spans)][0]
                observations.append({
                    "criterion_id": criterion_id, "kind": "evidence",
                    "text": "The submission addresses this criterion in the cited passage.",
                    "citation": {"span_id": other, "quote": sentence,
                                 "prefix": prefix, "suffix": suffix},
                })
                continue

            text = "The submission addresses this criterion in the cited passage."
            if behaviour == "entail_fail":
                text = "ENTAIL_FAIL the cited passage does something it does not do."

            observations.append({
                "criterion_id": criterion_id, "kind": "evidence", "text": text,
                "citation": {"span_id": span_id, "quote": sentence,
                             "prefix": prefix, "suffix": suffix},
            })

        return ModelResponse(text=json.dumps({"observations": observations}),
                             model_id=model_id, cached=False)


def _first_sentence(text: str) -> str:
    match = re.search(r"[^.!?]{25,180}[.!?]", text)
    return match.group(0).strip() if match else text[:120].strip()


def _run(tmp_path: Path, source_dir: Path, plan: dict[str, str] | None = None):
    store = LocalEventStore(tmp_path / "store")
    cache = ResponseCache(tmp_path / "cache")
    summary = run_pipeline(
        run_id="run-test",
        source=LocalSource(source_dir),
        criteria=CRITERIA,
        store=store,
        client=ScriptedAnalyst(cache, plan=plan),
        cache=cache,
        scanner=LocalPatternScanner(),
        max_workers=4,
    )
    return summary, render("run-test", store.read_run("run-test")), store


def test_full_corpus_run_completes_and_routes_every_submission(tmp_path):
    """Property: every dispatched unit reaches a terminal state. None is left hanging.

    The unparseable fixture is the interesting one: it must land in `failed`, not silently
    become a submission with nothing in it.
    """
    summary, rendered, _ = _run(tmp_path, FIXTURES, plan={"c4": "no_evidence"})

    assert len(summary.dispatched) == 16, f"expected 16 submissions, got {sorted(summary.dispatched)}"
    accounted = set(summary.completed) | set(summary.failed) | set(summary.abandoned)
    assert accounted == set(summary.dispatched), "a dispatched unit reached no terminal state"
    assert "s16" in summary.failed, "the unparseable fixture did not fail visibly"
    assert not summary.aborted


def test_unparseable_submission_fails_visibly_rather_than_rendering_empty(tmp_path):
    """Property: a file that cannot be opened is a failure, never a finding of absence.

    This is the difference between "Karani could not read this" and "this student submitted
    nothing relevant." The second is a confident wrong answer about a person's work.
    """
    _, rendered, _ = _run(tmp_path, FIXTURES, plan={"c4": "no_evidence"})

    parse_failures = [a for a in rendered.anomalies if a.kind == "parse_failure"]
    assert parse_failures, "no parse_failure anomaly for the corrupt PDF"
    assert parse_failures[0].student_id == "s16"

    s16_sheet = next((s for s in rendered.sheets if s.student_id == "s16"), None)
    assert s16_sheet is None or not s16_sheet.observations, (
        "the unparseable submission produced observations"
    )


def test_injection_is_flagged_and_analysis_proceeds(tmp_path):
    """Property (KAR-311): a flagged submission is still analysed.

    Both halves are asserted. The flag must appear — and the observations must appear too. A
    system that flagged and then refused would penalise a student for a file whose footnote
    they may not have written.
    """
    _, rendered, _ = _run(tmp_path, FIXTURES / "dev", plan={"c4": "no_evidence"})

    s07 = next(s for s in rendered.sheets if s.student_id == "s07")
    assert s07.injection_flagged, "s07's planted injection was not detected"
    assert s07.observations, "analysis did not proceed for the flagged submission"

    injections = [a for a in rendered.anomalies if a.kind == "injection_detected"]
    assert injections and injections[0].student_id == "s07"


def test_no_evidence_is_recorded_once_and_never_retried(tmp_path):
    """Property (KAR-308): absence is a finding, not a failure to find.

    Asserted by counting events, not by reading a status. A `no_evidence` observation that
    had entered the retry loop would show a second attempt in the log even if its final state
    looked identical.
    """
    _, rendered, store = _run(tmp_path, FIXTURES / "dev", plan={"c4": "no_evidence"})

    events = store.read_run("run-test")
    no_evidence = [e for e in events if e.step.value == "NoEvidenceRecorded"]
    assert no_evidence, "no no_evidence observations were produced"
    assert all(e.attempt == 1 for e in no_evidence), "a no_evidence observation was retried"

    # And it never appears as a rejection, which is the other way it could have been retried.
    rejected_criteria = {
        e.payload.get("criterion_id") for e in events if e.step.value == "ObservationRejected"
    }
    assert "c4" not in rejected_criteria


def test_misattributed_citation_is_rejected_then_retried_then_escalated(tmp_path):
    """Property (KAR-307): exactly two attempts, then a human queue item.

    The stand-in misattributes persistently, so the gate cannot succeed. What is asserted is
    the *shape* of the failure: bounded retries at observation granularity, then escalation —
    never an unbounded loop, and never quiet acceptance of an invalid citation.
    """
    _, rendered, store = _run(tmp_path, FIXTURES / "dev", plan={"c2": "misattribute"})

    events = store.read_run("run-test")
    rejections = [e for e in events if e.step.value == "ObservationRejected"
                  and e.payload.get("criterion_id") == "c2"]
    assert rejections, "the misattributed citation was accepted"

    # Rejected at a citation layer -- which one depends on the document, and both are correct
    # answers to this input. Attributing a quote to an arbitrary other paragraph usually fails
    # at containment (layer 2), because the quote simply is not in that paragraph. The harder
    # case -- a phrase that genuinely occurs in *both* spans, where only positional identity
    # can separate them -- needs a document built for it, and is unit-tested against exactly
    # that fixture in test_citation_validator.py.
    layers = {e.payload.get("failed_layer") for e in rejections}
    assert layers <= {"quote_check", "positional"}, f"rejected at an unexpected layer: {layers}"

    attempts = {e.attempt for e in rejections}
    assert max(attempts) <= 2, f"more than two attempts were made: {sorted(attempts)}"

    escalated = [e for e in events if e.step.value == "NeedsHumanReview"
                 and e.payload.get("criterion_id") == "c2"]
    assert escalated, "the attempt cap did not produce a human-queue item"
    assert escalated[0].payload["anomaly_kind"] == "attempt_cap_reached"


def test_fabricated_span_is_rejected_at_the_referential_layer(tmp_path):
    """Property: an invented span ID fails set membership, the cheapest possible check."""
    _, _, store = _run(tmp_path, FIXTURES / "dev", plan={"c3": "fabricate_span"})

    rejections = [e for e in store.read_run("run-test")
                  if e.step.value == "ObservationRejected"
                  and e.payload.get("criterion_id") == "c3"]
    assert rejections
    assert rejections[0].payload["failed_layer"] == "referential"


def test_entailment_disagreement_escalates_without_a_retry(tmp_path):
    """Property (KAR-310): a disagreement about meaning is escalated, never retried.

    The distinction this asserts is the whole reason entailment is handled differently from
    the other layers. A mechanical failure gets a retry because telling the model what was
    wrong is actionable. A disagreement about what a passage means does not, because "try
    again" there is pressure to produce something that gets past the checker.
    """
    _, rendered, store = _run(tmp_path, FIXTURES / "dev", plan={"c5": "entail_fail"})

    events = store.read_run("run-test")
    escalated = [e for e in events if e.step.value == "NeedsHumanReview"
                 and e.payload.get("anomaly_kind") == "entailment_disagreement"]
    assert escalated, "no entailment disagreement was escalated"

    # The decisive assertion: it was never sent back for another attempt.
    retried = [e for e in events if e.step.value == "ObservationRejected"
               and e.payload.get("criterion_id") == "c5"]
    assert not retried, "an entailment disagreement was routed into the retry loop"

    disagreements = [a for a in rendered.anomalies if a.kind == "entailment_disagreement"]
    assert disagreements


def test_run_renders_from_the_log_alone(tmp_path):
    """Property: everything the docket shows is a fold over the events, including the text.

    The rendition travels in its event, so the click-to-locus viewer has the frozen text
    without a side table. If this fails, "one append-only log drives every artifact" is true
    of the evidence sheets and false of the thing an instructor actually reads.
    """
    _, rendered, _ = _run(tmp_path, FIXTURES / "dev", plan={"c4": "no_evidence"})

    assert rendered.renditions, "no rendition text reached the fold"
    for student_id, rendition in rendered.renditions.items():
        assert rendition["text"], f"{student_id} has an empty rendition"
        assert rendition["spans"], f"{student_id} has no span map"
        # Every cited span must be resolvable from what the fold carries.
        sheet = next(s for s in rendered.sheets if s.student_id == student_id)
        for obs in sheet.observations:
            citation = obs.get("citation")
            if citation:
                assert citation["span_id"] in rendition["spans"], (
                    f"{student_id}: cited span {citation['span_id']} is not in the rendered map"
                )


def test_rerun_over_identical_inputs_is_stable(tmp_path):
    """Property (KAR-316): two runs over identical fixtures produce the same observations.

    Compared on the claims projection rather than on the whole artifact, because run IDs and
    timestamps legitimately differ between runs. What must not differ is what Karani found.
    """
    _, first, _ = _run(tmp_path / "a", FIXTURES / "dev", plan={"c4": "no_evidence"})
    _, second, _ = _run(tmp_path / "b", FIXTURES / "dev", plan={"c4": "no_evidence"})

    def shape(rendered):
        return sorted(
            (c["student_id"], c["criterion_id"], c["kind"],
             (c.get("citation") or {}).get("span_id"))
            for c in rendered.claims
        )

    assert shape(first) == shape(second)


@pytest.mark.parametrize("outcome", ["accepted_first_attempt", "no_evidence", "needs_human"])
def test_one_unattended_run_produces_divergent_outcomes(tmp_path, outcome):
    """Property (§1.2): six different consequences from one run, not six labels on one output.

    This is the video's central claim (§8 beat 4), so it is asserted against a real run over
    the real fixtures rather than against a hand-built log.
    """
    _, rendered, _ = _run(
        tmp_path, FIXTURES, plan={"c4": "no_evidence", "c2": "misattribute"}
    )
    assert rendered.overview["terminal_outcomes"][outcome] >= 1


def test_injection_and_exclusion_outcomes_are_present_in_a_full_run(tmp_path):
    """The two outcomes that are not observation-shaped, from the same run."""
    _, rendered, _ = _run(tmp_path, FIXTURES, plan={"c4": "no_evidence"})

    assert any(s.injection_flagged for s in rendered.sheets)
    assert any(a.kind == "parse_failure" for a in rendered.anomalies)
