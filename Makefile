.DEFAULT_GOAL := help
SHELL := /bin/bash
PY ?= python3.12
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help venv demo demo-live demo-emulator record-cache docket-golden dev-run compliance test lint fmt scale release-check submission-check bootstrap deploy static-docket clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"

venv: $(BIN)/python ## Create the virtualenv and install pinned dependencies

demo: $(BIN)/python ## Full pipeline over committed fixtures. Zero credentials, zero Java, zero Docker.
	KARANI_STORE_BACKEND=local \
	KARANI_SOURCE=local \
	KARANI_CACHE_BACKEND=file \
	KARANI_MODEL_BACKEND=cache \
	$(BIN)/python -m karani.cli run --source fixtures --offline --open-docket

record-cache: $(BIN)/python ## Run live ONCE and record every model response into fixtures/cache/.
	@echo "This makes real Vertex AI calls and costs money (roughly the price of one run)."
	@echo "Afterwards, commit fixtures/cache/ so that 'make demo' works offline for everyone."
	@echo ""
	KARANI_STORE_BACKEND=local \
	KARANI_MODEL_BACKEND=vertex \
	$(BIN)/python -m karani.cli run --source fixtures --live --run-id run-golden
	@echo ""
	@echo "Now: git add fixtures/cache && git commit -m 'chore: record the offline demo cache'"

demo-live: $(BIN)/python ## Same pipeline against real Vertex AI. Costs money. Requires credentials.
	KARANI_STORE_BACKEND=$${KARANI_STORE_BACKEND:-local} \
	KARANI_MODEL_BACKEND=vertex \
	$(BIN)/python -m karani.cli run --source fixtures --live

demo-emulator: $(BIN)/python ## Higher-fidelity demo against the Firestore emulator. Requires Java.
	@command -v java >/dev/null 2>&1 || { \
	  echo "ERROR: the Firestore emulator requires a Java runtime, which was not found."; \
	  echo "       Install a JDK, or run 'make demo' which needs neither Java nor Docker."; \
	  exit 1; }
	docker compose up -d firestore-emulator
	KARANI_STORE_BACKEND=emulator \
	KARANI_MODEL_BACKEND=cache \
	$(BIN)/python -m karani.cli run --source fixtures --offline
	docker compose down

docket-golden: $(BIN)/python ## Serve the docket over the recorded live run. No model, no cloud.
	KARANI_STORE_BACKEND=local \
	$(BIN)/python -m karani.cli docket --golden fixtures/recorded-run.jsonl

dev-run: $(BIN)/python ## Pipeline over the 3-submission dev subset — the only set used for iteration.
	KARANI_STORE_BACKEND=local \
	KARANI_MODEL_BACKEND=$${KARANI_MODEL_BACKEND:-cache} \
	$(BIN)/python -m karani.cli run --source fixtures/dev

compliance: $(BIN)/python ## Diff requirement IDs in PRD §4 against the §2 matrix. Nonzero on any orphan.
	$(BIN)/python scripts/compliance.py

release-check: $(BIN)/python ## Check local, submission-facing claims that must remain true before release.
	$(BIN)/python scripts/release_check.py

submission-check: $(BIN)/python ## Fail until Devpost copy, hosted proof, and publication requirements are complete.
	$(BIN)/python scripts/release_check.py --submission

bootstrap: ## Provision Karani cloud prerequisites; requires PROJECT=<Google Cloud project>. Creates resources.
	@test -n "$(PROJECT)" || { echo "usage: make bootstrap PROJECT=<project-id>"; exit 2; }
	./scripts/bootstrap_gcp.sh "$(PROJECT)"

deploy: ## Deploy Karani to Cloud Run; requires PROJECT=<Google Cloud project>. Creates or updates resources.
	@test -n "$(PROJECT)" || { echo "usage: make deploy PROJECT=<project-id>"; exit 2; }
	./scripts/deploy.sh "$(PROJECT)"

static-docket: $(BIN)/python ## Render the committed recorded run as a static docket under out/static-docket.
	$(BIN)/python scripts/render_static_docket.py --out out/static-docket

scale: $(BIN)/python ## Regenerate the ~150-submission scale corpus from the committed seed.
	$(BIN)/python scripts/gen_scale_corpus.py --out fixtures/scale

test: $(BIN)/python ## Full suite: replay, misattribution, collision, kill, and IAM negative tests.
	$(BIN)/pytest

lint: $(BIN)/python ## Ruff + mypy
	$(BIN)/ruff check src tests scripts
	$(BIN)/mypy

fmt: $(BIN)/python ## Format
	$(BIN)/ruff format src tests scripts
	$(BIN)/ruff check --fix src tests scripts

clean: ## Remove local run state. Never touches fixtures or the golden log.
	rm -rf .karani out .pytest_cache .ruff_cache .mypy_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
