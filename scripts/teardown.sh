#!/usr/bin/env bash
# Remove everything bootstrap_gcp.sh created that costs money (KAR-008, KAR-506).
#
# Exists as a pair with bootstrap_gcp.sh, and existed before the first billable endpoint was
# created. The rule it enforces: nothing runs overnight unmetered. The Gemma endpoint proof
# (KAR-623) in particular is created and torn down inside an hour.
#
# Deliberately does NOT delete Firestore data or the event log. Those are the evidence a run
# happened, they cost effectively nothing at this scale, and a teardown script that could
# erase the audit record is a teardown script that will one day erase the audit record.
#
#   ./scripts/teardown.sh asili-61171
#   ./scripts/teardown.sh asili-61171 --include-buckets
set -euo pipefail

PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
REGION="${KARANI_REGION:-us-central1}"
INCLUDE_BUCKETS="${2:-}"

if [[ -z "$PROJECT" ]]; then
  echo "usage: $0 <project-id> [--include-buckets]" >&2
  exit 2
fi

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
gcloud config set project "$PROJECT" >/dev/null

say "Cloud Scheduler"
gcloud scheduler jobs delete karani-nightly --location="$REGION" --quiet 2>/dev/null || true

say "Cloud Run"
gcloud run jobs delete karani-run --region="$REGION" --quiet 2>/dev/null || true
gcloud run services delete karani-docket --region="$REGION" --quiet 2>/dev/null || true

say "Vertex endpoints"
# The Gemma proof endpoint is the one that bills by the hour whether or not it serves a
# request, which is exactly why KAR-008 requires this script to exist before it is created.
for ep in $(gcloud ai endpoints list --region="$REGION" \
            --filter='displayName~karani' --format='value(name)' 2>/dev/null || true); do
  echo "deleting endpoint $ep"
  for model in $(gcloud ai endpoints describe "$ep" --region="$REGION" \
                 --format='value(deployedModels.id)' 2>/dev/null || true); do
    gcloud ai endpoints undeploy-model "$ep" --region="$REGION" \
      --deployed-model-id="$model" --quiet 2>/dev/null || true
  done
  gcloud ai endpoints delete "$ep" --region="$REGION" --quiet 2>/dev/null || true
done

# The container images. This was the gap: deploy.sh creates an Artifact Registry repository
# and pushes an image to it on every deploy, and teardown mentioned it nowhere -- neither
# removing it nor listing it as retained. Image storage is billed, so a script whose stated
# acceptance criterion is "leaves nothing billable" was leaving the one thing that
# accumulates with every redeploy.
say "Artifact Registry"
gcloud artifacts repositories delete karani --location="$REGION" --quiet 2>/dev/null || true

say "Model Armor template"
gcloud model-armor templates delete karani-injection --location="$REGION" --quiet 2>/dev/null || true

if [[ "$INCLUDE_BUCKETS" == "--include-buckets" ]]; then
  say "Buckets"
  for b in "karani-${PROJECT}-ingest" "karani-${PROJECT}-artifacts"; do
    gcloud storage rm -r "gs://$b" --quiet 2>/dev/null || true
  done
else
  say "Buckets retained (pass --include-buckets to remove)"
fi

say "Remaining billable resources"
echo "Cloud Run services:"; gcloud run services list --region="$REGION" --format='value(name)' 2>/dev/null || true
echo "Cloud Run jobs:";     gcloud run jobs list --region="$REGION" --format='value(name)' 2>/dev/null || true
echo "Vertex endpoints:";   gcloud ai endpoints list --region="$REGION" --format='value(displayName)' 2>/dev/null || true
echo "Artifact repos:";     gcloud artifacts repositories list --location="$REGION" --format='value(name)' 2>/dev/null || true
echo "Firestore databases:"; gcloud firestore databases list --format='value(name)' 2>/dev/null || true

cat <<EOF

Retained on purpose:
  Firestore databases and the event log -- the record that a run happened. These are listed
                                     above so the retention is a decision you can see rather
                                     than an omission you have to notice. Delete-protection is
                                     on; removing them takes two deliberate commands:
                                       gcloud firestore databases update --database=karani-events --no-delete-protection
                                       gcloud firestore databases delete --database=karani-events
  Service accounts and the custom role -- free, and re-creating them changes their identities
  Budget alerts                      -- keep them armed

Verify against actual billing rather than this output:
  https://console.cloud.google.com/billing
EOF
