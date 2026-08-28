"""Regression checks for the release-facing claim verifier."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_release_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/release_check.py", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_local_release_claims_are_consistent():
    """The checked local claims cannot silently drift back to the old IAM model."""
    result = run_release_check()
    assert result.returncode == 0, result.stdout + result.stderr


def test_submission_check_refuses_to_pass_without_live_evidence():
    """Missing deployment and publication proof remains a visible release blocker."""
    result = run_release_check("--submission")
    assert result.returncode == 1
    assert "Devpost draft still contains" in result.stdout
    assert "required submission metric is absent" in result.stdout


def test_static_docket_renderer_accepts_the_documented_relative_output_path(tmp_path):
    """The public static export completes when invoked exactly as the docs show it."""
    out = tmp_path / "static-docket"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_static_docket.py"),
            "--out",
            str(out.relative_to(tmp_path)),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "index.html").exists()
    assert (out / "challenge.html").exists()
