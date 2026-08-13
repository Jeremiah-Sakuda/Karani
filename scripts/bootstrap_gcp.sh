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
if command -v python3 >/dev/null && [[ -f src/karani/cli.py ]]; then
  GOOGLE_CLOUD_PROJECT="$PROJECT" PYTHONPATH=src python3 -m karani.cli preflight || {
    echo "WARNING: a pinned model ID did not resolve. Fix config.py before deploying." >&2
  }
fi

# --- Firestore -------------------------------------------------------------------------
say "Firestore"
if ! have firestore databases describe --database='(default)'; then
  gcloud firestore databases create --location="$REGION" --type=firestore-native
fi
gcloud firestore databases update --database='(default)' --delete-protection 2>/dev/null || true

# Firestore security rules are deployed by the Firebase CLI, not by gcloud -- there is no
# `gcloud firestore rules` command group. An earlier version of this script called one and
# swallowed the failure, so it reported success while the rules were never deployed: the
# browser-path half of the append-only guarantee silently absent on a project that looked
# fully provisioned.
if [[ -f deploy/firestore.rules ]]; then
  if command -v firebase >/dev/null 2>&1; then
    firebase deploy --only firestore:rules --project "$PROJECT" \
      || { echo "ERROR: firestore rules failed to deploy. The browser write path is UNGUARDED." >&2; exit 1; }
  else
    cat >&2 <<'RULES'

ACTION REQUIRED -- Firestore rules are NOT deployed.

deploy/firestore.rules guards the browser write path (KAR-102, KAR-312). The custom IAM
role covers service accounts; these rules cover everything else, and neither substitutes
for the other.

  npm i -g firebase-tools && firebase login
  firebase deploy --only firestore:rules --project PROJECT_ID

Not deploying them leaves grades/ writable from a browser session. This script will not
pretend otherwise.
RULES
  fi
fi

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

bind() {
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$1@${PROJECT}.iam.gserviceaccount.com" \
    --role="$2" --condition=None >/dev/null
}
bind karani-analysis "projects/$PROJECT/roles/karaniAppendOnly"
bind karani-analysis "roles/aiplatform.user"
bind karani-render   "projects/$PROJECT/roles/karaniAppendOnly"
bind karani-docket   "projects/$PROJECT/roles/karaniAppendOnly"
bind karani-ingest   "roles/storage.objectViewer"

# Deliberately NOT bound anywhere: any role granting datastore.entities.update or .delete,
# and any role granting write access to grades/. If a deploy fails for want of a permission,
# stop and say so -- do not widen a scope to unblock it.

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
