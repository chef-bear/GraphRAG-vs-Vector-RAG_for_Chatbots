"""L2 aggregates: group-by over a time window."""

from __future__ import annotations

from bench import algorithms as alg
from bench.families.base import Family, pick

TOP_N = 5
TOP_WINDOW = 10
FAN_RANGE = 29  # steps [lo, lo + FAN_RANGE]
FAN_WIDTH = 7
FAN_MIN_SENDERS = 4
FAN_CAPS = (5, 10)


class TopReceivers(Family):
    name = "top_receivers"
    level = 2
    answer_type = "ordered_list"

    def sample(self, ctx, rng, n):
        starts = pick(rng, range(ctx.last_step - TOP_WINDOW + 1), n)
        return [{"a": a, "b": a + TOP_WINDOW, "n": TOP_N} for a in starts]

    def question(self, p):
        return (
            f"List the top {p['n']} accounts by number of distinct sender accounts that sent "
            f"them money in transfers with step between {p['a']} and {p['b']} (inclusive). "
            "Ignore self-transfers (sender = receiver). Rank by that count, highest first; "
            "break ties by smaller account_id first."
        )

    def ground_truth(self, ctx, p):
        return alg.top_receivers(ctx.tx, p["a"], p["b"], p["n"])


class FanInCandidates(Family):
    name = "fan_in_candidates"
    level = 2
    answer_type = "set"

    def sample(self, ctx, rng, n):
        # at s25 a 30-step range doesn't fit; shrink it so starts still vary
        span = min(FAN_RANGE, ctx.last_step - 5)
        combos = [(lo, cap) for lo in range(ctx.last_step - span + 1) for cap in FAN_CAPS]
        return [
            {
                "lo": lo,
                "hi": lo + span,
                "width": FAN_WIDTH,
                "min_senders": FAN_MIN_SENDERS,
                "cap": cap,
            }
            for lo, cap in pick(rng, combos, n)
        ]

    def question(self, p):
        return (
            f"Find every account R for which some window of {p['width']} consecutive steps, "
            f"lying entirely within steps {p['lo']} to {p['hi']} (inclusive), contains at least "
            f"{p['min_senders']} different accounts that each sent R exactly one transfer "
            f"during that window, with that transfer's amount below {p['cap']}. "
            "Ignore self-transfers."
        )

    def ground_truth(self, ctx, p):
        return alg.fan_in_candidates(
            ctx.tx, p["lo"], p["hi"], p["width"], p["min_senders"], p["cap"]
        )
