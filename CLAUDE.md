# CLAUDE.md

**Source of truth: [docs/SPEC.md](docs/SPEC.md).** Read §0 (working agreement) before any change.
Stop at every 🛑 CHECKPOINT and report to the user.

- Project state: [docs/PROGRESS.md](docs/PROGRESS.md). Update it at the end of every session.
- Decisions not covered by the spec: [docs/DECISIONS.md](docs/DECISIONS.md).

## Environment
- WSL2 (Ubuntu 22.04) on Windows 11. 16 GB RAM (WSL capped at 10 GB), i7-1355U, no discrete GPU.
- Python 3.12 venv at `.venv/` (`make venv`). Docker Engine runs inside WSL.
- Ollama runs natively on **Windows**; WSL reaches it at `localhost:11434` (mirrored networking).
- A native Postgres 14 also listens on 5432, so the compose Postgres 16 is on **5433**.

## Commands
- `make test`: unit tests (no DB, no Ollama). Real-data tests run when `data/raw/` exists.
- `make up` and then `make ingest SCALE=s25`: full ingestion for one scale.
- `make test-integration`: needs `make up` plus a loaded scale (`INTEGRATION_SCALE`, default s25).
- `make lint` / `make fmt`.

## Layout
- `core/`: settings, scale windows, DB connection factories (shared by all phases).
- `ingest/`: `raw` → `profile`/`validate` → `stage` → `load_pg`/`load_neo4j` → `parity`.
  The CLI is `python -m ingest <cmd> --scale <s>`.
- Label hygiene is structural: labels live only in `data/staged/<scale>/labels/`, and the loaders
  read only the agent-facing Parquet files.

## Rules
- Feature branches only, with small commits. Never commit data, `.env` or results JSONL.
- No paid LLM APIs. Only local Ollama.
