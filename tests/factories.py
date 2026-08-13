"""Deterministic builders for tests and for the committed golden log.

Nothing here uses randomness, wall-clock time, or the environment. Two calls produce
byte-identical output, in this process or another one, which is what lets the replay test
compare snapshots rather than compare shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from karani.canon import sha256_text
from karani.config import MODEL_ANALYSIS, PROMPT_VERSION, TEMPERATURE
from karani.schema.events import Event, Step
from karani.schema.observation import Citation, Observation, Provenance, Verification
from karani.schema.rendition import Rendition
from karani.schema.spans import SpanRegistry
from karani.validate.citation import build_citation

# A fixed instant. Timestamps must not vary between runs or the snapshot comparison would be
# testing the clock. Real runs stamp real times; `render()` never reads them for ordering.
T0 = datetime(2026, 8, 12, 3, 0, 0, tzinfo=UTC)

# The phrase planted in two different paragraphs, with genuinely different surroundings.
# This is what makes the misattribution test a *positional* test rather than a lexical one:
# containment cannot separate the two occurrences, and context can.
SHARED_PHRASE = "the evidence does not support this reading"

_FILLER = [
    "The author opens by narrowing the question to a single decade.",
    "That framing is defensible, though it leaves the earlier period unexamined.",
    "A second source is introduced without being situated against the first.",
    "The transition here is abrupt, and the reader is left to infer the connection.",
    "Two statistics appear in this paragraph; only one is attributed.",
    "The argument recovers its footing by returning to the central claim.",
    "An illustrative case is offered, drawn from a municipal record.",
    "The case is apt, but its scale is not comparable to the claim it supports.",
    "A concession is made and then immediately withdrawn.",
    "The paragraph closes on a rhetorical question that is never answered.",
    "Here the prose becomes noticeably more confident.",
]


def demo_rendition() -> tuple[Rendition, SpanRegistry]:
    """A 50-paragraph rendition in which paragraphs 12 and 47 share a phrase.

    Paragraph indices are stable, so `sp-0012` and `sp-0047` are the same spans the PRD's
    misattribution fixture names.
    """
    paras: list[str] = []
    for i in range(50):
        if i == 12:
            paras.append(
                "Turning to the first counterargument, the author concedes that "
                f"{SHARED_PHRASE} on the question of municipal funding, and moves on."
            )
        elif i == 47:
            paras.append(
                "In the conclusion the author reverses position, insisting that "
                f"{SHARED_PHRASE} anywhere in the record, which overstates the case."
            )
        else:
            paras.append(_FILLER[i % len(_FILLER)])

    text = "\n\n".join(paras)

    offsets: list[tuple[int, int]] = []
    cursor = 0
    for para in paras:
        offsets.append((cursor, cursor + len(para)))
        cursor += len(para) + 2  # the "\n\n" separator

    rendition = Rendition.freeze(
        doc_id="doc-demo",
        student_id="s01",
        text=text,
        paragraphs=offsets,
        source_projection="text",
        source_filename="s01.md",
        source_kind="md",
    )
    registry = SpanRegistry.build(rendition.rendition_id, rendition.doc_id, text, offsets)
    return rendition, registry


def provenance(model_id: str = MODEL_ANALYSIS) -> Provenance:
    return Provenance(
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        temperature=TEMPERATURE,
        ts=T0,
    )


def evidence_observation(
    *,
    observation_id: str,
    student_id: str,
    criterion_id: str,
    span_id: str,
    quote: str,
    registry: SpanRegistry,
    rendition_text: str,
    run_id: str = "run-golden",
    attempts: int = 1,
    text: str = "The submission addresses this criterion in the cited passage.",
) -> Observation:
    return Observation(
        observation_id=observation_id,
        run_id=run_id,
        student_id=student_id,
        criterion_id=criterion_id,
        kind="evidence",
        text=text,
        citation=build_citation(
            span_id=span_id, quote=quote, registry=registry, rendition_text=rendition_text
        ),
        provenance=provenance(),
        verification=Verification(referential=True, quote_check=True, positional=True),
        attempts=attempts,
        created_at=T0,
    )


def no_evidence_observation(
    *,
    observation_id: str,
    student_id: str,
    criterion_id: str,
    run_id: str = "run-golden",
) -> Observation:
    return Observation(
        observation_id=observation_id,
        run_id=run_id,
        student_id=student_id,
        criterion_id=criterion_id,
        kind="no_evidence",
        text="No passage addressing this criterion was located in the submission.",
        # A claim about the search, never about the work. See observation.search_notes.
        search_notes=(
            "Scanned all 50 registered spans for material addressing this criterion; "
            "no passage was located."
        ),
        provenance=provenance(),
        attempts=1,
        created_at=T0,
    )


def misattributed_citation(registry: SpanRegistry, rendition_text: str) -> Citation:
    """The PRD's misattribution fixture, constructed exactly.

    A real quote taken from span 12 — carrying span 12's true surrounding context — but
    attributed to span 47, where the same phrase genuinely occurs. Referential membership
    passes. Quote containment passes. Only positional identity can reject this.
    """
    honest = build_citation(
        span_id="sp-0012", quote=SHARED_PHRASE, registry=registry, rendition_text=rendition_text
    )
    return Citation(
        span_id="sp-0047",
        quote=honest.quote,
        quote_hash=honest.quote_hash,
        prefix=honest.prefix,
        suffix=honest.suffix,
    )


def golden_events(run_id: str = "run-golden") -> list[Event]:
    """One run exercising all six terminal outcomes of PRD §1.2.

    The point of the golden log is that the divergence is visible in a single run: six
    different consequences, not six labels on identical output.
    """
    rendition, registry = demo_rendition()
    text = rendition.text
    quote_12 = SHARED_PHRASE
    quote_47 = "which overstates the case"
    quote_intro = "The author opens by narrowing the question to a single decade."

    events: list[Event] = [
        Event.build(run_id=run_id, step=Step.RUN_STARTED, item_id=run_id, ts=T0,
                    payload={"submissions": 6}),
    ]

    def ingest(sid: str, projection: str = "text") -> None:
        events.append(
            Event.build(
                run_id=run_id, step=Step.SUBMISSION_INGESTED, item_id=sid, ts=T0,
                payload={"student_id": sid, "source_projection": projection},
            )
        )
        events.append(
            Event.build(
                run_id=run_id, step=Step.RENDITION_FROZEN, item_id=sid, ts=T0,
                payload={"student_id": sid, "rendition_id": rendition.rendition_id},
            )
        )

    for sid in ("s01", "s02", "s03", "s07", "s12", "s13"):
        ingest(sid)

    # --- 1. accepted on the first attempt --------------------------------------------
    o1 = evidence_observation(
        observation_id="obs-s01-c1", student_id="s01", criterion_id="c1",
        span_id="sp-0000", quote=quote_intro, registry=registry, rendition_text=text,
        run_id=run_id,
    )
    events.append(Event.build(run_id=run_id, step=Step.OBSERVATION_ACCEPTED,
                              item_id="s01::c1", ts=T0, attempt=1,
                              payload={"student_id": "s01", "observation": o1.model_dump(mode="json")}))

    # --- 2. accepted after a bounded retry -------------------------------------------
    events.append(Event.build(run_id=run_id, step=Step.OBSERVATION_REJECTED,
                              item_id="s02::c2", ts=T0, attempt=1,
                              payload={"student_id": "s02", "criterion_id": "c2",
                                       "failed_layer": "positional",
                                       "reason": "quote occurs in the span but not at the cited location"}))
    o2 = evidence_observation(
        observation_id="obs-s02-c2", student_id="s02", criterion_id="c2",
        span_id="sp-0047", quote=quote_47, registry=registry, rendition_text=text,
        run_id=run_id, attempts=2,
    )
    events.append(Event.build(run_id=run_id, step=Step.OBSERVATION_ACCEPTED,
                              item_id="s02::c2", ts=T0, attempt=2,
                              payload={"student_id": "s02", "observation": o2.model_dump(mode="json")}))

    # --- 3. NEEDS_HUMAN via entailment disagreement -----------------------------------
    o3 = evidence_observation(
        observation_id="obs-s03-c3", student_id="s03", criterion_id="c3",
        span_id="sp-0012", quote=quote_12, registry=registry, rendition_text=text,
        run_id=run_id,
    )
    events.append(Event.build(run_id=run_id, step=Step.OBSERVATION_DRAFTED,
                              item_id="s03::c3", ts=T0, attempt=1,
                              payload={"student_id": "s03", "observation": o3.model_dump(mode="json")}))
    events.append(Event.build(run_id=run_id, step=Step.NEEDS_HUMAN_REVIEW,
                              item_id="s03::c3", ts=T0, attempt=1,
                              payload={"student_id": "s03", "criterion_id": "c3",
                                       "observation_id": "obs-s03-c3",
                                       "anomaly_kind": "entailment_disagreement",
                                       "reason": "the cited span does not entail the drafted claim; "
                                                 "routed to review without a regeneration attempt"}))

    # --- 4. no_evidence, first-class and never retried --------------------------------
    o4 = no_evidence_observation(observation_id="obs-s12-c4", student_id="s12",
                                 criterion_id="c4", run_id=run_id)
    events.append(Event.build(run_id=run_id, step=Step.NO_EVIDENCE_RECORDED,
                              item_id="s12::c4", ts=T0, attempt=1,
                              payload={"student_id": "s12", "observation": o4.model_dump(mode="json")}))

    # --- 5. injection detected; analysis proceeds anyway -------------------------------
    events.append(Event.build(run_id=run_id, step=Step.ARMOR_SCANNED, item_id="s07", ts=T0,
                              payload={"student_id": "s07", "scanned_bytes": len(text)}))
    events.append(Event.build(run_id=run_id, step=Step.INJECTION_DETECTED, item_id="s07", ts=T0,
                              payload={"student_id": "s07", "span_id": "sp-0009",
                                       "detail": "instruction-shaped text in a footnote directed at the "
                                                 "reader of the submission rather than at a human grader"}))
    o5 = evidence_observation(
        observation_id="obs-s07-c1", student_id="s07", criterion_id="c1",
        span_id="sp-0000", quote=quote_intro, registry=registry, rendition_text=text,
        run_id=run_id,
    )
    events.append(Event.build(run_id=run_id, step=Step.OBSERVATION_ACCEPTED,
                              item_id="s07::c1", ts=T0, attempt=1,
                              payload={"student_id": "s07", "observation": o5.model_dump(mode="json")}))

    # --- 6. abandoned; the run completes around it -------------------------------------
    events.append(Event.build(run_id=run_id, step=Step.TASK_ABANDONED, item_id="s13", ts=T0,
                              payload={"student_id": "s13", "reason": "join_timeout"}))

    events.append(Event.build(run_id=run_id, step=Step.RENDER_COMPLETED, item_id=run_id, ts=T0,
                              payload={"sheets": 6}))
    return events


def golden_log_jsonl(run_id: str = "run-golden") -> str:
    return "".join(e.model_dump_json() + "\n" for e in golden_events(run_id))


def stable_digest(payload: str) -> str:
    return sha256_text(payload)
