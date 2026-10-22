"""L1 lookups: single-account filters and counts."""

from __future__ import annotations

from bench import algorithms as alg
from bench.families.base import Family, pick, py

WINDOW = 10  # steps [a, a + WINDOW]


class AcctTotalOut(Family):
    name = "acct_total_out"
    level = 1
    answer_type = "number"

    def sample(self, ctx, rng, n):
        out = []
        for _ in range(n):
            a = int(rng.integers(0, ctx.last_step - WINDOW + 1))
            w = alg.in_window(ctx.tx, a, a + WINDOW)
            x = pick(rng, set(w.sender_id.astype(int)), 1)[0]
            out.append({"x": py(x), "a": a, "b": a + WINDOW})
        return out

    def question(self, p):
        return (
            f"What is the total amount sent by account {p['x']} in transfers with step between "
            f"{p['a']} and {p['b']} (inclusive)? Exclude sentinel (overflow) amounts."
        )

    def ground_truth(self, ctx, p):
        return alg.total_out(ctx.tx, p["x"], p["a"], p["b"])


class AcctCounterparties(Family):
    name = "acct_counterparties"
    level = 1
    answer_type = "integer"

    def sample(self, ctx, rng, n):
        return [{"x": py(x)} for x in pick(rng, ctx.accounts, n)]

    def question(self, p):
        return (
            f"How many distinct accounts, other than account {p['x']} itself, has account "
            f"{p['x']} sent money to?"
        )

    def ground_truth(self, ctx, p):
        return alg.counterparties(ctx.tx, p["x"])
