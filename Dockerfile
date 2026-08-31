# One image, two entrypoints: the Cloud Run Job (`karani-run`) and the Cloud Run service
# (`karani-docket`). Same image deliberately — a docket built from a different commit than the
# pipeline that produced the run it displays would be a docket showing you something other
# than what happened.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependencies in their own layer, from the pinned lockfile, so a source edit does not
# reinstall the world and so the deployed dependency set is the tested one.
COPY pyproject.toml requirements.lock ./
RUN pip install --upgrade pip \
 && pip install -r requirements.lock

COPY src/ ./src/
COPY fixtures/ ./fixtures/
COPY deploy/ ./deploy/
# The corpus generator plus its seed inputs. The scale corpus itself is gitignored (it is a
# pure function of the committed seed), so a scale run inside this container regenerates it
# with `--generate-scale-corpus` rather than expecting a directory only a dev machine has.
COPY scripts/gen_scale_corpus.py ./scripts/gen_scale_corpus.py

# Non-root. The container reads submissions and writes events; it has no reason to be root,
# and the delivery identity in particular touches an instructor's real Drive.
RUN useradd --create-home --uid 10001 karani \
 && chown -R karani:karani /app
USER karani

EXPOSE 8080

# Default: the docket service. The Job overrides this with `run --live`.
# No --golden: the docket serves the latest run from whatever store is configured, which
# on Cloud Run is Firestore -- so the hosted UI shows what the nightly Job produced. The
# committed recorded run is the fallback when the store has no runs yet.
CMD ["python", "-m", "karani.cli", "docket", "--port", "8080"]
