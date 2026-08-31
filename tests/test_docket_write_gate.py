"""Anonymous visitors may read the docket; they may not write to it (KAR-414).

The deployed docket runs with `--allow-unauthenticated`, deliberately: the public challenge
box is a submission asset and has to work with no login and no quota. But that had been
silently extended to unauthenticated **writes**. Anyone who found the URL could POST to
`/edit` and append an `ObservationEditedByHuman` event carrying `actor: "instructor"`, or
POST to `/ratify` and trigger a Drive write plus a CSV export.

The hole sat underneath an identity story elaborate enough to have its own diagram — five
service accounts, an IAM-conditioned binding, a separate grades database — with no check at
all on the layer that actually accepts writes. Least privilege below, an open door above.

Gate design, stated plainly because this project is careful about not overstating mechanisms:
a shared secret for one instructor's own docket, exchanged once at `/unlock` for an HttpOnly
cookie. Not an identity system. When the token is unset the endpoints stay open, which is
what keeps `make demo` and the recorded video unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from karani.docket.server import build_app
from karani.render import render
from karani.store.local import LocalEventStore, read_jsonl_log

REPO = Path(__file__).resolve().parent.parent
RECORDED = REPO / "fixtures" / "recorded-run.jsonl"
RUN_ID = "run-recorded-p2"
TOKEN = "test-instructor-token-2f9c"


def _client(tmp_path: Path, token: str | None, monkeypatch) -> TestClient:
    if token is None:
        monkeypatch.delenv("KARANI_INSTRUCTOR_TOKEN", raising=False)
    else:
        monkeypatch.setenv("KARANI_INSTRUCTOR_TOKEN", token)
    store = LocalEventStore(tmp_path / "events")
    for event in read_jsonl_log(RECORDED):
        store.create(event)
    app = build_app(render(RUN_ID, store.read_run(RUN_ID)), store=store)
    # https, because the unlock cookie is `Secure` and a test client on http would
    # silently drop it -- making the gate look broken for the wrong reason.
    return TestClient(app, follow_redirects=False, base_url="https://testserver")


@pytest.fixture
def locked(tmp_path: Path, monkeypatch) -> TestClient:
    return _client(tmp_path, TOKEN, monkeypatch)


@pytest.fixture
def open_docket(tmp_path: Path, monkeypatch) -> TestClient:
    return _client(tmp_path, None, monkeypatch)


def _an_observation(client: TestClient) -> tuple[str, str]:
    run = client.app.state.karani["run"]
    sheet = run.sheets[0]
    return str(sheet.observations[0]["observation_id"]), sheet.student_id


def _edit(client: TestClient, oid: str, sid: str):
    return client.post(
        "/edit",
        data={
            "observation_id": oid,
            "student_id": sid,
            "text": "Anonymous rewrite.",
            "edit_reason": "not the instructor",
        },
    )


def _edit_events(client: TestClient) -> list:
    store = client.app.state.karani["store"]
    return [e for e in store.read_run(RUN_ID) if e.step.value == "ObservationEditedByHuman"]


# --- reads stay public, which is the point of the deployment being unauthenticated -------


@pytest.mark.parametrize("path", ["/", "/challenge", "/student/s01", "/appeal/s01"])
def test_reads_need_no_token(locked: TestClient, path: str):
    assert locked.get(path).status_code == 200


def test_the_challenge_box_answers_without_a_token(locked: TestClient):
    response = locked.post("/challenge", data={"ask": "what grade would s01 get?"})
    assert response.status_code == 200
    assert "no field for what you asked for" in response.text


# --- writes do not -----------------------------------------------------------------------


def test_an_anonymous_edit_appends_nothing(locked: TestClient):
    """The regression. This used to append an event with actor 'instructor'."""
    oid, sid = _an_observation(locked)
    before = len(_edit_events(locked))
    _edit(locked, oid, sid)
    assert len(_edit_events(locked)) == before


def test_an_anonymous_ratify_is_refused(locked: TestClient):
    assert locked.post("/ratify", data={"student_ids": "s01"}).status_code == 403


def test_a_wrong_token_does_not_unlock(locked: TestClient):
    assert locked.get("/unlock", params={"token": "guess"}).status_code == 403
    oid, sid = _an_observation(locked)
    before = len(_edit_events(locked))
    _edit(locked, oid, sid)
    assert len(_edit_events(locked)) == before


def test_the_right_token_unlocks_editing(locked: TestClient):
    assert locked.get("/unlock", params={"token": TOKEN}).status_code == 303
    oid, sid = _an_observation(locked)
    before = len(_edit_events(locked))
    assert _edit(locked, oid, sid).status_code == 303
    assert len(_edit_events(locked)) == before + 1


def test_the_token_is_not_readable_from_the_page(locked: TestClient):
    """It is a shared secret; rendering it into HTML would defeat the whole arrangement."""
    locked.get("/unlock", params={"token": TOKEN})
    for path in ("/", "/student/s01", "/challenge"):
        assert TOKEN not in locked.get(path).text


def test_the_unlock_cookie_is_httponly(locked: TestClient):
    header = locked.get("/unlock", params={"token": TOKEN}).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "secure" in header


# --- unconfigured stays open, so the demo and the video are unchanged ---------------------


def test_with_no_token_configured_editing_is_open(open_docket: TestClient):
    oid, sid = _an_observation(open_docket)
    before = len(_edit_events(open_docket))
    assert _edit(open_docket, oid, sid).status_code == 303
    assert len(_edit_events(open_docket)) == before + 1


# --- recording a grade: the one write Karani makes on a person's behalf (KAR-415) --------


def test_recording_a_grade_requires_the_token(locked: TestClient):
    response = locked.post("/grade", data={"student_id": "s01", "grade": "B+"})
    assert response.status_code == 403


def test_a_grade_for_an_unknown_submission_is_refused(locked: TestClient):
    locked.get("/unlock", params={"token": TOKEN})
    response = locked.post("/grade", data={"student_id": "nobody", "grade": "B+"})
    assert response.status_code == 404


def test_locally_the_grade_write_reports_that_it_did_not_happen(locked: TestClient):
    """No grades database exists locally, and Karani says so rather than appearing to succeed.

    An instructor who believes a grade was recorded and finds an empty CSV column a week
    later is worse off than one who is told immediately.
    """
    locked.get("/unlock", params={"token": TOKEN})
    response = locked.post("/grade", data={"student_id": "s01", "grade": "B+"})
    assert response.status_code in (502, 503)
    assert "nothing was written" in response.text.lower() or "refused" in response.text.lower()


def test_there_is_no_path_from_an_observation_to_a_grade():
    """The invariant the endpoint must not quietly weaken.

    `Grade` takes its value as typed input. If a future change adds "suggest a grade from the
    evidence", it has to write that function — and writing it is the moment someone should
    stop. This asserts no such function exists.
    """
    import ast
    from pathlib import Path as _Path

    import karani.grades as grades_module

    tree = ast.parse(_Path(grades_module.__file__).read_text(encoding="utf-8"))

    # Imports, not prose. The module's own docstring says the words "Observation" and
    # "Grade" in the sentence explaining that no path between them exists, so a substring
    # search fails on the documentation that states the invariant.
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            if node.module:
                imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not any("observation" in name.lower() for name in imported), (
        f"karani.grades imports {sorted(imported)}; there must be no constructor path from "
        "an observation to a grade"
    )

    # And no function anywhere takes an observation and returns a grade.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = [a.arg.lower() for a in node.args.args]
            assert not any("observation" in a for a in args), (
                f"karani.grades.{node.name} accepts an observation"
            )


# --- the boundary page (KAR-420) and the scholarship exhibit (KAR-422) -------------------


def test_boundary_page_serves_without_any_token(locked: TestClient):
    response = locked.get("/boundary")
    assert response.status_code == 200
    assert "Can Karani write a grade?" in response.text


def test_boundary_attempt_with_no_credentials_reports_honestly(locked: TestClient):
    """Locally there are no cloud credentials; the page must say the attempt could not run
    from here rather than pretending a denial happened. Nothing may read as success."""
    response = locked.post("/boundary")
    assert response.status_code == 200
    assert "Could not attempt from here" in response.text
    assert "nothing was written" in response.text.lower()
    assert "BOUNDARY FAILURE" not in response.text


def test_scholarship_exhibit_serves_and_is_read_only(locked: TestClient):
    overview = locked.get("/scholarship")
    assert overview.status_code == 200
    assert "different job, the same clerk" in overview.text.lower()
    # internal navigation stays inside the exhibit
    assert "href='/scholarship/a01'" in overview.text.replace('"', "'")

    sheet = locked.get("/scholarship/a02")
    assert sheet.status_code == 200
    assert "nothing to cite" in sheet.text.lower()

    # the exhibit accepts no writes, with or without the token
    locked.get("/unlock", params={"token": TOKEN})
    assert locked.post("/scholarship-readonly").status_code == 403


def test_scholarship_findings_show_the_second_reader(locked: TestClient):
    sheet = locked.get("/scholarship/a01").text
    assert '"second_reader": true' in sheet or "&quot;second_reader&quot;: true" in sheet
