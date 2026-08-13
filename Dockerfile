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

# Non-root. The container reads submissions and writes events; it has no reason to be root,
# and the delivery identity in particular touches an instructor's real Drive.
RUN useradd --create-home --uid 10001 karani \
 && chown -R karani:karani /app
USER karani

EXPOSE 8080

# Default: the docket service. The Job overrides this with `run --live`.
CMD ["python", "-m", "karani.cli", "docket", "--golden", "fixtures/golden-log.jsonl", "--port", "8080"]
