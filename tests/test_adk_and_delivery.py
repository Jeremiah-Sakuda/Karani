"""KAR-302, KAR-315, KAR-406 — the three paths a review found were implemented but unreached.

Each of these existed as working code with no caller. That is a specific and nasty failure
mode for a hackathon submission, because the repository *looks* complete: the module is there,
it is well written, and a reader checking "is ADK used?" finds a file that uses ADK. What they
would not find, without grepping for callers, is that nothing invokes it.

So these tests assert **reachability**, not just correctness:

    ADK        the pipeline executes through the agent topology, and the trace proves it
    Gemma      triage runs on every submission and records which tier answered
    delivery   ratification actually produces artifacts and ArtifactDelivered events
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from karani.analysis.adk_agents import SharedResult, build_pipeline_agent, run_with_adk
from karani.analysis.cache import ResponseCache
from karani.armor.scan import LocalPatternScanner
from karani.delivery.deliver import build_csv, deliver
from karani.ingest.source import LocalSource
from karani.render import render
from karani.store.local import LocalEventStore
from karani.triage.gemma import heuristic_triage, triage

from .test_pipeline_e2e import CRITERIA, FIXTURES, ScriptedAnalyst


def _context(tmp_path: Path, run_id: str = "run-adk") -> dict:
    cache = ResponseCache(tmp_path / "cache")
    return {
        "run_id": run_id,
        "source": LocalSource(FIXTURES / "dev"),
        "criteria": CRITERIA,
        "store": LocalEventStore(tmp_path / "store"),
        "client": ScriptedAnalyst(cache, plan={"c4": "no_evidence"}),
        "cache": cache,
        "scanner": LocalPatternScanner(),
        "max_workers": 3,
        "project": "",
    }


# --- ADK: the mandatory agent framework, on the execution path -------------------------


def test_the_adk_topology_has_the_four_roles():
    """Property: the agent roles of §3.2 exist as a composed ADK graph."""
    agent = build_pipeline_agent({"run_id": "x"})
    names = [sub.name for sub in agent.sub_agents]
    assert names == ["dispatcher", "analyst_validator", "anomaly_triage"]
    assert agent.name == "karani_pipeline"


def test_the_pipeline_actually_executes_through_adk(tmp_path):
    """Property (KAR-302's AC): a dispatcher → workers → validator trace, from a real run.

    The acceptance criterion asks for a visible trace, and this asserts the trace comes from
    an execution rather than from a logging statement: the run's own results have to appear
    in it.

    `run_with_adk` had **zero callers** when a review checked. The mandatory Google Agent
    Framework requirement was being satisfied by a module nothing invoked — which is exactly
    the shape of claim a Stage One reviewer opens a file to verify.
    """
    context = _context(tmp_path)
    shared: SharedResult = asyncio.run(run_with_adk(context))

    assert [line.split("]")[0].lstrip("[") for line in shared.trace] == [
        "dispatcher",
        "analyst_validator",
        "anomaly_triage",
    ]
    assert "Dispatched 3 submissions" in shared.trace[0]

    # The trace reports what actually happened, not a fixed string.
    assert shared.summary is not None
    assert len(shared.summary.completed) == 3
    assert shared.rendered is not None
    assert shared.rendered.overview["terminal_outcomes"]["no_evidence"] >= 1


def test_adk_run_and_direct_run_produce_the_same_claims(tmp_path):
    """Property: ADK supplies the topology and changes no result.

    This is the claim `docs/antigravity/decision.md` makes — that no invariant depends on the
    framework, and swapping it for plain SDK calls structured as the same roles would change
    nothing. Asserted rather than stated.
    """
    from karani.analysis.dispatcher import run_pipeline

    via_adk = _context(tmp_path / "a", run_id="run-same")
    asyncio.run(run_with_adk(via_adk))
    adk_claims = render("run-same", via_adk["store"].read_run("run-same")).claims

    direct = _context(tmp_path / "b", run_id="run-same")
    run_pipeline(**{k: v for k, v in direct.items() if k != "shared"})
    direct_claims = render("run-same", direct["store"].read_run("run-same")).claims

    def shape(claims):
        return sorted((c["student_id"], c["criterion_id"], c["kind"]) for c in claims)

    assert shape(adk_claims) == shape(direct_claims)


# --- Gemma triage: reachable, and honest about which tier answered ---------------------


def test_triage_runs_on_every_submission_and_records_the_deciding_tier(tmp_path):
    """Property (KAR-315): a `TriageDecided` event per submission, naming what decided it.

    `decided_by` is recorded from what ran, never inferred from configuration. That is what
    stops the log from claiming Gemma answered when the deterministic fallback did — and in
    every environment without a local Ollama daemon, the fallback is what answers.
    """
    context = _context(tmp_path)
    asyncio.run(run_with_adk(context))

    events = [e for e in context["store"].read_run("run-adk") if e.step.value == "TriageDecided"]
    assert len(events) == 3, "triage did not run on every submission"

    for event in events:
        assert event.payload["decided_by"], "no deciding tier recorded"
        # Offline, this must be the fallback -- and must say so rather than naming Gemma.
        if not event.payload["gemma_available"]:
            assert "gemma" not in event.payload["decided_by"].lower(), (
                "the fallback is claiming to be Gemma"
            )


def test_triage_rejects_course_material_but_not_student_work():
    """Property: the ambiguous non-submission case is handled without a model call."""
    essay = (FIXTURES / "s01.md").read_text(encoding="utf-8")
    assert triage(essay).kind == "submission"

    material = (
        "Essay 3 Assignment Sheet. This assignment is due by Friday at midnight. Your essay "
        "should be 750 to 1100 words. Grading rubric: thesis, evidence, organization, "
        "counterarguments, mechanics. Points possible: 100. Late policy: one letter grade per "
        "day. Office hours Tuesday and Thursday. Submit your work through the course site. "
        "Learning outcomes include argumentation and source integration. Course policies "
        "apply as described in the syllabus."
    ) * 2
    assert heuristic_triage(material).kind == "non_submission"


def test_triage_never_raises_and_always_answers():
    """Property: a bonus tier cannot take a mandatory one hostage.

    Gemma is a bonus item. If triage could raise, an unavailable bonus model would stop a run
    that satisfies every mandatory requirement.
    """
    for text in ("", "x", "a" * 100_000, "🙂" * 500):
        decision = triage(text)
        assert decision.decided_by
        assert decision.kind in ("submission", "non_submission", "unreadable")


# --- delivery: the action the Taskmaster category is about -----------------------------


def test_ratification_delivers_artifacts_and_logs_them(tmp_path):
    """Property (KAR-406): the workflow ends somewhere, and the log records that it did.

    `deliver()` had zero callers when a review checked — the step that defines this contest
    category, *"sends the right info to the right places"*, was implemented and unreachable.
    """
    context = _context(tmp_path)
    asyncio.run(run_with_adk(context))
    run = render("run-adk", context["store"].read_run("run-adk"))

    out = tmp_path / "delivered"
    result = deliver(run, out_dir=out, grades={}, ratified={s.student_id for s in run.sheets})

    assert result.files, "ratification produced no artifacts"
    assert any(f.endswith(".csv") for f in result.files)
    assert all((out / f).exists() for f in result.files)

    delivered = [e for e in result.events if e.step.value == "ArtifactDelivered"]
    assert delivered, "no ArtifactDelivered events"


def test_the_csv_grade_column_is_empty_when_the_instructor_has_not_graded(tmp_path):
    """Property: the pipeline contributes no verdict-bearing field to the exported CSV.

    The export is the last place a verdict could enter a downstream system, and the only
    correct number of verdicts for it to contribute is zero. Karani exports a blank cell
    rather than deriving, inferring, or defaulting one.
    """
    context = _context(tmp_path)
    asyncio.run(run_with_adk(context))
    run = render("run-adk", context["store"].read_run("run-adk"))

    csv_text = build_csv(run, grades={})
    rows = [line.split(",") for line in csv_text.strip().splitlines()]
    header, body = rows[0], rows[1:]

    grade_col = header.index("grade")
    assert body, "no rows exported"
    for row in body:
        assert row[grade_col] == "", f"a grade was written without an instructor: {row}"


def test_the_csv_grade_column_carries_exactly_what_the_instructor_wrote(tmp_path):
    """Property: grades pass through from `grades/` unchanged, and only from there."""
    context = _context(tmp_path)
    asyncio.run(run_with_adk(context))
    run = render("run-adk", context["store"].read_run("run-adk"))

    csv_text = build_csv(run, grades={"s01": "B+"})
    lines = {line.split(",")[0]: line.split(",")[1] for line in csv_text.strip().splitlines()[1:]}

    assert lines["s01"] == "B+"
    for student, grade in lines.items():
        if student != "s01":
            assert grade == "", f"{student} received a grade nobody wrote"


def test_no_csv_column_is_derived_from_an_observation(tmp_path):
    """Property: the export carries counts of Karani's bookkeeping, never assessments.

    `observations` and `needs_review` describe how much evidence was located and how much was
    escalated. Neither orders students, and neither describes the work.
    """
    context = _context(tmp_path)
    asyncio.run(run_with_adk(context))
    run = render("run-adk", context["store"].read_run("run-adk"))

    header = build_csv(run, grades={}).splitlines()[0].split(",")
    from karani.schema.observation import BANNED_FIELD_NAMES

    assert not (set(header) - {"grade"}) & BANNED_FIELD_NAMES, (
        f"a verdict-shaped column reached the export: {header}"
    )
