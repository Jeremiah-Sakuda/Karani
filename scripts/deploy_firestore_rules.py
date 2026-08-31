#!/usr/bin/env python3
"""Deploy Firestore security rules to the named databases, without the Firebase CLI.

Exists because the deploy failed on deadline day. `bootstrap_gcp.sh` called
`firebase deploy --only firestore:rules`, which requires an interactive `firebase login` --
a browser OAuth flow the operator had never run on that machine -- and the script correctly
refused to continue with the browser write path unguarded. Everything else in this project
authenticates with the gcloud CLI's own token; the rules deploy was the one step that
demanded a second, different login for the same identity.

The Firebase Rules REST API accepts that same token. So this does what the CLI does --
create a ruleset from the source file, point the database's release at it -- with two HTTP
calls per database and no additional authentication. The mapping of database to rules file
is read from `firebase.json`, which stays the single source of truth so the two deploy
paths can never disagree about which file guards which database.

Releases for named databases are `projects/{p}/releases/cloud.firestore/{database}`. Getting
that name wrong is the failure firebase.json exists to prevent: rules that deploy cleanly to
`(default)` -- a database Karani does not use -- guard nothing while reporting success. After
each deploy, the release is read back and its ruleset compared to the one just created, so
"deployed" here means verified-live rather than accepted-for-processing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = "https://firebaserules.googleapis.com/v1"


def _token() -> str:
    try:
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        sys.exit(
            f"cannot obtain a gcloud access token ({type(exc).__name__}); run: gcloud auth login"
        )
    if not token:
        sys.exit("gcloud returned an empty access token; run: gcloud auth login")
    return token


def _call(method: str, url: str, token: str, project: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            # The Rules API requires a quota project; without this header the same token
            # that works everywhere else is refused here, which is exactly the kind of
            # one-surface difference that produced this script in the first place.
            "x-goog-user-project": project,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read() or b"{}")


def deploy(project: str) -> int:
    config = json.loads((REPO / "firebase.json").read_text(encoding="utf-8"))
    targets = config.get("firestore", [])
    if not targets:
        sys.exit("firebase.json lists no firestore targets; refusing to report success")

    token = _token()
    failures = 0

    for target in targets:
        database = target["database"]
        rules_path = REPO / target["rules"]
        source = rules_path.read_text(encoding="utf-8")

        ruleset = _call(
            "POST",
            f"{API}/projects/{project}/rulesets",
            token,
            project,
            {"source": {"files": [{"name": rules_path.name, "content": source}]}},
        )
        ruleset_name = ruleset["name"]

        release_name = f"projects/{project}/releases/cloud.firestore/{database}"
        try:
            _call(
                "POST",
                f"{API}/projects/{project}/releases",
                token,
                project,
                {"name": release_name, "rulesetName": ruleset_name},
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 409:  # 409: release exists -- update it instead
                raise
            _call(
                "PATCH",
                f"{API}/{release_name}",
                token,
                project,
                {"release": {"name": release_name, "rulesetName": ruleset_name}},
            )

        # Read back rather than trust the write. "Deployed" means the live release points at
        # the ruleset containing these bytes, not that an API call returned 200.
        live = _call("GET", f"{API}/{release_name}", token, project)
        if live.get("rulesetName") == ruleset_name:
            print(f"  OK   {database:<15} release -> {ruleset_name.rsplit('/', 1)[-1]}")
        else:
            failures += 1
            print(f"  FAIL {database:<15} release points at {live.get('rulesetName')}")

    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: deploy_firestore_rules.py <project-id>")
    sys.exit(deploy(sys.argv[1]))
