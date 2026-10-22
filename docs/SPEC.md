# SPEC — Agentic Fraud Investigation Across Relational and Graph Databases

> **For Claude Code.** This is the source-of-truth spec for this repo. Save it as `docs/SPEC.md` and add a pointer to it from `CLAUDE.md`. Work through the phases in order. **Stop at every `🛑 CHECKPOINT`** and report to the user before continuing. Read §0 before touching any code.

---

## 0. Working agreement (read first)

**The user wants to be looped in.** Follow these rules for the whole project:

1. **Audit before changing.** The repo already contains work. Phase 0 is a read-only audit. Don't delete, rename or rewrite existing modules until the user approves the migration plan at Checkpoint 0.
2. **Checkpoints are hard stops.** At each `🛑 CHECKPOINT`, post a short report and wait for a reply. The report has four parts: what was done, what was verified and how, open questions, and the proposed next step.
3. **Ask, don't guess, on anything in §11 (Open decisions).** For anything else, choose the simplest option that satisfies this spec, then record it in `docs/DECISIONS.md` (date, decision, why, alternatives).
4. **Keep `docs/PROGRESS.md` current.** It holds a checklist of phases and tasks with status. Update it at the end of every work session, so the user can see the project state at a glance.
5. **Small commits on a feature branch**, one logical change each, with descriptive messages. Never commit to `main` directly. Never commit data files or `.env`.
6. **Tests are part of done.** A task is complete only when its acceptance criteria pass and `make test` is green.
7. **No paid APIs.** All LLM calls go to local Ollama (§5). Don't add OpenAI, Anthropic or Gemini SDK calls, even as fallbacks.

---

## 1. Project in one paragraph

We load one synthetic AML dataset (AMLSim output) into **PostgreSQL** and **Neo4j**. A **local LLM agent** (Ollama) gets natural-language fraud-investigation tasks, writes SQL or Cypher, runs it, reads the results and either answers or retries. The benchmark has ground-truth answers, and tasks get harder level by level: lookups → aggregations → multi-hop traversal → cycle detection → full ring investigation. For each combination of database × mode (one-shot vs. agentic) × model × data scale, we measure accuracy, query errors, recovery, number of DB calls, tokens and latency.

**Research questions**
- RQ1: Does the data model (relational vs. graph) change agent accuracy as tasks need more hops?
- RQ2: Does iterative agentic querying close the gap, and at what cost in calls and tokens?
- RQ3: How do failure modes differ between SQL and Cypher, and which ones does the agent recover from?
- RQ4: How does database execution latency scale with data size and traversal depth?

**Hypothesis:** Postgres stays competitive on filtering and aggregation. Neo4j pulls ahead on path and cycle tasks, and Cypher agents need fewer retries on those tasks.

---

## 2. Dataset — verified facts (from profiling the provided zip)

**Source:** an example dataset generated with **IBM AMLSim**, a multi-agent simulator that produces synthetic banking transactions with known money-laundering patterns, built to test ML models and graph algorithms (github.com/IBM/AMLSim). Cite it in the README and report. Because the data comes from a simulator, results describe agent behavior on AMLSim-style patterns; list this under threats to validity.

The zip holds AMLSim output: three CSVs. They go in `data/raw/` (gitignored). The ingestion code must not assume any other source.

### 2.1 Files

| File | Rows | Columns |
|---|---|---|
| `accounts.csv` | 10,000 | `ACCOUNT_ID` int (0–9999), `CUSTOMER_ID` str (`C_<n>`, 1:1 with account), `INIT_BALANCE` float, `COUNTRY` str, `ACCOUNT_TYPE` str, `IS_FRAUD` bool (`true`/`false`, lowercase), `TX_BEHAVIOR_ID` int (1–5) |
| `transactions.csv` | 1,323,234 | `TX_ID` int (1..1,323,234, unique), `SENDER_ACCOUNT_ID`, `RECEIVER_ACCOUNT_ID`, `TX_TYPE` str, `TX_AMOUNT` float, `TIMESTAMP` int (step 0–199), `IS_FRAUD` bool (`True`/`False`, capitalized), `ALERT_ID` int (`-1` = none) |
| `alerts.csv` | 1,719 | `ALERT_ID`, `ALERT_TYPE` (`cycle` / `fan_in`), `IS_FRAUD`, `TX_ID`, `SENDER_ACCOUNT_ID`, `RECEIVER_ACCOUNT_ID`, `TX_TYPE`, `TX_AMOUNT`, `TIMESTAMP` — one row per fraudulent transaction |

### 2.2 Shape of the data
- **391 fraud patterns** (`ALERT_ID`): 192 `cycle`, 199 `fan_in`. Each pattern has 1–5 transactions (median 4) and spans 0–10 timesteps.
- Every `alerts.csv` row has a matching transaction (1,719 = the transactions with `IS_FRAUD=True`).
- **Cycles:** 183 of 192 are complete 5-account loops. The other 9 have only 1–4 transactions and don't close in the data, so they're excluded from cycle-closure ground truth. Every transaction within a cycle has the **same amount** (100% of cycles), which is a useful signal for path tasks. **Cycles are generally NOT time-ordered:** only 15 of 183 have non-decreasing timestamps around the loop. Cycle tasks must therefore constrain by time *window*, never by "each hop after the previous one".
- **Fan-in:** each of the 199 patterns has exactly 1 receiver, and 190 of them have 4 distinct senders. Only about 20% of fan-in patterns use identical amounts, so fan-in tasks must not require equal amounts.
- **Patterns fully inside each scale window** (§3.2): s25 = 39, s50 = 91, s100 = 196, full = 391.
- **Fraud accounts:** 1,685 accounts have `IS_FRAUD=true`. 1,639 of them appear in alerts; 46 are flagged but never transact inside a pattern. 228 accounts belong to more than one pattern.
- **Dense graph:** 68,947 distinct (sender, receiver) pairs carry 1.32M transactions. Mean out-degree is about 132 transactions (min 7, max 963). As a result, **unconstrained 2-hop expansion reaches most of the graph**. Traversal tasks must be constrained (time window, amount, ordering) or they're meaningless (§6).
- Timestamps are abstract integer steps, not dates.

### 2.3 Data quality issues (ingestion must handle these explicitly)
| Issue | Count | Handling |
|---|---|---|
| `TX_AMOUNT == 21474836.47` (INT32_MAX/100, an overflow sentinel) | 3,053 | Keep the row, set `amount_is_sentinel = true`, and exclude it from amount-based ground truth. Log the count. |
| `TX_AMOUNT > 1e6` | 15,911 (none fraudulent) | Keep. Note in the data report. |
| `TX_AMOUNT == 0` | 19 | Keep. |
| Self-loops (sender == receiver) | 181 | Keep, flag `is_self_loop`. Exclude from cycle ground truth. |
| `COUNTRY` constant (`US`), `ACCOUNT_TYPE` constant (`I`), `TX_TYPE` constant (`TRANSFER`) | — | Load them anyway (agents should see a realistic schema), but no task may depend on them. |
| Boolean casing differs between files | — | Normalize to real booleans. |

The ingestion validation step must re-derive every number in §2.1–2.3 and fail loudly if any differ.

---

## 3. Scope change for data ingestion

**New scope:** this AMLSim zip is the **only** data source. Anything already in the repo that ingests other data (IBM AML-Data from Kaggle, generated data, etc.) gets one of three treatments, decided at Checkpoint 0: removed, moved to `legacy/`, or kept behind a flag.

### 3.1 Pipeline (one direction, reproducible)
```
data/raw/*.csv
  └─ ingest/validate.py   → assert §2 facts, write data/reports/data_profile.json
  └─ ingest/stage.py      → normalized Parquet in data/staged/{scale}/ (accounts, transactions, patterns)
  └─ ingest/load_pg.py    → Postgres (COPY from staged data)
  └─ ingest/load_neo4j.py → Neo4j (neo4j-admin import for full; batched UNWIND acceptable for small scales)
  └─ ingest/parity.py     → row/edge counts + 20 checksum queries must match across both DBs
```
Expose these as `make ingest SCALE=<s>` (runs validate → stage → load both → parity) and `make parity`.

### 3.2 Scale levels (for RQ4)
Build scales by **timestamp window**, not random sampling. A pattern spans at most 10 steps, so a time window keeps patterns intact, while random sampling would break them.

| Scale | Steps | Approx. transactions |
|---|---|---|
| `s25` | 0–24 | 160,480 |
| `s50` | 0–49 | 326,374 |
| `s100` | 0–99 | 657,561 |
| `full` | 0–199 | 1,323,234 |

A pattern counts as in ground truth at a given scale only if **all** of its transactions fall inside the window. Record per-scale pattern counts in the data report.

### 3.3 Label hygiene (critical for valid results)
The agent-facing databases **must not contain** `IS_FRAUD` (on accounts or transactions), `ALERT_ID`, or the alerts table. Otherwise the agent can read the answers.
- Ground truth is computed in Python from `data/staged/` (§6.3). Neither database is consulted for it, so neither is favored.
- Tasks that need "known fraud" seeds pass the seed account IDs **in the task prompt**. A separate `watchlist` table/node set holds *only* the seeds of the current task family; it's a stretch goal, decided at Checkpoint 2.
- Add a test that fails if any label column or table exists in either agent-facing DB.

---

## 4. Database models

Fairness rule: **both sides get equivalent information, indexes and documentation.** Any helper structure added to one side (e.g. aggregated edges) needs an equivalent on the other side.

### 4.1 PostgreSQL 16
```sql
CREATE TABLE accounts (
  account_id      INTEGER PRIMARY KEY,
  customer_id     TEXT NOT NULL,
  init_balance    NUMERIC(14,2) NOT NULL,
  country         TEXT NOT NULL,
  account_type    TEXT NOT NULL,
  behavior_id     SMALLINT NOT NULL
);
CREATE TABLE transactions (
  tx_id               INTEGER PRIMARY KEY,
  sender_id           INTEGER NOT NULL REFERENCES accounts,
  receiver_id         INTEGER NOT NULL REFERENCES accounts,
  tx_type             TEXT NOT NULL,
  amount              NUMERIC(14,2) NOT NULL,
  step                SMALLINT NOT NULL,
  amount_is_sentinel  BOOLEAN NOT NULL,
  is_self_loop        BOOLEAN NOT NULL
);
CREATE INDEX ON transactions (sender_id, step);
CREATE INDEX ON transactions (receiver_id, step);
CREATE INDEX ON transactions (step);
CREATE INDEX ON transactions (amount);
```
- The agent connects as a **read-only role** with `statement_timeout` set (default 30 s, configurable).
- One database per scale (`fraud_s25`, `fraud_s50`, …) is fine.

### 4.2 Neo4j 5 Community
```
(:Account {account_id, customer_id, init_balance, country, account_type, behavior_id})
(:Account)-[:TRANSFER {tx_id, amount, step, tx_type, amount_is_sentinel, is_self_loop}]->(:Account)
```
- Constraint: `CREATE CONSTRAINT FOR (a:Account) REQUIRE a.account_id IS UNIQUE`.
- Indexes on relationship properties: `TRANSFER(step)` and `TRANSFER(amount)`.
- Community Edition allows **one user database**, so scale experiments run scale by scale: `make ingest SCALE=s50` reloads Neo4j, then the runner executes every task for that scale.
- The agent runs queries in **read transactions** (`session.execute_read`) with a transaction timeout equal to the Postgres one.
- Set heap and page cache in the compose file for the user's machine (ask at Checkpoint 0 how much RAM is available).
- APOC is **off** by default: plain Cypher only, for fairness with plain SQL. It's an optional ablation.

### 4.3 Schema docs given to the agent
Write `agent/schema_docs/postgres.md` and `agent/schema_docs/neo4j.md`. Both must have the same content: entities, fields, meaning of `step`, the sentinel flag, and 3 example queries each solving the **same** 3 example problems. Keep the examples out of benchmark task families. Both files stay under the same token budget (±10%); a test enforces this.

### 4.4 Stretch: third arm
Apache AGE (Cypher inside Postgres) separates the effect of the query language from the effect of the storage engine. Don't build it until the user approves it after Phase 5.

---

## 5. Local LLM via Ollama

- Ollama runs on the **host**, not in compose (GPU access is simpler that way). From containers, reach it at `http://host.docker.internal:11434`; add `extra_hosts: ["host.docker.internal:host-gateway"]` on Linux.
- Client: the official `ollama` Python package (native `/api/chat` with `tools`), wrapped in `agent/llm.py` behind a small interface `chat(messages, tools) -> (message, usage)`. The rest of the code must not import `ollama` directly, so the backend can be swapped later.
- **Set `num_ctx` explicitly** (start at 16384). Ollama's default context window is small, and long schema docs plus result tables get silently truncated otherwise. Log the value used in every run.
- Determinism: `temperature=0` and a fixed `seed` from config. We still do 3 repeats per cell, because local inference isn't perfectly deterministic.
- Token accounting: use `prompt_eval_count` and `eval_count` from each response. Sum them per task.
- Models: configurable list in `config/models.yaml`. Suggested starting set (confirm at Checkpoint 3 based on the user's VRAM): a code-tuned ~7B model (e.g. `qwen2.5-coder:7b`), a general ~8B model (e.g. `llama3.1:8b`), and one larger model if the hardware allows. Each model must pass a **tool-calling smoke test** before it's allowed in a benchmark run.
- **Fallback if a model's tool calling is unreliable:** a JSON-mode protocol where the model returns `{"action": "query"|"answer", ...}`, parsed and validated with Pydantic. Implement both behind the same interface, select per model in config, and record which was used.

---

## 6. Benchmark

### 6.1 Task families (levels)
Each family is a **template** with parameters drawn from the data. Answers are a scalar or a set of `account_id`s. Constrained traversals are required because the graph is dense (§2.2).

| Level | Family | Example prompt | Answer |
|---|---|---|---|
| L1 lookup | `acct_total_out` | "Total amount sent by account 6456 between steps 10 and 20, excluding sentinel amounts?" | number |
| L1 lookup | `acct_counterparties` | "How many distinct accounts did 6456 send money to?" | integer |
| L2 aggregate | `top_receivers` | "Top 5 accounts by number of distinct senders during steps 30–40." | ordered list |
| L2 aggregate | `fan_in_candidates` | "Accounts that received transfers from ≥4 distinct senders within a single 10-step window, where each of those senders sent them exactly one transfer in that window, during steps 0–49." (Calibrate thresholds in Phase 2 so the answer set stays small.) | set |
| L3 path | `same_amount_chain_k` (k = 2…5) | "Starting at account X, follow transfers of exactly amount A within steps [a, a+10], in any time order. Which accounts are reachable in ≤k hops?" | set |
| L3 path | `time_respecting_reach_k` | "Accounts reachable from X within k hops using time-increasing transfers within steps [a, a+5]." (A pure traversal-difficulty probe, unrelated to fraud labels.) | set |
| L4 cycle | `cycle_membership` | "Does account X take part in a money loop (returning to X) of length ≤5 where every transfer has the same amount, all within steps [a, a+10]? If so, list the accounts in the loop." (Transfers may be in any time order; see §2.2.) | bool + set |
| L4 cycle | `cycle_enumeration_window` | "List all loops of length 3–5 with identical amounts that start and end within steps [a, b]." | set of sets |
| L5 investigation | `ring_from_seed` | "Account X is a confirmed fraudster. Investigate and return all accounts that are part of the same scheme." | set (scored vs. pattern members) |
| L5 investigation | `ring_type` | Same as above, plus "classify the scheme as cycle or fan-in". | set + label |

- Target **~120 task instances per scale**: about 20 per level, plus extra L3 instances across k.
- **Negative controls:** about 15% of instances use seeds that are *not* in any pattern, where the correct answer is "none" or the empty set.
- Generator: `bench/generate.py --scale s50 --seed 42` writes `bench/tasks/{scale}.jsonl` (`task_id, level, family, params, prompt, answer_type, ground_truth`). The output is deterministic for a given seed.

### 6.2 Scoring (`bench/score.py`)
- Number: correct if within 0.01 absolute or 1e-6 relative.
- Integer / bool / label: exact match.
- Set: precision, recall and F1. "Correct" means F1 = 1.0. Report mean F1 too.
- Ordered list: exact match plus Kendall's tau.
- Set of sets (cycles): canonicalize each cycle by rotating it to start at its smallest ID, then compute set F1.
- Any malformed final answer scores 0 and is logged as failure class `bad_answer_format`.

### 6.3 Ground truth (`bench/ground_truth.py`)
- Computed in Python from staged Parquet with pandas/networkx. **Never** from Postgres or Neo4j.
- **Three-way agreement test:** each family has a reference SQL and a reference Cypher query in `bench/reference/`. `make verify-gt` checks that Python == SQL == Cypher for every instance. All three must agree before any benchmark run. A disagreement means a bug, not a finding.
- L5 ground truth = the pattern's member accounts from `alerts.csv`. Note that 228 accounts belong to more than one pattern; for those seeds, the ground truth is the union of all their patterns. Document this choice in DECISIONS.md.

---

## 7. Agent

### 7.1 Tools (identical for both DBs except for the language)
| Tool | Behavior |
|---|---|
| `get_schema()` | Returns the schema doc from §4.3. |
| `run_query(query: str)` | Executes read-only with the timeout. Returns up to 50 rows as a compact table, plus `total_rows` and `truncated` flags. On error, returns the DB error message verbatim, trimmed to 500 chars. |
| `final_answer(answer: json, explanation: str)` | Ends the episode. The answer is validated against the task's `answer_type`. |

### 7.2 Modes
- **one-shot:** schema in the system prompt. The model gets exactly one `run_query`, then must call `final_answer`. No retry on error.
- **agentic:** up to `max_steps` (default 8) tool calls. The model may inspect results, fix errors and run follow-up queries.
- Both modes use the same system prompt skeleton; only the step budget differs. Prompts live in `agent/prompts/` as versioned files.

### 7.3 Guardrails
- Reject writes before execution (SQL: non-SELECT/WITH statements; Cypher: `CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD CSV|CALL dbms`). Read-only roles and transactions are the real protection; this is a second layer.
- Hard wall-clock cap per task (default 300 s). On timeout, log the class `episode_timeout`.

---

## 8. Runner, logging, metrics

### 8.1 Runner
`bench/run.py --scale s50 --db pg,neo4j --mode oneshot,agentic --models qwen2.5-coder:7b --repeats 3`
- Resumable: skip (task, db, mode, model, repeat) cells that already have results.
- Writes one JSON line per episode to `results/raw/{run_id}.jsonl`, plus `results/runs/{run_id}/config.json` (git SHA, models, num_ctx, prompts version, scale, timeouts).

### 8.2 Per-episode record
`task_id, level, family, scale, db, mode, model, repeat, steps[] (each step: query text, ok, error_class, error_msg, db_ms, rows, truncated, prompt_tokens, completion_tokens, llm_ms), final_answer, score fields, n_db_calls, n_failed_calls, recovered (bool: ≥1 failed call and a correct final answer), total_tokens, e2e_ms, termination (answered | max_steps | timeout | crash)`.

### 8.3 Failure taxonomy (`bench/failures.py`, rule-based first)
`syntax_error, unknown_column_or_property, wrong_join_or_direction, unbounded_traversal (timeout), wrong_time_filter, wrong_amount_filter, missing_sentinel_exclusion, partial_result_truncation, bad_answer_format, hallucinated_answer (no supporting query), max_steps`. Store the classification with the episode, then hand-audit a sample of 30 at Checkpoint 5.

### 8.4 Analysis (`analysis/`)
- A notebook or script that reads `results/raw/*.jsonl` into one Parquet file and produces:
  - Accuracy by level × db × mode (headline chart)
  - Accuracy and DB latency vs. hop depth k (L3)
  - DB latency vs. scale for the reference queries (no LLM involved; isolates the engine)
  - Calls and tokens per correct answer
  - Recovery rate by db
  - Failure-class distribution by db
- Use bootstrap 95% CIs over task instances. Don't claim a difference whose CIs overlap without saying so.

---

## 9. Repo layout and tooling

```
docker-compose.yml        # postgres:16, neo4j:5-community (no Ollama — runs on host)
Makefile                  # up, down, ingest, parity, gen-tasks, verify-gt, bench, analyze, test, lint
pyproject.toml            # Python 3.11+, uv or pip; ruff + pytest
.env.example              # PG/Neo4j creds, OLLAMA_HOST, NUM_CTX, timeouts
config/{models,bench}.yaml
ingest/  agent/  bench/  analysis/  tests/
data/{raw,staged,reports}/   # gitignored except reports/*.json
results/                     # gitignored except small summary CSVs
docs/{SPEC,DECISIONS,PROGRESS}.md
```
- `make test` must run without Ollama: unit tests mock `agent/llm.py`. Integration tests that need the DBs or Ollama are marked and opt-in (`make test-integration`).
- CI is optional (ruff + unit tests on GitHub Actions).

---

## 10. Phases and checkpoints

### Phase 0 — Repo audit (read-only)
- Inventory the existing code: what exists, what works, what conflicts with this spec, especially ingestion.
- Check the local environment: Docker, Python version, Ollama installed (`ollama list`), and available RAM/VRAM if the user can share them.
- Draft a migration plan: keep / refactor / move to `legacy/` / delete, per file.

🛑 **CHECKPOINT 0:** Present the inventory, the migration plan and the §11 questions that are relevant now. Wait for approval.

### Phase 1 — Ingestion (new scope)
- Execute the approved migration. Implement §3 and §4 with compose services, then `make ingest SCALE=full` and the smaller scales.
- Acceptance: `validate.py` reproduces every §2 number; parity passes for all 4 scales; the label-hygiene test passes; `data/reports/data_profile.json` and per-scale pattern counts are committed.

🛑 **CHECKPOINT 1:** Share the data report, parity output and load times per DB per scale.

### Phase 2 — Ground truth and tasks
- Implement the §6 generator, ground truth, reference SQL/Cypher, scorer and `make verify-gt`.
- Acceptance: three-way agreement is 100% on all instances at `s50`; the scorer has unit tests for every answer type.

🛑 **CHECKPOINT 2:** Show the task counts per family, plus **10 sample tasks** (prompt + ground truth + both reference queries) for the user to sanity-check. Flag any family whose answers are trivially empty or huge (>500 accounts); those need a tighter constraint.

### Phase 3 — Agent and Ollama
- Implement §5 and §7. Run the tool-calling smoke test per model.
- Run a smoke benchmark: 10 tasks × 2 DBs × 2 modes × 1 model at `s25`.
- Acceptance: episodes complete end to end, logs match §8.2, and no crashes.

🛑 **CHECKPOINT 3:** Share the smoke results table, the observed seconds per episode, and an **estimated wall-clock time for the full matrix** on the user's machine. Confirm the model list and the matrix size with the user.

### Phase 4 — Full runs
- Run the approved matrix scale by scale. Commit summary CSVs; keep the raw JSONL out of git.
- Report progress in PROGRESS.md after each scale.

🛑 **CHECKPOINT 4:** Share the headline accuracy table per scale, plus anything surprising.

### Phase 5 — Analysis and write-up
- Implement §8.3–8.4. Draft `docs/REPORT.md`: setup, results with CIs, failure analysis, threats to validity (synthetic data, small local models, prompt sensitivity), and next steps.
- Update the README: a one-command quickstart, the headline chart and key findings.

🛑 **CHECKPOINT 5:** Share the draft report and the hand-audited failure sample. Ask whether to pursue the stretch goals (Apache AGE arm, APOC ablation, schema-hint ablation, watchlist table).

---

## 11. Open decisions (ask the user; don't guess)
1. What to do with existing ingestion code: delete, move to `legacy/`, or keep behind a flag? (Checkpoint 0)
2. Machine specs (RAM, GPU/VRAM). These drive Neo4j memory settings and the model choice. (Checkpoint 0)
3. Model list and matrix size after seeing the smoke-run timing. (Checkpoint 3)
4. Whether to add the `watchlist` seed table to both DBs, or keep seeds only in prompts. (Checkpoint 2)
5. Whether pattern-overlap accounts use union ground truth (default) or are excluded from L5. (Checkpoint 2)
6. Stretch goals. (Checkpoint 5)

## 12. Definition of done
- `git clone` → `cp .env.example .env` → `make up ingest gen-tasks verify-gt bench analyze` reproduces the results on a fresh machine with Ollama installed.
- The report answers RQ1–RQ4 with CIs, and every claim traces back to a results file.
