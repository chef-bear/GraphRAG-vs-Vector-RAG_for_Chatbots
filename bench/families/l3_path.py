"""L3 paths: constrained multi-hop reachability, k = 2..5."""

from __future__ import annotations

from bench import algorithms as alg
from bench.families.base import Family, pick, py

KS = (2, 3, 4, 5)
CHAIN_WINDOW = 10
TIME_WINDOW = 5


class SameAmountChain(Family):
    """Per k: 3 seeds on a closed cycle (its amount and window), 1 ordinary account with
    one of its own amounts, 1 negative control (an amount it never sent -> [])."""

    name = "same_amount_chain_k"
    level = 3
    answer_type = "set"
    per_k = 5

    def sample(self, ctx, rng, n):
        cycles = ctx.patterns[ctx.patterns.is_closed_cycle]
        cycle_ids = sorted(cycles.alert_id.astype(int))
        in_pattern = set(ctx.patterns_by_account)
        plain = [a for a in ctx.accounts if a not in in_pattern and a not in ctx.flagged_accounts]
        tx = ctx.tx[~ctx.tx.amount_is_sentinel]
        out = []
        for k in KS:
            for pid in pick(rng, cycle_ids, 3):
                row = cycles[cycles.alert_id == pid].iloc[0]
                x = pick(rng, ctx.members_by_pattern[pid], 1)[0]
                a = int(row.min_step)
                out.append({"x": x, "amount": ctx.pattern_amount[pid], "a": a,
                            "b": a + CHAIN_WINDOW, "k": k})
            for negative in (False, True):
                while True:
                    x = pick(rng, plain, 1)[0]
                    a = int(rng.integers(0, ctx.last_step - CHAIN_WINDOW + 1))
                    own = alg.in_window(tx, a, a + CHAIN_WINDOW)
                    own = own[own.sender_id == x]
                    if own.empty:
                        continue
                    if negative:  # a cycle's amount that x never sent in this window
                        amount = ctx.pattern_amount[pick(rng, cycle_ids, 1)[0]]
                        if amount in set(own.amount):
                            continue
                    else:
                        amount = float(pick(rng, own.amount.tolist(), 1)[0])
                    break
                p = {"x": py(x), "amount": amount, "a": a, "b": a + CHAIN_WINDOW, "k": k}
                if negative:
                    p["negative_control"] = True
                out.append(p)
        return out

    def question(self, p):
        return (
            f"Starting at account {p['x']}, follow transfers in the direction money moves, "
            f"using only transfers of exactly {p['amount']:.2f} with step between {p['a']} and "
            f"{p['b']} (inclusive), in any time order. Which accounts, other than {p['x']}, "
            f"can be reached in at most {p['k']} transfers?"
        )

    def ground_truth(self, ctx, p):
        return alg.same_amount_reach(ctx.tx, p["x"], p["amount"], p["a"], p["b"], p["k"])


class TimeRespectingReach(Family):
    name = "time_respecting_reach_k"
    level = 3
    answer_type = "set"
    per_k = 4

    def sample(self, ctx, rng, n):
        out = []
        for k in KS:
            for _ in range(self.per_k):
                a = int(rng.integers(0, ctx.last_step - TIME_WINDOW + 1))
                w = alg.in_window(ctx.tx, a, a + TIME_WINDOW)
                x = pick(rng, set(w.sender_id.astype(int)), 1)[0]
                out.append({"x": py(x), "a": a, "b": a + TIME_WINDOW, "k": k})
        return out

    def question(self, p):
        return (
            f"Which accounts, other than {p['x']}, can be reached from account {p['x']} by a "
            f"chain of at most {p['k']} transfers (following the direction money moves) where "
            f"every transfer has step between {p['a']} and {p['b']} (inclusive) and each "
            "transfer in the chain has a strictly larger step than the transfer before it?"
        )

    def ground_truth(self, ctx, p):
        return alg.time_respecting_reach(ctx.tx, p["x"], p["a"], p["b"], p["k"])
