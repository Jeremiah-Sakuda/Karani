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


@pytest.fixture(autouse=True, scope="session")
def _offline_environment() -> None:
    saved = {var: os.environ.pop(var, None) for var in _CREDENTIAL_VARS}
    # Force the offline backends regardless of what the operator's shell had set, so that
    # `make demo-live`'s environment cannot leak into a test run.
    os.environ["KARANI_STORE_BACKEND"] = "local"
    os.environ["KARANI_MODEL_BACKEND"] = "cache"
    yield
    for var, value in saved.items():
        if value is not None:
            os.environ[var] = value
