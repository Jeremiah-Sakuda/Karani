#!/usr/bin/env bash
# Deploy the Cloud Run Job, the docket service, and the Scheduler trigger (KAR-410, KAR-411).
#
# The Scheduler job is deployed FIRST and can be deployed against a trivial job body, because
# KAR-410's acceptance criterion is "execution history shows >=7 nightly runs by recording
# day" and that clock only starts once the schedule exists. It is the one deliverable that
# cannot be recovered by working harder later: a schedule created on the 23rd cannot show
# seven nights of history on the 24th, whatever the feature progress.
#
#   ./scripts/deploy.sh asili-61171
#   ./scripts/deploy.sh asili-61171 --scheduler-only     # start the history clock today
set -euo pipefail

PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
REGION="${KARANI_REGION:-us-central1}"
MODE="${2:-}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/karani/karani:latest"

[[ -z "$PROJECT" ]] && { echo "usage: $0 <project-id> [--scheduler-only]" >&2; exit 2; }

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
gcloud config set project "$PROJECT" >/dev/null

# --- Scheduler first, always -----------------------------------------------------------
say "Cloud Scheduler (nightly 03:00)"
if ! gcloud scheduler jobs describe karani-nightly --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs create http karani-nightly \
    --location="$REGION" \
    --schedule="0 3 * * *" \
    --time-zone="America/Chicago" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/karani-run:run" \
    --http-method=POST \
    --oauth-service-account-email="karani-analysis@${PROJECT}.iam.gserviceaccount.com" \
    --description="Karani nightly evidence run"
  echo "created -- the KAR-410 execution-history clock starts now"
else
  echo "exists; history clock already running"
fi

if [[ "$MODE" == "--scheduler-only" ]]; then
  say "Scheduler-only mode: stopping here"
  gcloud scheduler jobs describe karani-nightly --location="$REGION" \
    --format='value(schedule,state,lastAttemptTime)'
  exit 0
fi

# --- image -----------------------------------------------------------------------------
say "Building image"
gcloud artifacts repositories describe karani --location="$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create karani --repository-format=docker --location="$REGION"

# The lockfile is generated rather than committed stale, so the image's dependency set is the
# one the tests ran against.
[[ -f requirements.lock ]] || {
  echo "requirements.lock missing; generating"
  pip freeze > requirements.lock 2>/dev/null || true
}

gcloud builds submit --tag "$IMAGE" .

# --- job -------------------------------------------------------------------------------
say "Cloud Run Job (analysis fan-out)"
JOB_ARGS=(
  --image="$IMAGE"
  --region="$REGION"
  --service-account="karani-analysis@${PROJECT}.iam.gserviceaccount.com"
  --tasks=1
  --parallelism=1
  --max-retries=1
  --task-timeout=1800s
  --memory=2Gi
  --cpu=2
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_GENAI_USE_VERTEXAI=true,KARANI_STORE_BACKEND=firestore,KARANI_MODEL_BACKEND=vertex"
  --command="python"
  --args="-m,karani.cli,run,--source,fixtures,--live,--workers,15"
)
if gcloud run jobs describe karani-run --region="$REGION" >/dev/null 2>&1; then
  gcloud run jobs update karani-run "${JOB_ARGS[@]}"
else
  gcloud run jobs create karani-run "${JOB_ARGS[@]}"
fi

# --- docket service --------------------------------------------------------------------
say "Cloud Run service (docket)"
# The docket is deployed --allow-unauthenticated on purpose: the public challenge box is the
# most direct demonstration this project has, and it must work with no login and no quota.
#
# But reads and writes are not the same request. /edit appends events to the log and /ratify
# writes to the instructor's Drive, and both were reachable by anyone who found the URL --
# under an identity story with five service accounts and its own diagram. So the deployed
# service carries an instructor token; reads stay open, writes need one visit to
# /unlock?token=...
#
# Reused across deploys when one already exists, so a redeploy does not silently invalidate
# the URL the instructor has. Generated locally and never echoed to the build log.
EXISTING_TOKEN=$(
  gcloud run services describe karani-docket --region="$REGION" --format=json 2>/dev/null \
    | python3 -c '
import json, sys
try:
    spec = json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0]
except Exception:
    sys.exit(0)
for var in spec.get("env", []):
    if var.get("name") == "KARANI_INSTRUCTOR_TOKEN":
        print(var.get("value", ""))
' 2>/dev/null || true
)
INSTRUCTOR_TOKEN="${EXISTING_TOKEN:-$(openssl rand -hex 24)}"

# min-instances=0: the docket must survive to Oct 1 without accumulating idle cost, and a
# cold start on a static pre-rendered golden run is a second, not a minute.
gcloud run deploy karani-docket \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="karani-docket@${PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=4 \
  --memory=1Gi \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},KARANI_STORE_BACKEND=firestore,KARANI_INSTRUCTOR_TOKEN=${INSTRUCTOR_TOKEN}" \
  --port=8080

URL=$(gcloud run services describe karani-docket --region="$REGION" --format='value(status.url)')

say "Deployed"
cat <<EOF
docket        $URL
unlock        $URL/unlock?token=$INSTRUCTOR_TOKEN
              ^ the only place this token is printed. Reads are public; editing and
                ratification need this link once, then a session cookie for 12 hours.
challenge     $URL/challenge     (free, unmetered, no login -- KAR-412)
job           gcloud run jobs execute karani-run --region=$REGION
scheduler     gcloud scheduler jobs describe karani-nightly --location=$REGION

Verify the docket loads LOGGED OUT, in a private window, from a different network.
"It worked on my machine while signed in" is not the check.
EOF
