"""Test environment.

The default suite is the one a stranger runs on a clean clone: no credentials, no emulator,
no model calls, no money. Tests that need any of those carry a marker (`deployed`, `live`,
`emulator`) and are excluded by pyproject's default `addopts`.

Credentials are stripped for the whole session rather than per-test. A leaked credential in
the ambient environment would not fail anything loudly — it would let an offline-by-design
code path quietly succeed by going online, and the test asserting it was offline would still
be green. Removing them at session scope is the only way that assertion means anything.
"""

from __future__ import annotations

import os

import pytest

_CREDENTIAL_VARS = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "FIRESTORE_EMULATOR_HOST",
    "CLOUDSDK_CORE_PROJECT",
)


# The markers whose tests NEED the credentials the offline suite strips.
_CREDENTIALED_MARKERS = ("deployed", "live", "emulator")


def _run_wants_credentials(config: pytest.Config) -> bool:
    """True when the operator explicitly selected a credentialed marker.

    Found on deploy day, by the release gate never running: this fixture stripped
    `GOOGLE_CLOUD_PROJECT` for every session, including `pytest -m deployed` -- so the exact
    command that bootstrap_gcp.sh, the README, and the run-book all print skipped all four
    boundary tests with "GOOGLE_CLOUD_PROJECT is not set", while the operator had set it on
    the command line. A gate that cannot be run as documented protects nothing, and its
    skips read enough like success that nobody had noticed the denial had never once been
    asserted against a real deployment.

    The stripping stays absolute for the default suite -- that rationale is unchanged. It is
    keyed on the -m expression: a marker name appearing without "not " in front of it means
    the operator asked for the credentialed tests, so the credentials they set must survive.
    The default addopts is `not deployed and not live and not emulator`, where every mention
    is negated, so a plain `pytest` still strips everything.
    """
    markexpr = config.getoption("-m", default="") or ""
    return any(
        marker in markexpr and f"not {marker}" not in markexpr for marker in _CREDENTIALED_MARKERS
    )


@pytest.fixture(autouse=True, scope="session")
def _offline_environment(request: pytest.FixtureRequest) -> None:
    if _run_wants_credentials(request.config):
        yield
        return

    saved = {var: os.environ.pop(var, None) for var in _CREDENTIAL_VARS}
    # Force the offline backends regardless of what the operator's shell had set, so that
    # `make demo-live`'s environment cannot leak into a test run.
    os.environ["KARANI_STORE_BACKEND"] = "local"
    os.environ["KARANI_MODEL_BACKEND"] = "cache"
    yield
    for var, value in saved.items():
        if value is not None:
            os.environ[var] = value
