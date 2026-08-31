"""`render(run_id)` — a pure fold over the event stream, and the only writer of artifacts.

Three properties, and the code is arranged so that violating any of them is difficult rather
than merely discouraged.

**Pure.** The only input is a list of events. No store handle, no clock, no environment, no
network. The CI replay test runs this function with every Google credential variable
explicitly cleared and a *shuffled* log, and snapshot-compares the bytes. A fold that reached
for anything outside its argument would fail that test rather than pass it quietly.

**Sole writer.** Evidence sheets, the class overview, and the claims projection are produced
here and nowhere else. If a second writer existed, the log would stop being the thing the
artifacts are derived from and would become one of several sources that happen to agree — and
"happen to agree" is not a property you can test.

**Byte-stable under reordering.** The fold imposes its own total order, derived from event
content (see `STEP_RANK`), rather than trusting arrival order or timestamps. Parallel workers
routinely write in the same millisecond; an order broken by a timestamp tie would be an order
broken by chance.

There is no ordinal signal anywhere in the output. Students are ordered by student ID.
Criteria are ordered by criterion ID. Nothing is sorted by anything that could be read as
quality, because a list sorted by quality is a ranking whatever the column header says, and a
class overview that ranks students is a leaderboard with a different name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from karani.canon import canonical_json, sha256_text
from karani.config import INSUFFICIENT_THRESHOLD
from karani.schema.events import Event, Step

# The six terminal outcomes of PRD §1.2. Every unit of work ends in exactly one, and each
# has a visibly different downstream consequence. This is the autonomy claim: six different
# consequences from one unattended run, not six labels on identical output.
TERMINAL_OUTCOMES = (
    "accepted_first_attempt",
    "accepted_after_retry",
    "needs_human",
    "no_evidence",
    "injection_detected",
    "abandoned",
)


@dataclass
class EvidenceSheet:
    student_id: str
    observations: list[dict[str, Any]] = field(default_factory=list)
    superseded: list[dict[str, Any]] = field(default_factory=list)
    status: str = "complete"
    source_projection: str = "text"
    injection_flagged: bool = False


@dataclass
class AnomalyItem:
    kind: str
    student_id: str
    criterion_id: str | None
    detail: str
    event_id: str


@dataclass
class RenderedRun:
    run_id: str
    sheets: list[EvidenceSheet]
    overview: dict[str, Any]
    claims: list[dict[str, Any]]
    anomalies: list[AnomalyItem]
    excluded: list[dict[str, Any]]
    source_events: list[str]
    range_hash: str
    renditions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "sheets": [
                {
                    "student_id": s.student_id,
                    "status": s.status,
                    "source_projection": s.source_projection,
                    "injection_flagged": s.injection_flagged,
                    "observations": s.observations,
                    "superseded": s.superseded,
                }
                for s in self.sheets
            ],
            "overview": self.overview,
            "claims": self.claims,
            "anomalies": [
                {
                    "kind": a.kind,
                    "student_id": a.student_id,
                    "criterion_id": a.criterion_id,
                    "detail": a.detail,
                    "event_id": a.event_id,
                }
                for a in self.anomalies
            ],
            "excluded": self.excluded,
            "renditions": self.renditions,
            # Divergence is detectable, not assumed: an artifact names the events it consumed
            # and hashes them, so `scripts/verify_artifact.py` can re-fold and compare rather
            # than take the artifact's word for its own provenance.
            "generated_from": {
                "event_count": len(self.source_events),
                "source_events": self.source_events,
                "range_hash": self.range_hash,
            },
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def render(run_id: str, events: list[Event]) -> RenderedRun:
    """Fold an event stream into artifacts. Pure; order-independent; byte-stable."""
    ordered = sorted((e for e in events if e.run_id == run_id), key=lambda e: e.sort_key)

    # --- accumulate -------------------------------------------------------------------
    # `current` holds the live version of each observation. Supersession replaces the entry
    # and pushes the previous version into history: nothing is ever discarded, because an
    # edited observation whose original is gone cannot be appealed.
    current: dict[str, dict[str, Any]] = {}
    history: dict[str, list[dict[str, Any]]] = {}
    outcome: dict[str, str] = {}
    students: dict[str, dict[str, Any]] = {}
    anomalies: list[AnomalyItem] = []
    excluded: list[dict[str, Any]] = []
    injection_flagged: set[str] = set()
    renditions: dict[str, dict[str, Any]] = {}
    # Drafts awaiting a verdict. Never rendered from here -- only promoted out of it.
    drafted: dict[str, dict[str, Any]] = {}
    rejected_criteria: set[tuple[str, str]] = set()

    def student(sid: str) -> dict[str, Any]:
        return students.setdefault(sid, {"source_projection": "text", "criteria": set()})

    for event in ordered:
        p = event.payload
        sid = str(p.get("student_id", "")) or _student_of(event.item_id)

        if event.step is Step.SUBMISSION_INGESTED:
            student(sid)["source_projection"] = p.get("source_projection", "text")

        elif event.step is Step.RENDITION_FROZEN:
            # Carried so the docket's viewer resolves citations from the log alone.
            if p.get("text"):
                renditions[sid] = {
                    "rendition_id": p.get("rendition_id", ""),
                    "text": p["text"],
                    "spans": p.get("spans", {}),
                    "anchor_capability": p.get("anchor_capability", "exact"),
                    "source_projection": p.get("source_projection", "text"),
                }

        elif event.step is Step.INJECTION_DETECTED:
            injection_flagged.add(sid)
            anomalies.append(
                AnomalyItem(
                    kind="injection_detected",
                    student_id=sid,
                    criterion_id=None,
                    detail=str(p.get("detail", "injection pattern detected in submission text")),
                    event_id=event.event_id,
                )
            )

        elif event.step is Step.OBSERVATION_DRAFTED:
            # A draft is a proposal, not a finding. It is held aside and only reaches an
            # evidence sheet if something later promotes it.
            #
            # This was a real defect: drafts were written straight into `current`, so an
            # observation that the validator went on to REJECT still rendered on the sheet —
            # a citation that failed set membership, or quoted text that is not in the span
            # it names, presented to an instructor as evidence. The event log was correct
            # throughout; the fold was reading it wrongly, which is the failure mode a
            # "one log drives every artifact" design is supposed to make impossible.
            obs = p.get("observation")
            if isinstance(obs, dict):
                drafted[str(obs["observation_id"])] = obs

        elif event.step is Step.OBSERVATION_ACCEPTED:
            obs = p.get("observation")
            if isinstance(obs, dict):
                oid = str(obs["observation_id"])
                current[oid] = obs
                drafted.pop(oid, None)
                student(str(obs["student_id"]))["criteria"].add(str(obs["criterion_id"]))
                outcome[oid] = (
                    "accepted_first_attempt"
                    if int(obs.get("attempts", 1)) <= 1
                    else "accepted_after_retry"
                )

        elif event.step is Step.OBSERVATION_REJECTED:
            # Rejected drafts are discarded from the projection entirely. They remain in the
            # log — every attempt is evidence — but an artifact that displayed them would be
            # showing an instructor a claim the system itself refused.
            rejected_criteria.add((sid, str(p.get("criterion_id", ""))))

        elif event.step is Step.NO_EVIDENCE_RECORDED:
            obs = p.get("observation")
            if isinstance(obs, dict):
                oid = str(obs["observation_id"])
                current[oid] = obs
                outcome[oid] = "no_evidence"
                student(str(obs["student_id"]))["criteria"].add(str(obs["criterion_id"]))
                anomalies.append(
                    AnomalyItem(
                        kind="no_evidence",
                        student_id=str(obs["student_id"]),
                        criterion_id=str(obs["criterion_id"]),
                        detail=str(obs.get("search_notes") or "no supporting passage located"),
                        event_id=event.event_id,
                    )
                )

        elif event.step is Step.NEEDS_HUMAN_REVIEW:
            oid = str(p.get("observation_id", event.item_id))
            outcome[oid] = "needs_human"
            # An escalated observation IS shown, flagged, because the instructor is being
            # asked to look at it -- that is what escalation means. Promoted out of `drafted`
            # if that is where it is, so the human sees the claim under review rather than an
            # anomaly item pointing at nothing.
            # Prefer the observation carried on the escalation event: it is the VERIFIED
            # one, recording which layers passed before entailment disagreed. Falling back to
            # the draft loses that and renders the escalation as though nothing was checked.
            carried = p.get("observation")
            source = (
                carried if isinstance(carried, dict) else (current.get(oid) or drafted.get(oid))
            )

            # A draft promoted on the ATTEMPT-CAP branch is one the validator rejected -- twice.
            # Rendering its citation put a span that does not exist and a quote appearing nowhere
            # in the submission onto the instructor's sheet, in a blockquote, styled as the
            # student's own words. That falsified "every evidence observation cites a real span"
            # on the one screen where it matters.
            #
            # `rejected_criteria` was computed for exactly this case and never read.
            #
            # The escalation still renders -- the instructor is being asked to look at it -- but
            # as an absence, because absence is what actually survived validation.
            if (
                source is not None
                and not isinstance(carried, dict)
                and (sid, str(source.get("criterion_id", ""))) in rejected_criteria
            ):
                source = {
                    **source,
                    "kind": "no_evidence",
                    "citation": None,
                    "search_notes": (
                        "The proposed citations for this criterion failed validation on every "
                        "permitted attempt and were discarded. Nothing is shown here because "
                        "nothing passed; every attempt remains in the event log."
                    ),
                }

            if source is not None:
                current[oid] = {
                    **source,
                    "needs_human": True,
                    "needs_human_reason": p.get("reason"),
                }
                drafted.pop(oid, None)
                student(str(source.get("student_id", sid)))["criteria"].add(
                    str(source.get("criterion_id", ""))
                )
            anomalies.append(
                AnomalyItem(
                    kind=str(p.get("anomaly_kind", "needs_human")),
                    student_id=sid,
                    criterion_id=p.get("criterion_id"),
                    detail=str(p.get("reason", "escalated for human review")),
                    event_id=event.event_id,
                )
            )

        elif event.step is Step.OBSERVATION_EDITED_BY_HUMAN:
            before, after = p.get("before"), p.get("after")
            if isinstance(after, dict):
                new_id = str(after["observation_id"])
                if isinstance(before, dict):
                    old_id = str(before["observation_id"])
                    history.setdefault(new_id, []).append(before)
                    # Carry the superseded record's own history forward, so the chain stays
                    # whole across repeated edits rather than only remembering one step back.
                    history[new_id] = history.get(old_id, []) + history[new_id]
                    current.pop(old_id, None)
                    outcome.pop(old_id, None)
                current[new_id] = after
                outcome[new_id] = outcome.get(new_id, "accepted_first_attempt")

        elif event.step is Step.TASK_ABANDONED:
            excluded.append(
                {
                    "student_id": sid,
                    "reason": str(p.get("reason", "join_timeout")),
                    "event_id": event.event_id,
                }
            )
            outcome[f"abandoned::{sid}"] = "abandoned"
            anomalies.append(
                AnomalyItem(
                    kind="abandoned",
                    student_id=sid,
                    criterion_id=None,
                    detail=str(p.get("reason", "join_timeout")),
                    event_id=event.event_id,
                )
            )

        elif event.step is Step.TASK_FAILED:
            anomalies.append(
                AnomalyItem(
                    kind="parse_failure" if p.get("stage") == "ingest" else "task_failed",
                    student_id=sid,
                    criterion_id=None,
                    detail=str(p.get("reason", "task failed")),
                    event_id=event.event_id,
                )
            )

    # --- project ----------------------------------------------------------------------
    sheets: list[EvidenceSheet] = []
    for sid in sorted(students):
        obs = sorted(
            (o for o in current.values() if o.get("student_id") == sid),
            key=lambda o: (str(o.get("criterion_id", "")), str(o.get("observation_id", ""))),
        )
        needs_human_count = sum(1 for o in obs if o.get("needs_human"))
        # More than half a student's criteria unresolved is one problem with the submission's
        # processing, not six independent ones. Routing it as a single INSUFFICIENT sheet
        # keeps the anomaly queue readable instead of burying the other students' items.
        status = (
            "INSUFFICIENT"
            if obs and needs_human_count / len(obs) > INSUFFICIENT_THRESHOLD
            else "complete"
        )
        superseded = sorted(
            (h for o in obs for h in history.get(str(o.get("observation_id")), [])),
            key=lambda o: str(o.get("observation_id", "")),
        )
        sheets.append(
            EvidenceSheet(
                student_id=sid,
                observations=obs,
                superseded=superseded,
                status=status,
                source_projection=str(students[sid]["source_projection"]),
                injection_flagged=sid in injection_flagged,
            )
        )

    claims = sorted(
        current.values(),
        key=lambda o: (str(o.get("student_id", "")), str(o.get("criterion_id", ""))),
    )

    # Counted, never generated. Every number here is a length or a sum over the projection
    # directly above it, which is what makes KAR-404's acceptance criterion — the overview
    # matches a direct count of the same projection — a tautology rather than a coincidence.
    by_criterion: dict[str, dict[str, int]] = {}
    for o in claims:
        cid = str(o.get("criterion_id", ""))
        bucket = by_criterion.setdefault(cid, {"evidence": 0, "no_evidence": 0, "needs_human": 0})
        bucket["evidence" if o.get("kind") == "evidence" else "no_evidence"] += 1
        if o.get("needs_human"):
            bucket["needs_human"] += 1

    outcome_counts = {name: 0 for name in TERMINAL_OUTCOMES}
    for value in outcome.values():
        if value in outcome_counts:
            outcome_counts[value] += 1

    # Injection is counted per *submission*, not per observation, and so it is counted here
    # rather than falling out of the observation-keyed map above.
    #
    # This was a real defect: the divergence tour reported "injection flagged: 0" on a run
    # where s07's payload had been detected, flagged, and shown with a chip two panels lower
    # on the same page. The tour is the video's central claim -- six different consequences
    # from one unattended run -- and it was contradicting the table underneath it.
    #
    # Injection does not appear in `outcome` because it is not a terminal state *of an
    # observation*: a flagged submission still produces observations, by design (KAR-311).
    # It is a terminal outcome of the submission, which is a different unit of work.
    outcome_counts["injection_detected"] = len(injection_flagged)

    overview = {
        # Ordered by student ID. Not by anything that could be read as quality — see the
        # module docstring.
        "students": [s.student_id for s in sheets],
        "students_total": len(sheets),
        "observations_total": len(claims),
        "by_criterion": {k: by_criterion[k] for k in sorted(by_criterion)},
        "terminal_outcomes": outcome_counts,
        "excluded_total": len(excluded),
        "anomalies_total": len(anomalies),
        "insufficient_sheets": [s.student_id for s in sheets if s.status == "INSUFFICIENT"],
    }

    source_events = [e.event_id for e in ordered]
    range_hash = sha256_text(canonical_json([e.content_hash for e in ordered]))

    return RenderedRun(
        run_id=run_id,
        sheets=sheets,
        overview=overview,
        claims=claims,
        anomalies=sorted(anomalies, key=lambda a: (a.kind, a.student_id, a.event_id)),
        excluded=sorted(excluded, key=lambda x: str(x["student_id"])),
        source_events=source_events,
        range_hash=range_hash,
        renditions=renditions,
    )


def _student_of(item_id: str) -> str:
    """Best-effort student ID for events whose payload omits it.

    Item IDs on the analysis path are `{student_id}::{criterion_id}`. This is a fallback for
    lifecycle events, not a parser anything important depends on.
    """
    return item_id.split("::", 1)[0] if "::" in item_id else item_id
