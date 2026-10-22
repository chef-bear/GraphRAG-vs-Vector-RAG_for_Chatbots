"""L4 cycles: loop membership and enumeration with identical amounts."""

from __future__ import annotations

from bench import algorithms as alg
from bench.families.base import Family, pick

MEMBERSHIP_WINDOW = 10
ENUM_WINDOW = 19


class CycleMembership(Family):
    """Positives: closed-cycle members with a window covering their cycle. Negatives:
    fan-in members around their pattern, and accounts in no pattern."""

    name = "cycle_membership"
    level = 4
    answer_type = "bool_set"
    n_fan_in_negatives = 2
    n_plain_negatives = 3

    def sample(self, ctx, rng, n):
        pats = ctx.patterns
        cycles = pats[pats.is_closed_cycle]
        fans = pats[pats.alert_type == "fan_in"]
        n_pos = n - self.n_fan_in_negatives - self.n_plain_negatives
        out = []

        def around(row):
            # any window [a, a + W] that still contains the whole pattern
            lo = max(0, int(row.max_step) - MEMBERSHIP_WINDOW)
            a = int(rng.integers(lo, int(row.min_step) + 1))
            return a, a + MEMBERSHIP_WINDOW

        for pid in pick(rng, cycles.alert_id.astype(int), n_pos):
            a, b = around(cycles[cycles.alert_id == pid].iloc[0])
            out.append({"x": pick(rng, ctx.members_by_pattern[pid], 1)[0], "a": a, "b": b})
        for pid in pick(rng, fans.alert_id.astype(int), self.n_fan_in_negatives):
            a, b = around(fans[fans.alert_id == pid].iloc[0])
            x = pick(rng, ctx.members_by_pattern[pid], 1)[0]
            out.append({"x": x, "a": a, "b": b, "negative_control": True})
        in_pattern = set(ctx.patterns_by_account) | ctx.flagged_accounts
        plain = [a for a in ctx.accounts if a not in in_pattern]
        for x in pick(rng, plain, self.n_plain_negatives):
            a = int(rng.integers(0, ctx.last_step - MEMBERSHIP_WINDOW + 1))
            out.append({"x": x, "a": a, "b": a + MEMBERSHIP_WINDOW, "negative_control": True})
        return out

    def question(self, p):
        return (
            f"Does account {p['x']} take part in a money loop: a chain of 2 to 5 transfers that "
            f"starts and ends at account {p['x']} without visiting any other account twice, "
            f"where every transfer has the same amount and step between {p['a']} and {p['b']} "
            "(inclusive)? The transfers may happen in any time order, and self-transfers don't "
            f"count. If so, list every account on any such loop, including {p['x']}."
        )

    def ground_truth(self, ctx, p):
        loops = alg.loops_through(ctx.tx, p["x"], p["a"], p["b"])
        accounts = sorted({a for loop in loops for a in loop})
        return {"in_loop": bool(loops), "accounts": accounts}


class CycleEnumerationWindow(Family):
    name = "cycle_enumeration_window"
    level = 4
    answer_type = "set_of_cycles"

    def sample(self, ctx, rng, n):
        # shrink the window at s25 so there are enough distinct starts
        width = min(ENUM_WINDOW, ctx.last_step - n)
        starts = pick(rng, range(ctx.last_step - width + 1), n)
        return [{"a": a, "b": a + width} for a in starts]

    def question(self, p):
        return (
            "List every money loop of 3 to 5 transfers (a chain that returns to its starting "
            "account without visiting any other account twice) in which all transfers have the "
            f"same amount and every transfer has step between {p['a']} and {p['b']} "
            "(inclusive). Give each loop once, as its accounts in the order money moves."
        )

    def ground_truth(self, ctx, p):
        return alg.loops_in_window(ctx.tx, p["a"], p["b"])
