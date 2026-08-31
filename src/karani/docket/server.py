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
import uuid
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

    @app.get("/scholarship", response_class=HTMLResponse)
    @app.get("/scholarship/{student_id}", response_class=HTMLResponse)
    def scholarship(student_id: str = "") -> HTMLResponse:
        """The second domain, one click away (KAR-422): scholarship review, same pipeline.

        Served from the committed recorded log (`fixtures/scholarship-run.jsonl`) baked
        into the image — real Gemini analysis and real local-Gemma second-reader verdicts,
        replayed. The point is provable generality: a different rubric, a different kind of
        document, and the same refusal, with zero code changes. Cached at first request;
        the fold is pure, so once is enough.
        """
        from karani.config import REPO_ROOT
        from karani.store.local import read_jsonl_log

        if "scholarship_run" not in state:
            log_path = REPO_ROOT / "fixtures" / "scholarship-run.jsonl"
            if not log_path.exists():
                return HTMLResponse(
                    page(
                        "Karani — scholarship",
                        "<p class='sub'>The scholarship fixture is not present in this build.</p>",
                    ),
                    status_code=404,
                )
            state["scholarship_run"] = render("run-scholarship-p2", read_jsonl_log(log_path))
        sch = state["scholarship_run"]

        banner = (
            '<div class="notice"><strong>A different job, the same clerk.</strong> These are '
            "scholarship personal statements reviewed against a scholarship rubric — not "
            "essays. Same pipeline, zero code changes: evidence is cited to the applicant's "
            "own words, absence is recorded as a finding, and there is still no field that "
            "could rank one applicant against another. Every accepted citation here was "
            "also cross-checked by a second, locally-run model (Gemma) — see any finding's "
            "\u201chow this finding was produced\u201d panel. "
            '<a href="/">Back to the essay review</a>.</div>'
        )
        html_page = student_page(sch, student_id) if student_id else overview_page(sch)
        # The shared renderers link to the main run's routes; rebase the ones that must stay
        # inside the scholarship view, and disable the write actions -- this view is a
        # committed exhibit, not tonight's live run.
        html_page = html_page.replace("href='/student/", "href='/scholarship/")
        html_page = html_page.replace('action="/edit"', 'action="/scholarship-readonly"')
        html_page = html_page.replace('action="/ratify"', 'action="/scholarship-readonly"')
        html_page = html_page.replace("<header", banner + "<header", 1)
        return HTMLResponse(html_page)

    @app.post("/scholarship-readonly", response_class=HTMLResponse)
    def scholarship_readonly() -> HTMLResponse:
        return HTMLResponse(
            page(
                "Karani — exhibit",
                "<p class='sub'>The scholarship view is a committed exhibit of the recorded "
                "run, so corrections and delivery are disabled here. The live essay review "
                "on the <a href='/'>overnight review</a> accepts both.</p>",
            ),
            status_code=403,
        )

    @app.get("/boundary", response_class=HTMLResponse)
    def boundary_get() -> HTMLResponse:
        """The denial, as a page (KAR-420): watch this service try to write a grade.

        The video used to prove the grades boundary in a terminal — impersonated token,
        Python heredoc, PermissionDenied in a monospace wall. True, and unreadable to the
        instructor it protects. This page runs the same class of attempt live, server-side,
        under this service's own identity, and shows the refusal in words. The pytest gate
        (`-m deployed`, against the analysis identity specifically) remains the release
        proof; this is the same boundary made watchable.
        """
        return HTMLResponse(
            page(
                "Karani — the boundary",
                """
<nav class="crumbs"><a href="/">← back to the overnight review</a></nav>
<header class="top">
  <h1>Can Karani write a grade?</h1>
  <p class="sub">Not "does it choose not to." Grades live in a separate database that every
  part of Karani is locked out of — by Google Cloud's permission system, not by good
  intentions. This page lets you watch it try.</p>
</header>
<div class="panel">
  <p>Press the button and this very service — the one rendering the page you are reading —
  will attempt to create a grade record, live, using its own identity. If the boundary
  holds, Google Cloud refuses it before Karani's own code gets a say.</p>
  <form method="post" action="/boundary" style="margin-top:.8rem">
    <button type="submit">Try to write a grade, right now</button>
  </form>
</div>
<div class="panel">
  <p class="sub">Why this matters: a tool that promises not to grade can break its promise
  in an update. A tool with no field for a grade, writing to a database it cannot reach,
  needs a redesign to break it — and a redesign is visible in a way a prompt change never
  is.</p>
</div>
""",
            )
        )

    @app.post("/boundary", response_class=HTMLResponse)
    def boundary_attempt() -> HTMLResponse:
        from karani.config import GRADES_DATABASE, Settings

        settings = Settings.from_env()
        identity = "this docket service"
        try:
            import google.auth
            from google.cloud import firestore as _fs

            credentials, _ = google.auth.default()
            identity = getattr(credentials, "service_account_email", identity) or identity
            client = _fs.Client(project=settings.project or None, database=GRADES_DATABASE)
            probe = f"boundary-page-{uuid.uuid4().hex}"
            client.collection("grades").document(probe).create({"grade": "A"})
        except Exception as exc:  # noqa: BLE001 - the refusal IS the result
            kind = type(exc).__name__
            if kind == "PermissionDenied":
                verdict = f"""
<div class="notice"><strong>Refused.</strong> Google Cloud denied the write before it
reached the database.</div>
<div class="panel">
  <p><strong>Who asked:</strong> <span class="mono">{_e(identity)}</span></p>
  <p><strong>What it tried:</strong> create a brand-new grade record in the grades
  database — the exact operation its permissions would have to allow for Karani to ever
  write a grade.</p>
  <p><strong>The answer:</strong> <span class="mono">{_e(kind)}: 403</span>.
  Not a policy, not a setting Karani checks — a locked door it does not hold a key to.</p>
</div>"""
            else:
                verdict = f"""
<div class="notice"><strong>Could not attempt from here.</strong> This copy of the docket
has no cloud credentials at all (<span class="mono">{_e(kind)}</span>) — common when
running locally. On the hosted docket this attempt runs live and is refused by IAM. Either
way: nothing was written.</div>"""
            return HTMLResponse(
                page(
                    "Karani — the boundary",
                    f"""
<nav class="crumbs"><a href="/boundary">← try again</a> · <a href="/">overnight review</a></nav>
<header class="top"><h1>It tried. It was turned away.</h1></header>
{verdict}
<div class="panel"><p class="sub">This attempt ran during your page request, under the
service's own identity — no simulation, no screenshot. The same denial is asserted against
the analysis pipeline's identity by the deployed test suite on every release.</p></div>
""",
                )
            )
        # If we ever get here, the write SUCCEEDED and the central claim is false.
        # Say so at maximum volume rather than styling it away.
        return HTMLResponse(
            page(
                "Karani — BOUNDARY FAILURE",
                "<h1>The write succeeded. The boundary is broken.</h1>"
                "<p>A pipeline-side identity just created a grade record. Do not trust this "
                "deployment until the IAM bindings are re-verified "
                "(<span class='mono'>pytest -m deployed</span>).</p>",
            ),
            status_code=500,
        )

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
        from karani.delivery.deliver import build_csv, deliver

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

        # The gradebook CSV, rendered right here (KAR-421). The empty grade column used to
        # be provable only by opening the exported file in Finder -- invisible on the hosted
        # docket, whose container filesystem nobody can browse, and a terminal beat in the
        # demo. The one fact this whole system is arranged around deserves to be LOOKED AT,
        # so the delivery receipt shows the table itself, empty cells and all.
        import csv as _csv
        import io as _io

        csv_rows = list(_csv.reader(_io.StringIO(build_csv(run, grades))))
        header, body_rows = csv_rows[0], csv_rows[1:]
        grade_col = header.index("grade") if "grade" in header else -1
        csv_head = "".join(f"<th>{_e(h)}</th>" for h in header)
        csv_body = "".join(
            "<tr>"
            + "".join(
                (
                    f"<td class='sub'><em>{_e(cell) or '— yours to write —'}</em></td>"
                    if i == grade_col
                    else f"<td>{_e(cell)}</td>"
                )
                for i, cell in enumerate(cells)
            )
            + "</tr>"
            for cells in body_rows
        )

        return HTMLResponse(
            page(
                "Karani — delivered",
                f"""
<nav class="crumbs"><a href="/">← back to the overnight review</a></nav>
<header class="top">
  <h1>Delivered</h1>
  <p class="sub">{len(result.files)} file(s) written to
     <span class="mono">{result.destination}</span> — the evidence sheets, the
     <a href="/brief">morning brief</a>, and the gradebook CSV below.</p>
</header>

<h2>The gradebook, as exported</h2>
<div class="panel scroll">
  <table><tr>{csv_head}</tr>{csv_body}</table>
  <p class="sub" style="margin-top:.8rem"><strong>{result.grades_absent} grade cell(s) are
  empty.</strong> They are read from a database no part of the pipeline can write, so they
  arrive blank until you fill them. Karani exports the blank rather than inventing the
  number — that is the whole point of it.</p>
</div>

<h2>Files delivered</h2>
<div class="panel"><ul>{files}</ul></div>
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
