"""KAR-102, KAR-312, KAR-313 — the identity boundary.

Three surfaces, three different enforcement mechanisms, and each is asserted where it
actually applies:

    schema / interface   always runs; proves the shape             (this file, unmarked)
    Firestore rules      `emulator` mark; proves the browser path
    custom IAM role      `deployed` mark; proves the server path

**The distinction that makes this worth reading.** A Firestore emulator does not evaluate
IAM. A service account using the server SDK does not evaluate Firestore rules. Each mechanism
is invisible to the other's test, so a suite that ran only one of them would report a green
boundary with one side wide open — and it is the *server* side that the pipeline actually
uses.

The unmarked tests here run on every clean clone and prove what can be proven without a
cloud: that no verdict-shaped field exists, that the store interface has no mutation methods,
and that the negative-test matrix is complete and internally consistent. The marked tests are
the ones that prove the claim on the deployed path, and KAR-312's is also a camera beat: the
denial is filmed, because an emulator test is evidence and footage is proof.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path

import pytest
import yaml

from karani.schema.observation import BANNED_FIELD_NAMES, Observation
from karani.store import EventStore
from karani.store.local import LocalEventStore

MATRIX = Path(__file__).resolve().parent.parent / "deploy" / "iam" / "negative-matrix.yaml"
ROLE = Path(__file__).resolve().parent.parent / "deploy" / "iam" / "karani-append-only.yaml"


@pytest.fixture(scope="module")
def matrix() -> dict:
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


# --- always-on: the parts that need no cloud ------------------------------------------


def test_custom_role_grants_no_mutation_permission():
    """Property: the append-only role cannot mutate, by omission rather than by policy.

    Asserted against the role definition itself, so that someone who adds
    `datastore.entities.update` "temporarily, to unblock a deploy" fails a test rather than
    only a code review. AGENTS.md's standing rule is that a failing deploy with correct
    permissions beats a passing deploy with wrong ones; this is that rule with teeth.
    """
    role = yaml.safe_load(ROLE.read_text(encoding="utf-8"))
    granted = set(role["includedPermissions"])

    forbidden = {
        "datastore.entities.update",
        "datastore.entities.delete",
        "datastore.databases.delete",
    }
    assert not (granted & forbidden), f"append-only role grants mutation: {granted & forbidden}"
    assert "datastore.entities.create" in granted
    assert "datastore.entities.get" in granted


def test_every_service_account_is_denied_grade_writes(matrix):
    """Property (KAR-312): no pipeline identity can write `grades/`. Every one. No exception.

    Checked exhaustively rather than for the obvious candidates. The interesting entry is
    `karani-docket`: the docket is *where an instructor ratifies*, which makes it the identity
    someone would most plausibly grant grade-write access to as a convenience. The ratification
    write goes through the instructor's own authenticated session instead.
    """
    for account in matrix["service_accounts"]:
        denied = {row["operation"] for row in account["denied"]}
        grade_denials = {op for op in denied if "grade" in op}
        assert grade_denials, f"{account['id']} does not assert any grades denial"


def test_the_analysis_identity_denies_the_operation_that_was_actually_granted(matrix):
    """Property: the matrix names the CREATE, not the vague "write".

    This is the finding that made the whole boundary false for a while. The append-only role
    grants `datastore.entities.create`, which cannot be scoped to a collection, so the
    operation to deny is specifically *creating a fresh document* — not "writing a grade",
    which a `.set()` test can satisfy for the wrong reason.

    Asserting the matrix uses the precise name keeps the test suite and the threat aligned: a
    future editor who softens this back to "write_grade" fails here.
    """
    analysis = next(a for a in matrix["service_accounts"] if a["id"] == "karani-analysis")
    denied = {row["operation"] for row in analysis["denied"]}

    assert "firestore.create_grade_fresh_document" in denied, (
        "the analysis identity must deny creating a FRESH grade document -- that is the "
        "operation datastore.entities.create authorises"
    )
    assert "firestore.create_anything_in_grades_database" in denied, (
        "the boundary is the database, not a collection name"
    )


def test_analysis_identity_is_denied_event_mutation(matrix):
    """Property (KAR-102): the identity that writes the log cannot rewrite it."""
    analysis = next(a for a in matrix["service_accounts"] if a["id"] == "karani-analysis")
    denied = {row["operation"] for row in analysis["denied"]}
    assert {"firestore.update_event", "firestore.delete_event"} <= denied


def test_render_identity_cannot_call_a_model(matrix):
    """Property: `render()` derives artifacts; it cannot generate them.

    If the render identity could call Vertex, the fold could produce content instead of
    folding it, and the replay test's byte-stability guarantee would stop meaning anything —
    it would be asserting that a generated artifact happened to be reproducible.
    """
    render = next(a for a in matrix["service_accounts"] if a["id"] == "karani-render")
    assert "vertex.generate_content" in {row["operation"] for row in render["denied"]}


def test_delivery_identity_cannot_read_the_instructors_drive(matrix):
    """Property (KAR-406): the identity that touches real Drive is scoped to what it created.

    `drive.file`, not `drive`. This is the only identity that reaches an instructor's actual
    account, so its scope is the one worth being pedantic about.
    """
    delivery = next(a for a in matrix["service_accounts"] if a["id"] == "karani-delivery")
    assert "drive.file" in delivery["granted"]
    assert "drive" not in delivery["granted"]
    assert "drive.list_all_files" in {row["operation"] for row in delivery["denied"]}


def test_every_denial_states_why(matrix):
    """Property: the matrix is an argument, not a checklist.

    A denial with no reason is a denial nobody can evaluate, and it is the first one someone
    removes when a deploy fails.
    """
    for account in matrix["service_accounts"]:
        for row in account["denied"]:
            assert row.get("why", "").strip(), f"{account['id']}/{row['operation']} has no reason"


def test_the_schema_itself_has_no_grade_field():
    """Property: layer 1. There is nowhere to put a verdict, before any identity is involved.

    The IAM boundary is layer 2 and this is layer 1, and layer 1 holds even if layer 2 is
    misconfigured: a correctly-permissioned write of a grade still has no field to write into.
    """
    assert Observation.banned_fields_present() == set()
    assert not (set(Observation.model_fields) & BANNED_FIELD_NAMES)


def test_store_interface_cannot_express_a_mutation():
    """Property: the code cannot call what does not exist."""
    for surface in (EventStore, LocalEventStore):
        for method in ("update", "delete", "set", "replace", "merge"):
            assert not hasattr(surface, method), f"{surface.__name__}.{method} exists"


# --- emulator: the browser path --------------------------------------------------------


@pytest.mark.emulator
def test_client_surface_rejects_event_update():
    """Property (KAR-102, browser half): Firestore rules refuse update and delete.

    Covers the path a service account never takes. Run with `make demo-emulator` or with
    FIRESTORE_EMULATOR_HOST set.
    """
    pytest.importorskip("google.cloud.firestore")
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST is not set")

    from google.api_core.exceptions import PermissionDenied
    from google.cloud import firestore

    client = firestore.Client(project="karani-local")
    doc = client.collection("runs").document("run-emulator").collection("events").document("e1")
    doc.create({"step": "RunStarted", "run_id": "run-emulator"})

    # `PermissionDenied` specifically. This previously read
    # `pytest.raises((PermissionDenied, Exception))`, which a connection refusal, a
    # `TypeError`, or a failed import all satisfy — so the test asserted that *something went
    # wrong*, not that the rule denied the write. An emulator that was never reachable would
    # have passed it, which is the one outcome it exists to rule out.
    with pytest.raises(PermissionDenied):
        doc.update({"step": "Tampered"})


# --- deployed: the server path ---------------------------------------------------------


@pytest.mark.deployed
def test_deployed_pipeline_sa_cannot_CREATE_a_fresh_grade_document():
    """Property (KAR-312): the operation the granted permission would authorise is denied.

    **This test replaced one that could pass while the boundary was broken**, and the
    replacement is the whole point.

    The old test did `grades.document("s01").set({...})` and expected `PermissionDenied`. A
    `.set()` with no precondition is an upsert, so it can require *update* permission — which
    the append-only role withholds — and be denied for a reason that has nothing to do with
    the boundary being tested. Meanwhile `datastore.entities.create` **is** granted, and
    `.create()` on a document ID that does not exist yet is exactly the operation it
    authorises. The green check was measuring the wrong thing.

    So this attempts a create, on a random document ID that certainly does not exist, in the
    grades database. If the boundary holds, it is denied. If it succeeds, a pipeline identity
    just wrote a grade and the central claim of this project is false.

    Do not record the `PERMISSION_DENIED` camera beat until this passes: filming the wrong
    operation demonstrates a denial that proves nothing.
    """
    pytest.importorskip("google.cloud.firestore")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        pytest.skip("GOOGLE_CLOUD_PROJECT is not set")

    from google.api_core.exceptions import NotFound, PermissionDenied
    from google.cloud import firestore

    from karani.config import GRADES_DATABASE

    victim = f"probe-{uuid.uuid4().hex}"

    try:
        client = firestore.Client(project=project, database=GRADES_DATABASE)
    except NotFound:
        pytest.skip(f"grades database {GRADES_DATABASE} does not exist yet; run bootstrap_gcp.sh")

    with pytest.raises((PermissionDenied, NotFound)):
        client.collection("grades").document(victim).create(
            {"grade": "A", "actor": "pipeline", "student_id": victim}
        )


@pytest.mark.deployed
def test_deployed_pipeline_sa_cannot_create_anywhere_in_the_grades_database():
    """Property: the denial is the database, not one collection's name.

    An identity blocked from `grades/` but able to create in `grades_v2/` or `scratch/` on the
    same database has not been blocked from anything -- it has been blocked from a string. The
    boundary is the database binding, so this probes a collection nobody has ever named.
    """
    pytest.importorskip("google.cloud.firestore")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        pytest.skip("GOOGLE_CLOUD_PROJECT is not set")

    from google.api_core.exceptions import NotFound, PermissionDenied
    from google.cloud import firestore

    from karani.config import GRADES_DATABASE

    try:
        client = firestore.Client(project=project, database=GRADES_DATABASE)
    except NotFound:
        pytest.skip(f"grades database {GRADES_DATABASE} does not exist yet")

    with pytest.raises((PermissionDenied, NotFound)):
        client.collection(f"anything-{uuid.uuid4().hex}").document("x").create({"grade": "A"})


@pytest.mark.deployed
def test_deployed_pipeline_sa_CAN_still_create_events():
    """Property: the condition restricts the boundary without breaking the pipeline.

    The complement that keeps the two tests above honest. A binding that denied everything
    would pass both of them and ship a system that cannot run. This asserts the events
    database is still writable by the identity that has to write it.
    """
    pytest.importorskip("google.cloud.firestore")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        pytest.skip("GOOGLE_CLOUD_PROJECT is not set")

    from google.cloud import firestore

    from karani.config import EVENTS_DATABASE

    client = firestore.Client(project=project, database=EVENTS_DATABASE)
    probe = f"probe-{uuid.uuid4().hex}"
    client.collection("runs").document(probe).collection("events").document("e1").create(
        {"step": "RunStarted", "run_id": probe}
    )


@pytest.mark.deployed
def test_deployed_analysis_sa_cannot_mutate_an_event():
    """Property (KAR-102, the half that matters): append-only holds against the server SDK."""
    pytest.importorskip("google.cloud.firestore")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        pytest.skip("GOOGLE_CLOUD_PROJECT is not set")

    from google.api_core.exceptions import PermissionDenied
    from google.cloud import firestore

    from karani.config import EVENTS_DATABASE

    client = firestore.Client(project=project, database=EVENTS_DATABASE)
    doc = client.collection("runs").document("run-iam-probe").collection("events").document("probe")
    with contextlib.suppress(Exception):
        # Already present from an earlier probe run is fine; the update below is the assertion.
        doc.create({"step": "RunStarted", "run_id": "run-iam-probe"})

    with pytest.raises(PermissionDenied):
        doc.update({"step": "Tampered"})
