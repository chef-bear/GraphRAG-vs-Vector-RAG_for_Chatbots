# Agentic Fraud Investigation: Relational vs. Graph

A benchmark of local LLM agents (Ollama) that investigate money-laundering patterns by writing
SQL against **PostgreSQL** or Cypher against **Neo4j**, on the same synthetic dataset. See
[docs/SPEC.md](docs/SPEC.md) for the research questions and design, and
[docs/PROGRESS.md](docs/PROGRESS.md) for current status.

**Data:** an example dataset generated with [IBM AMLSim](https://github.com/IBM/AMLSim), a
multi-agent simulator of banking transactions with known laundering patterns. Results describe
agent behavior on AMLSim-style patterns.

## Quickstart (ingestion)

```bash
make venv                        # Python 3.11+ venv with dependencies
cp .env.example .env             # then set passwords
# put accounts.csv, transactions.csv, alerts.csv in data/raw/
make test                        # unit tests (no DB needed)
make up                          # Postgres 16 + Neo4j 5 in Docker
make ingest SCALE=s25            # validate -> stage -> load both DBs -> parity
make test-integration
```
