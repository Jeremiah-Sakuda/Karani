#!/usr/bin/env bash
# Iterate a runtime prompt against the dev fixtures and report the result.
#
# The rule this enforces (AGENTS.md): every runtime prompt -- analysis, validator feedback,
# entailment question, triage -- is iterated **against Gemini**, never tuned by feel and never
# tuned against a different model. A prompt tuned against one model and shipped against
# another has a measured acceptance rate describing a system that is not the one running.
#
# Iterates over fixtures/dev/ (3 submissions), never the full 15. The full set is reserved for
# integration runs and the recording; spending it on prompt iteration makes the integration
# numbers meaningless, because the prompt was fitted to them.
#
#   ./scripts/prompt_bench.sh
#   ./scripts/prompt_bench.sh --label v2
set -euo pipefail

cd "$(dirname "$0")/.."

LABEL="${2:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ID="bench-${LABEL}"

if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  cat >&2 <<'EOF'
ERROR: GOOGLE_CLOUD_PROJECT is not set.

prompt_bench makes real Vertex AI calls, deliberately. Benching a runtime prompt against a
cached or stubbed response measures the cache, not the prompt.

  gcloud auth application-default login
  export GOOGLE_CLOUD_PROJECT=<project>
EOF
  exit 2
fi

echo "benching the current prompt version against fixtures/dev/ on Gemini"
echo "  run id   ${RUN_ID}"
echo "  project  ${GOOGLE_CLOUD_PROJECT}"
echo

KARANI_STORE_BACKEND=local \
KARANI_MODEL_BACKEND=vertex \
PYTHONPATH=src .venv/bin/python -m karani.cli run \
  --source fixtures/dev --live --run-id "${RUN_ID}"

ARTIFACT="out/${RUN_ID}/rendered.json"
[[ -f "$ARTIFACT" ]] || { echo "no artifact at $ARTIFACT" >&2; exit 1; }

PYTHONPATH=src .venv/bin/python - "$ARTIFACT" "$LABEL" <<'PY'
import json
import pathlib
import sys

artifact = json.loads(pathlib.Path(sys.argv[1]).read_text())
label = sys.argv[2]
claims = artifact.get("claims", [])

# First-attempt acceptance: of the observations that were accepted, how many needed no retry.
# Reported with its denominator, because "92%" of twelve observations and "92%" of twelve
# hundred are different claims and only one of them is worth publishing.
accepted = [c for c in claims if c.get("kind") == "evidence" and not c.get("needs_human")]
first_try = [c for c in accepted if int(c.get("attempts", 1)) <= 1]
absent = [c for c in claims if c.get("kind") == "no_evidence"]
escalated = [c for c in claims if c.get("needs_human")]

rate = f"  ({len(first_try) / len(accepted):.0%})" if accepted else ""
print()
print(f"label                {label}")
print(f"observations         {len(claims)}")
print(f"accepted             {len(accepted)}")
print(f"  first attempt      {len(first_try)}{rate}")
print(f"no_evidence          {len(absent)}")
print(f"needs_human          {len(escalated)}")
print()
print("Write these into docs/metrics.json with the measurement method named, or they do not")
print("exist: a number that was benched but never recorded cannot be published anywhere.")
PY
