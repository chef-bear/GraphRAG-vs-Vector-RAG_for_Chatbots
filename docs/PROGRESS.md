# Progress

_Last updated: 2026-10-22_

## Phase 0: Repo audit ✅
- [x] Inventory existing code: unrelated GraphRAG/EDGAR project, no AML code
- [x] Environment check: no Docker, no Ollama, 16 GB RAM, CPU only
- [x] Checkpoint 0 approved: delete old code, Docker in WSL, Ollama on Windows, WSL 10 GB

## Phase 1: Ingestion ✅ (awaiting Checkpoint 1 review)
- [x] Remove legacy files (commit `db7b207`)
- [x] Tooling: `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`
- [x] `core/`: settings, scales, DB connections
- [x] `ingest/raw`, `profile`, `validate`: all §2 facts reproduced on the real data
- [x] `ingest/stage`: Parquet for all 4 scales, labels kept separate
- [x] `ingest/load_pg`: COPY, indexes, read-only agent role with a 30 s timeout
- [x] `ingest/load_neo4j`: batched UNWIND, constraint, relationship indexes (full load about 85 s)
- [x] `ingest/parity`: 24 three-way checks pass at **all 4 scales**
- [x] Docker Engine in WSL; `make up` brings up healthy PG16 and Neo4j 5.26
- [x] `make test` (45) and `make test-integration` (8, at s25 and full) green; lint clean
- [x] Reports committed: `data/reports/{data_profile,scales,parity,load_times}.json`
- [ ] 🛑 Checkpoint 1: user review

Current DB state: Postgres has `fraud_s25`, `fraud_s50`, `fraud_s100` and `fraud_full`. Neo4j holds **full**.

## Phase 2: Ground truth and tasks ✅ (awaiting Checkpoint 2 review)
- [x] `bench/answers.py` + `bench/score.py`: 7 answer types, canonical forms, every §6.2 rule (unit-tested per type)
- [x] `bench/algorithms.py`: Python ground truth (pandas, no DB), unit-tested on hand-built graphs
- [x] `bench/families/`: 10 families across 5 levels; L5 seeds kept only if the stated typology reproduces the labels
- [x] `bench/reference/`: SQL + Cypher for every family (L5 families share `ring.*`)
- [x] `bench/generate.py` (`make gen-tasks`): 116 tasks per scale, 16 negative controls, deterministic, no duplicates
- [x] `bench/verify.py` (`make verify-gt SCALE=...`): **116/116 three-way agreement at all 4 scales** (acceptance only needed s50)
- [x] `make test` 120 passed; `make test-integration` 9 passed (at full); lint clean
- [ ] 🛑 Checkpoint 2: user review of samples; decide §11.4 (watchlist) and §11.5 (union ground truth)

Current DB state: Neo4j holds **full**.

## Phase 3: Agent and Ollama ⏳
- [ ] User installs Ollama on Windows
## Phase 4: Full runs ⏳
## Phase 5: Analysis and write-up ⏳
