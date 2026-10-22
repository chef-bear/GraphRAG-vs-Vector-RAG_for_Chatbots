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

## Phase 2

- **2026-10-22 — Task plan: 116 instances per scale.** L1 20, L2 20, L3 36 (9 per k for k = 2–5), L4 20, L5 20. 16 of them (13.8%) are negative controls, against the spec's "about 15%". Negatives only make sense where there's a seed account (L3 `same_amount_chain_k`, L4 `cycle_membership`, L5). The generator re-checks each one: a sampled negative whose answer turns out non-empty is kept as a positive, with a warning.
- **2026-10-22 — `fan_in_candidates` uses a 7-step window and an amount cap (5 or 10).** The spec's literal wording ("≥4 distinct senders each sending exactly one transfer within a 10-step window") matches about 5,000 of the 10,000 accounts. Background senders send about one transfer per pair per 10 steps, so the clause isn't distinctive. With the cap, answers have 3–104 accounts. With cap 5 the rule is fraud-precise (70 of 70 at `full`). The range is 30 steps, shrunk at s25 so window starts can still vary.
- **2026-10-22 — L5 prompts state the scheme typology explicitly**: cycle = a same-amount loop of 3–5 accounts within 11 steps; fan-in = at least 4 senders each sending under 5.00 to one receiver within 7 steps. Without it, "investigate the scheme" can't be answered from data that has no labels. The rule reproduces the label-derived ring exactly for 100% of eligible seeds (121 at s25, 319 at s50). A cap of 10 would only manage 71–78%. The generator still keeps only seeds where the rule matches the labels, so every L5 instance is solvable from the DB. So far it has never had to drop one.
- **2026-10-22 — L5 seeds come from "clean" patterns only:** closed cycles and fan-ins with exactly 4 senders. The 9 incomplete cycles and 9 fan-ins with fewer senders don't fit the typology. Negative seeds are accounts in no pattern and not flagged as fraud. `ring_type` positives are accounts whose patterns are all of one type, 3 cycle and 2 fan-in.
- **2026-10-22 — Overlap accounts use union ground truth (default in §11.5).** For seeds in several patterns, the answer is the union of all their patterns' members. This needs the user's confirmation at Checkpoint 2.
- **2026-10-22 — Semantics pinned in the prompts:**
  - every step range is inclusive
  - transfers follow the direction money moves
  - `same_amount_chain_k` and `cycle_membership` allow any time order
  - `time_respecting_reach_k` requires *strictly* increasing steps
  - loops are simple (no repeated account) and ignore self-transfers
  - `top_receivers` breaks ties by smaller account_id and ignores self-transfers
  - `acct_counterparties` excludes the account itself
  - reachability answers exclude the start account
- **2026-10-22 — Windows and starts are drawn without replacement**, so a scale never contains duplicate instances. `cycle_enumeration_window` shrinks its 20-step window at s25 for the same reason.
- **2026-10-22 — Reference queries run under agent constraints.** Verification runs SQL as the read-only `fraud_agent` role (30 s statement timeout) and Cypher in `execute_read` with a 30 s timeout, through the same `core/readonly.py` the agent will use. A reference that only works with admin rights or no timeout would fail verification.
- **2026-10-22 — Neo4j 5.26 quirk.** A list comprehension over a variable-length relationship list (`[t IN ts | t.step]`), when concatenated with another list, gets type-inferred as booleans and fails with a confusing "Type mismatch". The workaround is to build `[t0] + ts` first and comprehend over that. This is worth watching for in RQ3: agents writing Cypher may hit the same error.
