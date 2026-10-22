# Progress

_Last updated: 2026-10-22_

## Phase 0: Repo audit ✅
- [x] Inventory existing code: unrelated GraphRAG/EDGAR project, no AML code
- [x] Environment check: no Docker, no Ollama, 16 GB RAM, CPU only
- [x] Checkpoint 0 approved: delete old code, Docker in WSL, Ollama on Windows, WSL 10 GB

## Phase 1: Ingestion 🚧
- [x] Remove legacy files (commit `db7b207`)
- [x] Tooling: `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`
- [x] `core/`: settings, scales, DB connections
- [x] `ingest/raw`, `profile`, `validate`: all §2 facts reproduced on the real data
- [x] `ingest/stage`: Parquet for all 4 scales (37 MB), labels kept separate
- [x] `ingest/load_pg`: schema, COPY, indexes, read-only agent role (**not yet run against a DB**)
- [x] `ingest/load_neo4j`: batched UNWIND, constraint, relationship indexes (**not yet run**)
- [x] `ingest/parity`: 24 three-way checks (**not yet run against DBs**)
- [x] Unit tests: 45 passing; integration tests written (label hygiene, read-only, parity)
- [ ] **Blocked:** user installs Docker Engine in WSL and runs `wsl --shutdown` so `.wslconfig` takes effect
- [ ] `make up`, then `make ingest-all` (4 scales); parity green for all 4
- [ ] `make test-integration` green
- [ ] Commit `data/reports/{data_profile,scales,parity,load_times}.json`
- [ ] 🛑 Checkpoint 1

## Phase 2: Ground truth and tasks ⏳
## Phase 3: Agent and Ollama ⏳
- [ ] User installs Ollama on Windows
## Phase 4: Full runs ⏳
## Phase 5: Analysis and write-up ⏳
