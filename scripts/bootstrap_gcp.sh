#!/usr/bin/env bash
# Provision everything Karani needs on Google Cloud (KAR-506, KAR-330).
#
# Pairs with teardown.sh, and the pair exists before any billable endpoint is created
# (KAR-008). Anything this script creates, teardown.sh removes -- if you add a resource here
# and not there, you have added an unmetered overnight cost.
#
# Idempotent: safe to re-run. Every create is guarded by an existence check, so a partial
# failure is recovered by running it again rather than by hand-repairing state.
#
#   ./scripts/bootstrap_gcp.sh asili-61171
set -euo pipefail

PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
REGION="${KARANI_REGION:-us-central1}"

if [[ -z "$PROJECT" ]]; then
  echo "usage: $0 <project-id>" >&2
  exit 2
fi

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
have() { gcloud "$@" >/dev/null 2>&1; }

say "Project $PROJECT (region $REGION)"
gcloud config set project "$PROJECT" >/dev/null

# --- billing, checked first ------------------------------------------------------------
# Checked before anything else because every step below fails in a different and less
# obvious way when billing is off, and the resulting error messages point at the wrong thing.
if ! gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null | grep -qi true; then
  cat >&2 <<EOF

ERROR: billing is not enabled on $PROJECT.

Vertex AI, Cloud Run, Firestore and Cloud Scheduler all require it. Link a billing
account and re-run:

  gcloud billing accounts list
  gcloud billing projects link $PROJECT --billing-account=<ACCOUNT_ID>

EOF
  exit 1
fi

# --- APIs ------------------------------------------------------------------------------
say "Enabling APIs"
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  modelarmor.googleapis.com \
  --project="$PROJECT" || true

# --- model preflight -------------------------------------------------------------------
# Pinned model IDs are claims about the world, so they are verified here rather than at the
# first live call. The PRD pinned `gemini-3.5-pro`, which does not exist; that failure would
# otherwise have surfaced after the architecture was frozen.
say "Verifying pinned model IDs resolve"
# The venv interpreter when it exists: the system python3 may be outside the supported
# range, and a preflight that fails on ITS dependencies reports a model problem that isn't.
PREFLIGHT_PY="python3"
[[ -x .venv/bin/python ]] && PREFLIGHT_PY=".venv/bin/python"
if [[ -f src/karani/cli.py ]]; then
  GOOGLE_CLOUD_PROJECT="$PROJECT" PYTHONPATH=src "$PREFLIGHT_PY" -m karani.cli preflight || {
    echo "WARNING: a pinned model ID did not resolve against live Vertex." >&2
    echo "         If both lines above say DefaultCredentialsError, the models are fine and" >&2
    echo "         the problem is auth: run 'gcloud auth login' and re-run this script." >&2
  }
fi

# --- Firestore: TWO databases, and the separation is the security boundary --------------
#
# `datastore.entities.create` cannot be scoped to a collection. Granting it over a database
# authorises creating a document ANYWHERE in that database, and the Firestore server SDK is
# authorised by IAM alone -- Security Rules are not evaluated for server clients. So events
# and grades in one database means any identity that can append an event can create a grade.
#
# This was a real defect in this script: the role below used to be bound at project scope with
# --condition=None, which made "no pipeline identity can write grades/" false on the deployed
# path while every local test still passed.
say "Firestore databases"
EVENTS_DB="${KARANI_EVENTS_DB:-karani-events}"
GRADES_DB="${KARANI_GRADES_DB:-karani-grades}"

for db in "$EVENTS_DB" "$GRADES_DB"; do
  if ! gcloud firestore databases describe --database="$db" >/dev/null 2>&1; then
    gcloud firestore databases create --database="$db" \
      --location="$REGION" --type=firestore-native
    echo "created $db"
  else
    echo "$db exists"
  fi
  # No silent failure here. This exact line used to end in '2>/dev/null || true', the
  # update failed on an older gcloud, and both databases sat unprotected while the teardown
  # docs described the two deliberate commands needed to delete them.
  gcloud firestore databases update --database="$db" --delete-protection >/dev/null || {
    echo "ERROR: could not enable delete protection on $db." >&2
    echo "       Run 'gcloud components update' and re-run this script." >&2
    exit 1
  }
done

# Firestore security rules, via the Firebase Rules REST API with the gcloud CLI's own
# token. This block used to shell out to `firebase deploy`, which requires an interactive
# `firebase login` -- a second, browser-based OAuth flow for the SAME identity gcloud
# already holds. On deploy day the operator had never run it on that machine, the CLI
# refused, and this script correctly halted with the browser write path unguarded -- but
# halted on a dependency the deploy never needed. scripts/deploy_firestore_rules.py does
# what the CLI does in two HTTP calls per database, reads the database-to-rules mapping
# from the same firebase.json, and verifies each release by reading it back.
say "Firestore security rules"
[[ -f firebase.json ]] || { echo "ERROR: firebase.json missing; rules would target (default)." >&2; exit 1; }
gcloud services enable firebaserules.googleapis.com --project="$PROJECT" >/dev/null
python3 scripts/deploy_firestore_rules.py "$PROJECT" \
  || { echo "ERROR: firestore rules failed to deploy. The browser write path is UNGUARDED." >&2; exit 1; }

# --- custom role: create + get, no update, no delete -----------------------------------
say "Custom IAM role (append-only)"
if ! have iam roles describe karaniAppendOnly --project="$PROJECT"; then
  gcloud iam roles create karaniAppendOnly --project="$PROJECT" \
    --file=deploy/iam/karani-append-only.yaml
else
  gcloud iam roles update karaniAppendOnly --project="$PROJECT" \
    --file=deploy/iam/karani-append-only.yaml >/dev/null
fi

# --- per-stage service accounts --------------------------------------------------------
# One identity per stage, each scoped to what that stage does and nothing else. The scopes
# are the claim; deploy/iam/negative-matrix.yaml is the proof, and tests/test_iam_boundary.py
# is what checks the proof against reality.
say "Service accounts"
create_sa() {
  local name="$1" desc="$2"
  if ! have iam service-accounts describe "${name}@${PROJECT}.iam.gserviceaccount.com"; then
    gcloud iam service-accounts create "$name" --display-name="$desc"
  fi
}
create_sa karani-ingest   "Karani ingest (source read only)"
create_sa karani-analysis "Karani analysis (Vertex invoke + event create)"
create_sa karani-render   "Karani render (event read + artifact write)"
create_sa karani-delivery "Karani delivery (one Drive folder, write only)"
create_sa karani-docket   "Karani docket service"

# Unconditional binding, for roles that carry no Firestore reach.
bind() {
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$1@${PROJECT}.iam.gserviceaccount.com" \
    --role="$2" --condition=None >/dev/null
}

# Firestore binding, CONDITIONED on the events database.
#
# This condition is the thing that makes the grades boundary real. Without it the append-only
# role authorises `db.collection("grades").document(uuid).create({...})`, because
# datastore.entities.create is database-wide and Security Rules do not apply to server SDKs.
bind_events_db() {
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$1@${PROJECT}.iam.gserviceaccount.com" \
    --role="projects/$PROJECT/roles/karaniAppendOnly" \
    --condition="expression=resource.name.startsWith('projects/${PROJECT}/databases/${EVENTS_DB}'),title=karani-events-db-only,description=Append-only access is limited to the events database; the grades database is unreachable from any pipeline identity." \
    >/dev/null
}

bind_events_db karani-analysis
bind_events_db karani-render
bind_events_db karani-docket
bind karani-analysis "roles/aiplatform.user"
bind karani-ingest   "roles/storage.objectViewer"

# Cloud Scheduler authenticates AS karani-analysis to POST jobs:run. Without run.invoker that
# POST returns 403 and the nightly trigger never fires -- the unattended-overnight premise
# fails on night one, silently, with the schedule looking perfectly healthy in the console.
bind karani-analysis "roles/run.invoker"

# Deliberately NOT bound anywhere: any role granting datastore.entities.update or .delete;
# any Firestore role without the events-database condition; any access at all to
# "$GRADES_DB". The instructor's authenticated session is the only writer of grades, and it
# authenticates as a person rather than as a service account.
#
# If a deploy fails for want of a permission, stop and say so -- do not widen a scope to
# unblock it. A failing deploy with correct permissions beats a passing deploy with wrong ones.

say "Verifying the grades boundary actually holds"
cat <<EOF
The binding above is conditioned on:
  projects/${PROJECT}/databases/${EVENTS_DB}

Grades live in a different database (${GRADES_DB}) that no pipeline identity is bound to at
all. Prove it before recording the denial beat -- a beat that films the wrong operation
"proves" a boundary the policy does not enforce:

  GOOGLE_CLOUD_PROJECT=${PROJECT} .venv/bin/pytest -m deployed -v

The decisive test attempts a FRESH-DOCUMENT create against the grades database, which is
exactly the operation datastore.entities.create authorises. A .set() on a fixed document ID
is not the same test and can pass while a create still succeeds.
EOF

# --- Model Armor -----------------------------------------------------------------------
say "Model Armor template"
if gcloud model-armor templates describe karani-injection --location="$REGION" >/dev/null 2>&1; then
  echo "template exists"
elif gcloud model-armor templates create karani-injection \
      --location="$REGION" \
      --pi-and-jailbreak-filter-settings-enforcement=enabled \
      --pi-and-jailbreak-filter-settings-confidence-level=LOW_AND_ABOVE 2>/dev/null; then
  echo "created"
else
  # KAR-311's honest-fallback branch. Never ship a local implementation under a Google
  # product's name; run it under its own name and record the finding.
  cat <<EOF
NOTE: the managed Model Armor API is not available on this account tier.
      Karani will run its own pattern scanner, under its own name, with an
      offline label on every detection it produces.
      Record this in docs/FINDINGS.md. Do not describe the fallback as Model Armor.
EOF
fi

# --- storage ---------------------------------------------------------------------------
say "Buckets"
for b in "karani-${PROJECT}-ingest" "karani-${PROJECT}-artifacts"; do
  gcloud storage buckets describe "gs://$b" >/dev/null 2>&1 \
    || gcloud storage buckets create "gs://$b" --location="$REGION" --uniform-bucket-level-access
done

# --- budget alerts ---------------------------------------------------------------------
say "Budget alerts"
cat <<EOF
Budget alerts at \$25 / \$50 / \$100 / \$140 must be armed in the console -- the API needs
billing-account-level permissions this script deliberately does not assume:

  https://console.cloud.google.com/billing/budgets

Alerts lag by up to 24 hours. During recording week, read actual billing daily rather than
trusting them.
EOF

say "Done"
cat <<EOF
Next:
  make deploy         build and deploy the job, the docket service, and the Scheduler trigger
  ./scripts/teardown.sh $PROJECT     remove everything billable
EOF
