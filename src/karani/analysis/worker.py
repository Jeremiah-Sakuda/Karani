"""The analyst worker and the validation gate (KAR-306, KAR-307, KAR-308, KAR-310).

One worker handles one submission end to end and emits events as it goes. The gate is a
small state machine with exactly three exits, and which exit a unit takes is the whole
autonomy story:

    accept            -> ObservationAccepted
    reject (<= 2)     -> ObservationRejected, then one more attempt for that observation only
    NEEDS_HUMAN       -> attempt cap reached, or an entailment disagreement at any attempt

Three decisions here are worth reading closely.

**Retry granularity is the observation, not the submission.** When one of five criteria fails
validation, only that one is resubmitted. Regenerating the whole submission would discard four
observations that already passed and spend the attempt budget re-deriving them — and, worse,
would make the accepted observations non-reproducible, since the second pass could word them
differently.

**`no_evidence` never enters the retry loop.** Absence is a finding. Retrying it would ask a
model that just reported finding nothing to go and find something, with a countdown attached.
That is a fabrication generator. Excluding absence from retry is what makes an attempt cap of
two survivable rather than coercive.

**An entailment disagreement escalates immediately, at any attempt.** See
`karani.validate.entailment` for why: a mechanical error is worth telling a model about, and a
disagreement about meaning is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from karani.analysis.cache import CacheKey, ResponseCache
from karani.analysis.client import ModelClient
from karani.analysis.prompts import (
    ANALYSIS_SYSTEM,
    Criterion,
    build_analysis_prompt,
    prompt_fingerprint,
)
from karani.armor.scan import Scanner, attribute_to_spans
from karani.canon import sha256_text
from karani.config import MAX_ATTEMPTS, MODEL_ANALYSIS, PROMPT_VERSION, TEMPERATURE
from karani.ingest.freeze import FrozenSubmission
from karani.schema.events import Event, Step
from karani.schema.observation import Citation, Observation, Provenance, Verification
from karani.schema.rendition import Rendition
from karani.triage.gemma import triage
from karani.validate.citation import validate_citation
from karani.validate.entailment import check_entailment


class MalformedModelOutput(ValueError):
    """The model's JSON could not be parsed into observations."""


@dataclass
class WorkerOutcome:
    student_id: str
    events: list[Event] = field(default_factory=list)
    accepted: list[Observation] = field(default_factory=list)
    needs_human: list[Observation] = field(default_factory=list)
    no_evidence: list[Observation] = field(default_factory=list)
    injection_detected: bool = False
    attempts_used: int = 0
    model_calls: int = 0
    cached_calls: int = 0


def analyze_submission(
    *,
    frozen: FrozenSubmission,
    criteria: list[Criterion],
    run_id: str,
    client: ModelClient,
    cache: ResponseCache,
    scanner: Scanner,
    project: str = "",
    now: datetime | None = None,
) -> WorkerOutcome:
    ts = now or datetime.now(UTC)
    ref, rendition, registry = frozen.ref, frozen.rendition, frozen.registry
    outcome = WorkerOutcome(student_id=ref.student_id)

    outcome.events.append(
        Event.build(
            run_id=run_id,
            step=Step.SUBMISSION_INGESTED,
            item_id=ref.student_id,
            ts=ts,
            payload={
                "student_id": ref.student_id,
                "source_filename": ref.filename,
                "source_projection": rendition.source_projection,
            },
        )
    )
    outcome.events.append(
        Event.build(
            run_id=run_id,
            step=Step.RENDITION_FROZEN,
            item_id=ref.student_id,
            ts=ts,
            payload={
                "student_id": ref.student_id,
                "rendition_id": rendition.rendition_id,
                "span_count": len(registry.spans),
                "source_projection": rendition.source_projection,
                "anchor_capability": rendition.anchor_capability,
                # The frozen text and its span map travel *in the event*, which costs a few
                # kilobytes per submission and buys the invariant outright: the docket's
                # click-to-locus viewer renders from the log and nothing else. If the text
                # lived in a side table, "one append-only log drives every artifact" would
                # be true of the evidence sheets and false of the thing the instructor
                # actually looks at when deciding whether a citation is fair.
                "text": rendition.text,
                "spans": {
                    span_id: [span.char_start, span.char_end]
                    for span_id, span in registry.spans.items()
                },
            },
        )
    )

    # --- triage (KAR-315) --------------------------------------------------------------
    # Gemma when it is available, deterministic heuristics under their own name when it is
    # not. Which tier answered is recorded on the event rather than inferred from config, so
    # the log cannot claim Gemma ran when the fallback did.
    decision = triage(rendition.text, project=project)
    outcome.events.append(
        Event.build(
            run_id=run_id,
            step=Step.TRIAGE_DECIDED,
            item_id=ref.student_id,
            ts=ts,
            payload={
                "student_id": ref.student_id,
                "kind": decision.kind,
                "text_tier": decision.text_tier,
                "language": decision.language,
                "reason": decision.reason,
                "decided_by": decision.decided_by,
                "gemma_available": decision.gemma_available,
            },
        )
    )
    if not decision.should_analyze:
        # Course material rather than student work. Recorded as a routing decision, not as a
        # failure -- nobody's submission went wrong here.
        outcome.events.append(
            Event.build(
                run_id=run_id,
                step=Step.TASK_FAILED,
                item_id=ref.student_id,
                ts=ts,
                payload={
                    "student_id": ref.student_id,
                    "stage": "triage",
                    "reason": f"not a submission ({decision.reason}); "
                    f"classified by {decision.decided_by}",
                },
            )
        )
        return outcome

    # --- injection scan on post-extraction bytes -------------------------------------
    # The scan target is exactly the rendition text the model is about to see. Scanning the
    # source file would miss a payload that only becomes text after extraction.
    scan = attribute_to_spans(scanner.scan(rendition.text), registry)
    outcome.events.append(
        Event.build(
            run_id=run_id,
            step=Step.ARMOR_SCANNED,
            item_id=ref.student_id,
            ts=ts,
            payload={
                "student_id": ref.student_id,
                "detector": scan.detector,
                "detector_available": scan.detector_available,
                "scanned_chars": len(rendition.text),
            },
        )
    )
    injection_spans: set[str] = set()
    if scan.detected:
        outcome.injection_detected = True
        injection_spans = {d.span_id for d in scan.detections if d.span_id}
        outcome.events.append(
            Event.build(
                run_id=run_id,
                step=Step.INJECTION_DETECTED,
                item_id=ref.student_id,
                ts=ts,
                payload={
                    "student_id": ref.student_id,
                    "detector": scan.detector,
                    "span_ids": sorted(injection_spans),
                    "patterns": sorted({d.pattern_name for d in scan.detections}),
                    "detail": (
                        "instruction-shaped text addressed to an automated reader; "
                        "flagged for the instructor and analysis proceeded"
                    ),
                },
            )
        )

    # --- the attempt loop -------------------------------------------------------------
    pending: list[Criterion] = list(criteria)
    feedback = ""
    settled: dict[str, Observation] = {}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not pending:
            break
        outcome.attempts_used = attempt

        key = CacheKey(
            rendition_id=rendition.rendition_id,
            prompt_version=f"{PROMPT_VERSION}-{prompt_fingerprint(criteria)}",
            model_id=MODEL_ANALYSIS,
            temperature=TEMPERATURE,
            attempt=attempt,
            feedback_hash=sha256_text(feedback)[:32] if feedback else "",
            criterion_scope=",".join(sorted(c.criterion_id for c in pending)),
        )
        response = client.generate(
            system=ANALYSIS_SYSTEM,
            prompt=build_analysis_prompt(
                interleaved_text=registry.interleaved_text(rendition.text),
                criteria=pending,
                feedback=feedback,
            ),
            model_id=MODEL_ANALYSIS,
            key=key,
        )
        outcome.model_calls += 1
        if response.cached:
            outcome.cached_calls += 1

        try:
            drafted = _parse_observations(
                response.text,
                run_id=run_id,
                student_id=ref.student_id,
                rendition=rendition,
                attempt=attempt,
                ts=ts,
                anchor_confidence=frozen.anchor_confidence,
            )
        except MalformedModelOutput as exc:
            outcome.events.append(
                Event.build(
                    run_id=run_id,
                    step=Step.TASK_FAILED,
                    item_id=ref.student_id,
                    ts=ts,
                    attempt=attempt,
                    payload={"student_id": ref.student_id, "stage": "analysis", "reason": str(exc)},
                )
            )
            break

        rejected: list[tuple[Observation, str]] = []

        for obs in drafted:
            item_id = f"{ref.student_id}::{obs.criterion_id}"

            # --- absence: recorded, never retried --------------------------------------
            if obs.kind == "no_evidence":
                settled[obs.criterion_id] = obs
                outcome.no_evidence.append(obs)
                outcome.events.append(
                    Event.build(
                        run_id=run_id,
                        step=Step.NO_EVIDENCE_RECORDED,
                        item_id=item_id,
                        ts=ts,
                        attempt=attempt,
                        payload={
                            "student_id": ref.student_id,
                            "observation": obs.model_dump(mode="json"),
                        },
                    )
                )
                continue

            outcome.events.append(
                Event.build(
                    run_id=run_id,
                    step=Step.OBSERVATION_DRAFTED,
                    item_id=item_id,
                    ts=ts,
                    attempt=attempt,
                    payload={
                        "student_id": ref.student_id,
                        "observation": obs.model_dump(mode="json"),
                    },
                )
            )

            # --- layers 1-3: deterministic ---------------------------------------------
            result = validate_citation(
                obs.citation,  # type: ignore[arg-type]
                registry=registry,
                rendition_text=rendition.text,
                anchor_confidence=obs.anchor_confidence,
            )
            if not result.ok:
                rejected.append((obs, result.rejection_reason))
                outcome.events.append(
                    Event.build(
                        run_id=run_id,
                        step=Step.OBSERVATION_REJECTED,
                        item_id=item_id,
                        ts=ts,
                        attempt=attempt,
                        payload={
                            "student_id": ref.student_id,
                            "criterion_id": obs.criterion_id,
                            "failed_layer": str(result.failed_layer),
                            "reason": result.feedback,
                        },
                    )
                )
                continue

            # --- layer 4: entailment ----------------------------------------------------
            span = registry.get(obs.citation.span_id)  # type: ignore[union-attr]
            assert span is not None  # layer 1 already proved membership
            entail = check_entailment(
                claim=obs.text,
                passage=span.text_from(rendition.text),
                submission=rendition.text,
                client=client,
                cache=cache,
                rendition_id=rendition.rendition_id,
            )
            verified = obs.model_copy(
                update={
                    "verification": Verification(
                        referential=result.verification.referential,
                        positional=result.verification.positional,
                        quote_check=result.verification.quote_check,
                        entailment=entail.supported,
                    )
                }
            )

            if entail.disagreement:
                # Straight to review. Never retried -- see the module docstring.
                escalated = verified.model_copy(
                    update={"needs_human": True, "needs_human_reason": entail.reason}
                )
                settled[obs.criterion_id] = escalated
                outcome.needs_human.append(escalated)
                outcome.events.append(
                    Event.build(
                        run_id=run_id,
                        step=Step.NEEDS_HUMAN_REVIEW,
                        item_id=item_id,
                        ts=ts,
                        attempt=attempt,
                        payload={
                            "student_id": ref.student_id,
                            "criterion_id": obs.criterion_id,
                            "observation_id": obs.observation_id,
                            "anomaly_kind": "entailment_disagreement",
                            "reason": entail.reason,
                            # The VERIFIED observation, not just its ID.
                            #
                            # Without it the fold promotes the raw draft and the escalated
                            # observation renders with every verification field null -- which
                            # reads as "nothing was checked" when in fact three layers passed
                            # and only entailment failed. That is exactly the information the
                            # instructor needs in order to judge the escalation: this citation
                            # is real, quoted correctly, and in the right place, and the
                            # disagreement is about what the passage means.
                            "observation": escalated.model_dump(mode="json"),
                        },
                    )
                )
                continue

            settled[obs.criterion_id] = verified
            outcome.accepted.append(verified)
            outcome.events.append(
                Event.build(
                    run_id=run_id,
                    step=Step.OBSERVATION_ACCEPTED,
                    item_id=item_id,
                    ts=ts,
                    attempt=attempt,
                    payload={
                        "student_id": ref.student_id,
                        "observation": verified.model_dump(mode="json"),
                    },
                )
            )

        # Only the criteria that failed go around again.
        failed_ids = {obs.criterion_id for obs, _ in rejected}
        pending = [c for c in criteria if c.criterion_id in failed_ids]
        feedback = "\n".join(f"- {obs.criterion_id}: {reason}" for obs, reason in rejected)

    # --- attempt cap reached -----------------------------------------------------------
    for criterion in pending:
        item_id = f"{ref.student_id}::{criterion.criterion_id}"
        outcome.events.append(
            Event.build(
                run_id=run_id,
                step=Step.NEEDS_HUMAN_REVIEW,
                item_id=item_id,
                ts=ts,
                attempt=MAX_ATTEMPTS,
                payload={
                    "student_id": ref.student_id,
                    "criterion_id": criterion.criterion_id,
                    # Must match the ID minted in _parse_observations, which carries the
                    # attempt suffix. Without it the escalation names an observation that
                    # does not exist, the fold cannot bind `needs_human` to anything, and the
                    # anomaly queue shows an item pointing at nothing — the instructor is told
                    # something needs review and given no way to see what.
                    "observation_id": (
                        f"obs-{ref.student_id}-{criterion.criterion_id}-a{MAX_ATTEMPTS}"
                    ),
                    "anomaly_kind": "attempt_cap_reached",
                    "reason": (
                        f"citation validation failed on {MAX_ATTEMPTS} attempts; "
                        f"escalated rather than accepted or retried further"
                    ),
                },
            )
        )

    return outcome


def _parse_observations(
    raw: str,
    *,
    run_id: str,
    student_id: str,
    rendition: Rendition,
    attempt: int,
    ts: datetime,
    anchor_confidence: str,
) -> list[Observation]:
    """Turn the model's JSON into validated `Observation` records.

    Anything malformed raises rather than being patched up. A repaired observation is one
    whose content was partly decided by the repair code, and its `provenance{}` would then
    describe a model that did not produce it.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MalformedModelOutput(f"model output was not valid JSON: {exc}") from exc

    items = payload.get("observations")
    if not isinstance(items, list):
        raise MalformedModelOutput("model output has no 'observations' array")

    provenance = Provenance(
        model_id=MODEL_ANALYSIS,
        prompt_version=PROMPT_VERSION,
        temperature=TEMPERATURE,
        ts=ts,
    )

    observations: list[Observation] = []
    for item in items:
        if not isinstance(item, dict) or "criterion_id" not in item:
            raise MalformedModelOutput(f"malformed observation entry: {item!r}")

        criterion_id = str(item["criterion_id"])
        kind = str(item.get("kind", "evidence"))
        citation = None

        if kind == "evidence":
            raw_citation = item.get("citation")
            if not isinstance(raw_citation, dict):
                raise MalformedModelOutput(
                    f"{criterion_id}: kind 'evidence' with no citation object"
                )
            quote = str(raw_citation.get("quote", ""))
            if not quote:
                raise MalformedModelOutput(f"{criterion_id}: citation with an empty quote")
            citation = Citation(
                span_id=str(raw_citation.get("span_id", "")),
                quote=quote,
                # Computed from the quote, not accepted from the model: the hash is an
                # integrity check on transport and storage, and a model-supplied hash would
                # only ever confirm the model agreed with itself.
                quote_hash=sha256_text(quote),
                prefix=str(raw_citation.get("prefix", "")),
                suffix=str(raw_citation.get("suffix", "")),
            )

        observations.append(
            Observation(
                observation_id=f"obs-{student_id}-{criterion_id}-a{attempt}",
                run_id=run_id,
                student_id=student_id,
                criterion_id=criterion_id,
                kind=kind,  # type: ignore[arg-type]
                text=str(item.get("text", "")),
                citation=citation,
                search_notes=(
                    str(item.get("search_notes") or "no search notes recorded")
                    if kind == "no_evidence"
                    else None
                ),
                anchor_confidence=anchor_confidence,  # type: ignore[arg-type]
                provenance=provenance,
                attempts=attempt,
                created_at=ts,
                source_projection=rendition.source_projection,
            )
        )

    return observations
