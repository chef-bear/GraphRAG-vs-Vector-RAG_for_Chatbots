PY ?= .venv/bin/python
# interpreter used to create the venv; must be 3.11+ (e.g. make venv BOOTSTRAP_PY=~/miniforge3/bin/python)
BOOTSTRAP_PY ?= python3
SCALE ?= s25
SCALES := s25 s50 s100 full

.PHONY: venv up down validate stage ingest ingest-all parity test test-integration lint fmt \
        gen-tasks verify-gt bench analyze

venv:
	$(BOOTSTRAP_PY) -m venv .venv && $(PY) -m pip install -e '.[dev]'

up:
	docker compose up -d --wait

down:
	docker compose down

validate:
	$(PY) -m ingest validate

stage:
	$(PY) -m ingest stage --scale $(SCALE)

# validate -> stage -> load Postgres -> load Neo4j -> parity
ingest:
	$(PY) -m ingest all --scale $(SCALE)

# Neo4j holds one scale at a time, so this ends with `full` loaded in Neo4j.
ingest-all:
	for s in $(SCALES); do $(PY) -m ingest all --scale $$s || exit 1; done

parity:
	$(PY) -m ingest parity --scale $(SCALE)

test:
	$(PY) -m pytest

test-integration:
	$(PY) -m pytest -m integration

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

fmt:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

SEED ?= 42

gen-tasks:
	for s in $(SCALES); do $(PY) -m bench.generate --scale $$s --seed $(SEED) || exit 1; done

# Neo4j must hold SCALE (make ingest SCALE=...); Postgres has every scale.
verify-gt:
	$(PY) -m bench.verify --scale $(SCALE)

bench analyze:
	@echo "'$@' is not implemented yet (see docs/PROGRESS.md)"; exit 1
