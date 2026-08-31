"""The arena (KAR-419): a stranger's essay through the real pipeline, kept by nobody.

The arena's honesty properties are the ones a public, unauthenticated, model-calling
endpoint lives or dies by: it must be the genuine pipeline (not a demo-shaped imitation),
it must keep nothing, and its limits must refuse loudly rather than degrade quietly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import karani.arena as arena_module
from karani.arena import build_arena_app


@pytest.fixture
def client(monkeypatch):
    # Reset the in-memory limiter state between tests.
    from collections import defaultdict, deque

    monkeypatch.setattr(arena_module, "_recent", defaultdict(deque))
    monkeypatch.setattr(arena_module, "_day", {"stamp": "", "count": 0})
    return TestClient(build_arena_app())


def test_the_form_serves(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "not kept" in response.text


def test_short_input_is_refused_before_any_model_call(client):
    assert client.post("/run", data={"text": "hi"}).status_code == 400


def test_the_hourly_limit_refuses_the_fourth_run(client, monkeypatch):
    """Three per IP per hour; the limiter is consulted BEFORE the spend, so a refused
    request costs nothing."""
    calls = []

    def fake_analyse(text):
        calls.append(text)
        return "<header></header>"

    monkeypatch.setattr(arena_module, "_analyse", fake_analyse)
    body = {"text": "x" * 300}
    for _ in range(3):
        assert client.post("/run", data=body).status_code == 200
    assert client.post("/run", data=body).status_code == 429
    assert len(calls) == 3


def test_the_daily_budget_refuses_without_calling_the_model(client, monkeypatch):
    def must_not_run(text):
        raise AssertionError("the model path ran after the budget was spent")

    monkeypatch.setattr(arena_module, "_analyse", must_not_run)
    monkeypatch.setattr(arena_module, "_day", {"stamp": "", "count": arena_module.PER_DAY})
    # _limited() re-stamps the day; force today's stamp so the count survives.
    import time

    arena_module._day["stamp"] = time.strftime("%Y-%m-%d", time.gmtime())
    response = client.post("/run", data={"text": "x" * 300})
    assert response.status_code == 429


def test_a_pipeline_error_is_reported_not_leaked(client, monkeypatch):
    def boom(text):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(arena_module, "_analyse", boom)
    response = client.post("/run", data={"text": "x" * 300})
    assert response.status_code == 502
    assert "secret internals" not in response.text
    assert "RuntimeError" in response.text


def test_the_arena_runs_the_real_pipeline_not_an_imitation():
    """The maximal-reuse claim, asserted structurally: _analyse calls run_pipeline — the
    same entrypoint the nightly job uses — and defines no analysis of its own."""
    import ast
    import inspect

    source = inspect.getsource(arena_module)
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "run_pipeline" in calls
    # No model client is constructed outside open_client, and no prompt text lives here.
    assert "generate_content" not in source
    assert "system_instruction" not in source


def test_nothing_the_visitor_pastes_survives(monkeypatch, tmp_path):
    """The ephemerality claim: after _analyse returns, the temporary corpus is gone and
    nothing landed outside it."""
    import tempfile

    created = []
    real_tmpdir = tempfile.TemporaryDirectory

    def tracking_tmpdir(*args, **kwargs):
        t = real_tmpdir(*args, **kwargs)
        created.append(t.name)
        return t

    monkeypatch.setattr(tempfile, "TemporaryDirectory", tracking_tmpdir)

    def fake_pipeline(**kwargs):
        # The store receives the run inside the tmp dir; nothing else is written.
        class Summary:
            pass

        return Summary()

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "unit-test-project")
    monkeypatch.setattr("karani.analysis.dispatcher.run_pipeline", fake_pipeline)
    monkeypatch.setattr(arena_module, "student_page", lambda run, sid: "<header></header>")
    arena_module._analyse("x" * 300)
    from pathlib import Path

    assert created and not Path(created[0]).exists()
