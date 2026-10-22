# Decisions

Format: date — decision. *Why.* Alternatives considered.

## Checkpoint 0 (user decisions)

- **2026-10-22 — Reuse this repo, delete the old GraphRAG/EDGAR code.** The user chose this; the old code is recoverable from git history (commit before `db7b207`). *Alternatives:* a fresh repo, or a `legacy/` folder.
- **2026-10-22 — Docker Engine inside WSL, not Docker Desktop.** The user chose this.
- **2026-10-22 — Ollama runs natively on Windows.** The model's RAM then comes from Windows rather than WSL's 10 GB, which leaves room for Neo4j and Postgres. WSL uses `networkingMode=mirrored` (in `C:\Users\squis\.wslconfig`), so `OLLAMA_HOST=http://localhost:11434` works from WSL. *Alternative:* Ollama inside WSL.
- **2026-10-22 — WSL memory capped at 10 GB** (`.wslconfig`). The user approved this. The machine has 16 GB RAM, an i7-1355U and no discrete GPU, so inference runs on the CPU.
- **2026-10-22 — Matrix-size trimming is deferred to Checkpoint 3.** The user wants to see real timings first.

## Phase 1

- **2026-10-22 — Compose Postgres on host port 5433.** A native PG 14 already uses 5432. *Alternative:* stop the native service.
- **2026-10-22 — Memory: PG `shared_buffers=1GB`; Neo4j heap 1.5 GB and page cache 1 GB.** The full graph store is a few hundred MB, so 1 GB of page cache holds it entirely. Postgres also gets the OS page cache. Both engines can keep the full dataset in memory, which keeps the comparison fair. All values are configurable in `.env`.
- **2026-10-22 — Image tags: `postgres:16` and `neo4j:5.26-community`.** 5.26 is the 5.x LTS release. It supports `CALL (x) { … } IN TRANSACTIONS`, which the loader uses.
- **2026-10-22 — Neo4j loads with batched `UNWIND` at every scale, including `full`.** The spec suggests `neo4j-admin import` for `full`. That needs the database stopped and a separate offline CSV path, which means two loaders to keep in parity. Batched UNWIND with a unique-constraint lookup keeps one code path. **Confirmed by measurement:** `full` loads in about 85 s (`data/reports/load_times.json`), so `neo4j-admin import` isn't needed. *Alternative:* `neo4j-admin database import full` for `full` only.
- **2026-10-22 — Added a shared `core/` package** (settings, scales, DB connections). Phases 1–3 all need these, and keeping them out of `ingest/` stops `agent/` and `bench/` from depending on the ingestion code.
- **2026-10-22 — Labels are staged separately** in `data/staged/<scale>/labels/`. The loaders only read the agent-facing Parquet files, so a label can't reach a DB by accident. `LABEL_NAMES` in `ingest/stage.py` is the one list that the hygiene tests check against.
- **2026-10-22 — Parity is three-way: staged Parquet, Postgres and Neo4j.** The spec only asks for PG to equal Neo4j. Comparing against the staged data as well catches loader bugs that affect both DBs the same way. There are 2 count checks and 22 checksum checks.
- **2026-10-22 — How some §2 facts are measured.** The spec's wording leaves these open; these definitions reproduce its numbers exactly:
  - *Closed cycle*: the pattern's edges form one simple directed loop. Each account sends exactly once and receives exactly once, with no self-loops.
  - *Time-ordered cycle* (15 of 183): walk the loop starting from the sender of the pattern's earliest `TX_ID`. Timestamps never decrease. Starting from any rotation would give 19.
  - *Mean out-degree* (132.34): transactions per account, averaged over the 9,999 accounts that send at least once.
  - *Fan-in identical amounts*: 40 of 199 patterns (20.1%).
  - *`TX_AMOUNT > 1e6`* (15,911): this count includes the 3,053 sentinel amounts.
- **2026-10-22 — The agent's PG role is read-only through the role itself.** It's created with `default_transaction_read_only = on` and `statement_timeout = QUERY_TIMEOUT_S`, with only CONNECT, USAGE and SELECT granted, and CREATE on `public` revoked. Neo4j Community has no role-based access control, so read-only on that side comes from `execute_read` transactions. Integration tests cover both.
- **2026-10-22 — Neo4j schema persists across reloads.** `clear_graph` deletes data, not the constraint or indexes, so after the first load the `TRANSFER(step)`/`TRANSFER(amount)` indexes are maintained during the load rather than built afterwards. That's why `index_s` is about 0 and the time shows up in `create_s`. Postgres always builds its indexes after COPY. Load time isn't a research metric, so this only affects the load-time report.
- **2026-10-22 — Parity normalizes Postgres `NUMERIC` whole numbers to `int`.** `sum(bigint)` returns `NUMERIC`. Converting it keeps checksums exact and the reports readable.

## Findings to carry into Phase 2

- **Amount tails grow over simulated time.** The median amount is about 156 in every step band. But non-sentinel amounts above 1e6 only appear from step 78, and the 3,053 sentinel amounts only in steps 149–199. So s25, s50 and s100 contain **no sentinel rows**, and the `missing_sentinel_exclusion` failure class can only happen at `full`. Phase 2 task design and the RQ4 analysis need to account for this.
