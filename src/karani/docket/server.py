"""The docket — a Cloud Run service serving one rendered run.

Edits are the interesting route. An instructor who disagrees with a drafted observation does
not change it: the edit writes an `ObservationEditedByHuman` event carrying both `before` and
`after`, the fold replaces the live version, and the original stays in the log and in the
appeal packet. Nothing is mutated anywhere, which is what makes "this output is designed to be
contestable" a mechanism rather than a slogan — you cannot contest a record whose earlier
version no longer exists.

The public challenge box (KAR-412) is free, unmetered, and needs no login, deliberately. A
judge who has to sign in to test the central claim will not test the central claim.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from karani.docket.render_html import (
    challenge_answer,
    challenge_page,
    overview_page,
    page,
    student_page,
)
from karani.render import RenderedRun, render
from karani.schema.events import Event, Step


def build_app(rendered: RenderedRun, store: Any | None = None) -> FastAPI:
    app = FastAPI(title="Karani docket", docs_url=None, redoc_url=None)
    state: dict[str, Any] = {"run": rendered, "store": store}

    def current() -> RenderedRun:
        return state["run"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(overview_page(current()))

    @app.get("/student/{student_id}", response_class=HTMLResponse)
    def student(student_id: str) -> HTMLResponse:
        return HTMLResponse(student_page(current(), student_id))

    @app.get("/challenge", response_class=HTMLResponse)
    def challenge_get() -> HTMLResponse:
        return HTMLResponse(challenge_page())

    @app.post("/challenge", response_class=HTMLResponse)
    def challenge_post(ask: str = Form("")) -> HTMLResponse:
        return HTMLResponse(challenge_page(answer=challenge_answer(ask), asked=ask))

    @app.post("/edit")
    def edit(
        observation_id: str = Form(...),
        student_id: str = Form(...),
        text: str = Form(...),
        edit_reason: str = Form(""),
    ) -> RedirectResponse:
        run = current()
        before = next(
            (
                o
                for s in run.sheets
                for o in s.observations
                if o.get("observation_id") == observation_id
            ),
            None,
        )
        if before is None or state["store"] is None:
            return RedirectResponse(f"/student/{student_id}", status_code=303)

        now = datetime.now(UTC)
        after = {
            **before,
            "observation_id": f"{observation_id}+edit{int(now.timestamp())}",
            "text": text,
            "supersedes": observation_id,
            "review": {
                "reviewer_id": "instructor",
                "edit_reason": edit_reason or "instructor edit",
                "ts": now.isoformat(),
            },
            # An instructor's edit resolves the escalation. It does not resolve it by the
            # system deciding it was fine; it resolves it because a human looked.
            "needs_human": False,
            "needs_human_reason": None,
        }

        state["store"].create(
            Event.build(
                run_id=run.run_id,
                step=Step.OBSERVATION_EDITED_BY_HUMAN,
                item_id=f"{student_id}::{before.get('criterion_id')}",
                ts=now,
                attempt=int(before.get("attempts", 1)),
                payload={
                    "student_id": student_id,
                    "before": before,
                    "after": after,
                    "actor": "instructor",
                    "ts": now.isoformat(),
                },
            )
        )
        # Re-fold rather than patching the in-memory artifact. The artifact is a function of
        # the log; recomputing it is the only way to keep that true after a write.
        state["run"] = render(run.run_id, state["store"].read_run(run.run_id))
        return RedirectResponse(f"/student/{student_id}", status_code=303)

    @app.get("/appeal/{student_id}")
    def appeal(student_id: str) -> JSONResponse:
        """KAR-413 — everything needed to contest one student's evidence, in one file.

        Observations, citations with the surrounding context that proves their position, the
        full supersession chain, and the hash over the consumed event range. A packet that
        omitted superseded versions would be a summary, not an appeal: the question under
        appeal is often precisely what changed and who changed it.
        """
        run = current()
        sheet = next((s for s in run.sheets if s.student_id == student_id), None)
        if sheet is None:
            return JSONResponse({"error": "no such submission in this run"}, status_code=404)

        rendition = run.renditions.get(student_id, {})
        return JSONResponse(
            {
                "run_id": run.run_id,
                "student_id": student_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "observations": sheet.observations,
                "supersession_chain": sheet.superseded,
                "rendition": {
                    "rendition_id": rendition.get("rendition_id"),
                    "source_projection": rendition.get("source_projection"),
                    "anchor_capability": rendition.get("anchor_capability"),
                    "spans": rendition.get("spans"),
                    "text": rendition.get("text"),
                },
                "anomalies": [
                    {
                        "kind": a.kind,
                        "criterion_id": a.criterion_id,
                        "detail": a.detail,
                        "event_id": a.event_id,
                    }
                    for a in run.anomalies
                    if a.student_id == student_id
                ],
                "verification": {
                    "source_event_count": len(run.source_events),
                    "range_hash": run.range_hash,
                    "how_to_verify": (
                        "karani verify --artifact <rendered.json> --log <events.jsonl> "
                        "re-folds the log and compares the range hash. A packet whose hash "
                        "does not match its log has diverged from the record."
                    ),
                },
                "what_this_packet_does_not_contain": (
                    "A grade, a score, a rank, or any assessment of quality. No such field "
                    "exists on any record in this system."
                ),
            }
        )

    @app.post("/ratify")
    def ratify_and_deliver(student_ids: str = Form("")) -> HTMLResponse:
        """Ratification — the step that turns evidence into delivered output (KAR-406).

        This is the action the Taskmaster category is actually about: *"sends the right info
        to the right places."* Everything upstream produces evidence; this is where the
        workflow ends somewhere the instructor already works.

        The grade column of the exported CSV reads exclusively from `grades/`, which no
        pipeline identity can write. If the instructor has not graded, the column is empty —
        Karani exports blank cells rather than filling them in.
        """
        from karani.config import REPO_ROOT, Settings
        from karani.delivery.deliver import deliver

        run = current()
        settings = Settings.from_env()
        targets = {s.strip() for s in student_ids.split(",") if s.strip()} or {
            s.student_id for s in run.sheets
        }

        # Grades are read from the instructor's own Firestore database, which lives outside
        # every pipeline identity's IAM reach. If it is unreachable -- no credentials, not
        # deployed, or the docket's own service account correctly denied -- this returns an
        # empty map and the CSV exports blank grade cells. That is the correct degraded
        # behaviour: Karani exports the blank rather than deriving a value.
        from karani.grades import open_grades_store

        grades_store = open_grades_store(settings.project)
        try:
            grades = grades_store.read_all() if grades_store else {}
        except Exception:  # noqa: BLE001 - denied or unreachable both mean "no grades to export"
            grades = {}

        result = deliver(
            run,
            out_dir=REPO_ROOT / "out" / run.run_id / "delivered",
            grades=grades,
            drive_folder_id=settings.delivery_drive_folder_id,
            ratified=targets,
        )
        if state["store"] is not None:
            for event in result.events:
                state["store"].create(event)
            state["run"] = render(run.run_id, state["store"].read_run(run.run_id))

        files = "".join(f"<li class='mono'>{f}</li>" for f in result.files)
        return HTMLResponse(
            page(
                "Karani — delivered",
                f"""
<nav class="crumbs"><a href="/">← class docket</a></nav>
<h1>Delivered</h1>
<p class="sub">{len(result.files)} artifact(s) written to
   <span class="mono">{result.destination}</span>, and
   {len(result.events)} <span class="mono">ArtifactDelivered</span> event(s) appended.</p>
<div class="panel"><ul>{files}</ul></div>
<div class="notice">The CSV's grade column is populated exclusively from
   <span class="mono">grades/</span> — written by the instructor's own session, and unwritable
   by every pipeline identity. {result.grades_absent} row(s) have an empty grade cell because
   no grade has been entered. Karani exports the blank rather than filling it.</div>
""",
            )
        )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse({"ok": True, "run_id": current().run_id})

    @app.get("/artifact.json")
    def artifact() -> JSONResponse:
        return JSONResponse(json.loads(current().to_json()))

    @app.exception_handler(404)
    def not_found(_request: Any, _exc: Any) -> HTMLResponse:
        return HTMLResponse(
            page("Not found", "<h1>Not found</h1><p><a href='/'>class docket</a></p>"),
            status_code=404,
        )

    return app


def serve(rendered: RenderedRun, port: int = 8080, store: Any | None = None) -> None:
    import uvicorn

    print(f"\ndocket  http://localhost:{port}")
    print(f"        http://localhost:{port}/challenge   (try to make it give you a grade)\n")
    uvicorn.run(build_app(rendered, store), host="0.0.0.0", port=port, log_level="warning")
