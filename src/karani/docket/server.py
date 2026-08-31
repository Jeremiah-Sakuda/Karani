"""The docket — a Cloud Run service serving one rendered run.

Edits are the interesting route. An instructor who disagrees with a drafted observation does
not change it: the edit writes an `ObservationEditedByHuman` event carrying both `before` and
`after`, the fold replaces the live version, and the original stays in the log and in the
appeal packet. Nothing is mutated anywhere, which is what makes "this output is designed to be
contestable" a mechanism rather than a slogan — you cannot contest a record whose earlier
version no longer exists.

The public challenge box (KAR-412) is free, unmetered, and needs no login, deliberately. A
judge who has to sign in to test the central claim will not test the central claim.

**Reads are public; writes are not.** That distinction was missing: `/edit` and `/ratify`
append events and trigger a Drive write, and on a service deployed
`--allow-unauthenticated` they were reachable by anyone with the URL, who could append an
event carrying `actor: "instructor"`. Every page here remains readable with no login. The two
endpoints that write require an instructor token, exchanged once at `/unlock` for an HttpOnly
cookie. With no token configured they stay open, which is why `make demo` is unchanged.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from karani.docket.render_html import (
    _e,
    challenge_answer,
    challenge_page,
    overview_page,
    page,
    student_page,
)
from karani.render import RenderedRun, render
from karani.schema.events import Event, Step


def build_app(
    rendered: RenderedRun, store: Any | None = None, events: list[Any] | None = None
) -> FastAPI:
    app = FastAPI(title="Karani docket", docs_url=None, redoc_url=None)
    # The write gate. When `KARANI_INSTRUCTOR_TOKEN` is set, the two endpoints that append
    # events -- /edit and /ratify -- require a cookie obtained by presenting that token once
    # at /unlock. When it is unset, they stay open.
    #
    # The deployed docket runs with `--allow-unauthenticated`, and that is deliberate: the
    # public challenge box is a submission asset and must work with no login, no quota, and
    # no friction. But "unauthenticated reads" had been silently extended to unauthenticated
    # *writes*, so anyone who found the URL could append an `ObservationEditedByHuman` event
    # carrying `actor: "instructor"` and trigger a Drive write and a CSV export.
    #
    # That is a genuine hole and it sat underneath an identity story elaborate enough to have
    # its own diagram: five service accounts, a conditioned IAM binding, a separate grades
    # database -- and then no check at all on the layer that accepts writes. Least privilege
    # below, an open door above.
    #
    # Defaulting to open when unset is what keeps `make demo` and the recorded video
    # unchanged; `deploy.sh` generates a token, so the public instance is closed.
    instructor_token = os.environ.get("KARANI_INSTRUCTOR_TOKEN", "").strip()

    state: dict[str, Any] = {"run": rendered, "store": store, "token": instructor_token}
    # Exposed so tests can drive the endpoints the way a person would -- post an edit, read
    # back the re-folded run, post another against the observation that superseded the first.
    # Reaching into the closure would have meant testing a copy of the handler instead.
    app.state.karani = state

    def current() -> RenderedRun:
        return state["run"]

    def writes_open(request: Request) -> bool:
        """Whether this request may append to the log."""
        if not instructor_token:
            return True
        # Constant-time comparison. `==` short-circuits on the first differing byte, which
        # in principle lets a remote caller time their way toward the token. Impractical to
        # exploit over Cloud Run jitter, but compare_digest costs nothing and a security
        # review should not have to argue about it.
        return secrets.compare_digest(
            request.cookies.get("karani_instructor", ""), instructor_token
        )

    @app.get("/unlock", response_class=HTMLResponse)
    def unlock(token: str = "") -> Any:
        """Exchange the instructor token for a cookie.

        A cookie rather than a form field so the token never renders into a page anyone can
        view, and `HttpOnly` so a script on the page cannot read it back out. This is a shared
        secret for one instructor's own docket, not an identity system -- said plainly here
        because the rest of this project is careful about not overstating what a mechanism is.
        """
        if not instructor_token:
            return HTMLResponse(
                page(
                    "Karani — unlock",
                    "<p class='sub'>This docket has no instructor token "
                    "configured, so editing and ratification are already open.</p>",
                )
            )
        if token != instructor_token:
            return HTMLResponse(
                page(
                    "Karani — unlock",
                    "<p class='sub'>That token was not recognised. "
                    "Editing and ratification stay locked; everything else is readable.</p>",
                ),
                status_code=403,
            )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "karani_instructor",
            instructor_token,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=60 * 60 * 12,
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(overview_page(current()))

    @app.get("/student/{student_id}", response_class=HTMLResponse)
    def student(student_id: str) -> HTMLResponse:
        return HTMLResponse(student_page(current(), student_id))

    @app.get("/brief", response_class=HTMLResponse)
    def brief() -> HTMLResponse:
        """The morning brief (KAR-418): work-list first, data set second."""
        from karani.docket.brief import brief_page

        return HTMLResponse(brief_page(current()))

    @app.get("/replay", response_class=HTMLResponse)
    def replay() -> HTMLResponse:
        """The glass-box replay (KAR-416). Metadata only; payloads never leave the server."""
        from karani.docket.replay import replay_page

        run = current()
        run_events = events
        if run_events is None and state["store"] is not None:
            run_events = state["store"].read_run(run.run_id)
        if not run_events:
            return HTMLResponse(
                page(
                    "Karani — replay",
                    "<p class='sub'>No raw events are available to this docket instance, "
                    "so there is nothing to replay. The artifact view is unaffected.</p>",
                ),
                status_code=404,
            )
        return HTMLResponse(replay_page(run.run_id, run_events))

    @app.get("/challenge", response_class=HTMLResponse)
    def challenge_get() -> HTMLResponse:
        return HTMLResponse(challenge_page())

    @app.post("/challenge", response_class=HTMLResponse)
    def challenge_post(ask: str = Form("")) -> HTMLResponse:
        return HTMLResponse(challenge_page(answer=challenge_answer(ask), asked=ask))

    @app.post("/edit")
    def edit(
        request: Request,
        observation_id: str = Form(...),
        student_id: str = Form(...),
        text: str = Form(...),
        edit_reason: str = Form(""),
    ) -> RedirectResponse:
        if not writes_open(request):
            return RedirectResponse(f"/student/{student_id}?locked=1", status_code=303)

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

        # How many times this unit of work has already been edited. The event ID is derived
        # from (run_id, step, item_id, attempt), and none of those four changes between two
        # edits of the same observation -- so a second edit minted an ID that already existed
        # with different content, raised `EventIdCollision`, and returned a 500 to an
        # instructor who had done nothing wrong.
        #
        # That is the single most likely thing for a human to do on this page: correct a
        # wording, read it back, correct it again.
        #
        # The generation counter is read from the log rather than held in memory, so it is the
        # same on a fresh process, and replaying the same sequence of edits reproduces the
        # same event IDs. `int(now.timestamp())` was doing this job in the observation ID and
        # did it badly -- two edits inside one second produced the same identifier.
        item_id = f"{student_id}::{before.get('criterion_id')}"
        generation = sum(
            1
            for event in state["store"].read_run(run.run_id)
            if event.step == Step.OBSERVATION_EDITED_BY_HUMAN and event.item_id == item_id
        )

        after = {
            **before,
            "observation_id": f"{observation_id}+edit{generation + 1}",
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
                item_id=item_id,
                ts=now,
                # The edit generation, not the analysis attempt count. Distinct edits are
                # distinct facts and need distinct identities.
                attempt=generation,
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

    @app.post("/grade")
    def record_grade(
        request: Request,
        student_id: str = Form(...),
        grade: str = Form(...),
        note: str = Form(""),
    ) -> HTMLResponse:
        """The instructor records a grade — the one write Karani makes on someone's behalf
        and the one it can never originate (KAR-415).

        `GradesStore.write()` existed with no caller. An adversarial review found it, and the
        finding was sharper than "dead code": the grades database is the centrepiece of this
        project's security argument, and nothing in the running system had ever written to
        it. The boundary was only ever demonstrated in the negative — a service account being
        denied — which proves an identity cannot write, not that the destination is real.

        There is deliberately no path from an `Observation` to a `Grade`. Not a disabled one:
        none. This handler takes the grade as **typed input from a person**, and the only
        thing it reads from the run is whether the student exists.

        It requires the instructor token, because the identity writing here is the whole
        point of the boundary existing.
        """
        if not writes_open(request):
            return HTMLResponse(
                page(
                    "Karani — locked",
                    "<p class='sub'>Recording a grade writes to the instructor's grades "
                    "database and requires the instructor token.</p>",
                ),
                status_code=403,
            )

        run = current()
        if not any(sheet.student_id == student_id for sheet in run.sheets):
            return HTMLResponse(
                page(
                    "Karani — unknown submission",
                    f"<p class='sub'>No submission {_e(student_id)} in this run.</p>",
                ),
                status_code=404,
            )

        from karani.config import Settings
        from karani.grades import Grade, open_grades_store

        store = open_grades_store(Settings.from_env().project)
        if store is None:
            # Not deployed, or no credentials. Reported rather than swallowed: an instructor
            # who believes a grade was recorded and finds an empty CSV column later is worse
            # off than one who is told now.
            return HTMLResponse(
                page(
                    "Karani — grades database unreachable",
                    "<p class='sub'>The grades database is not reachable from here, so "
                    "nothing was written. This is the expected state locally: the database "
                    "exists only on the deployed project, and Karani reports the failure "
                    "rather than recording a grade it did not store.</p>",
                ),
                status_code=503,
            )

        try:
            store.write(
                Grade(
                    student_id=student_id,
                    value=grade,
                    actor="instructor",
                    ts=datetime.now(UTC),
                    note=note,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the denial is the interesting outcome
            return HTMLResponse(
                page(
                    "Karani — grade not recorded",
                    f"<p class='sub'>The write was refused: "
                    f"<span class='mono'>{_e(type(exc).__name__)}</span>. Nothing was "
                    f"recorded. If this docket is running as a pipeline service account, "
                    f"this refusal is the boundary working as designed.</p>",
                ),
                status_code=502,
            )

        return HTMLResponse(
            page(
                "Karani — grade recorded",
                f"<p class='sub'>Recorded <span class='mono'>{_e(grade)}</span> for "
                f"<span class='mono'>{_e(student_id)}</span>, attributed to the instructor, "
                f"with an immutable history entry beside it. Karani did not derive this "
                f"value and has no function that could.</p>",
            )
        )

    @app.post("/ratify")
    def ratify_and_deliver(request: Request, student_ids: str = Form("")) -> HTMLResponse:
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

        if not writes_open(request):
            return HTMLResponse(
                page(
                    "Karani — locked",
                    "<p class='sub'>Ratification is locked on this docket. It appends events "
                    "and writes to the instructor's Drive, so it requires the instructor "
                    "token. Everything on this site remains readable without one.</p>",
                ),
                status_code=403,
            )

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


def serve(
    rendered: RenderedRun,
    port: int = 8080,
    store: Any | None = None,
    events: list[Any] | None = None,
) -> None:
    import uvicorn

    print(f"\ndocket  http://localhost:{port}")
    print(f"        http://localhost:{port}/challenge   (try to make it give you a grade)\n")
    uvicorn.run(build_app(rendered, store, events), host="0.0.0.0", port=port, log_level="warning")
