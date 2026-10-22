"""L5 investigations: recover a laundering scheme from a seed account.

Ground truth is label-derived (union of the members of every pattern containing the
seed, SPEC §6.3). The prompt states the two scheme typologies precisely; a seed is used
only if that stated rule, applied to the data, reproduces the label-derived answer
exactly. That keeps every instance solvable from the database alone, and is what makes
SQL == Cypher == ground truth checkable.
"""

from __future__ import annotations

from bench import algorithms as alg
from bench.families.base import Family, pick

CYCLE_SPAN = 10  # all loop transfers within CYCLE_SPAN + 1 consecutive steps
FAN_WIDTH = 7
FAN_MIN_SENDERS = 4
FAN_CAP = 5.0

TYPOLOGY = (
    "Laundering schemes in this data take one of two forms:\n"
    "- cycle: money moves around a closed loop of 3 to 5 distinct accounts; every transfer in "
    f"the loop has the same amount, and all of them happen within {CYCLE_SPAN + 1} consecutive "
    "steps (in any time order).\n"
    f"- fan_in: {FAN_MIN_SENDERS} or more distinct accounts each send at least one transfer "
    f"below {FAN_CAP:.2f} to the same receiving account within {FAN_WIDTH} consecutive steps; "
    "the scheme is the receiver plus those senders.\n"
    "Self-transfers never count."
)


def detect(ctx, x: int) -> dict[str, list[int]]:
    return alg.scheme_members(
        ctx.tx,
        x,
        cycle_span=CYCLE_SPAN,
        fan_width=FAN_WIDTH,
        fan_min_senders=FAN_MIN_SENDERS,
        fan_cap=FAN_CAP,
    )


def _clean(ctx) -> set[int]:
    """Patterns the typology describes: closed cycles and 4-sender fan-ins."""
    p = ctx.patterns
    return set(
        p[p.is_closed_cycle | ((p.alert_type == "fan_in") & (p.n_senders == 4))].alert_id.astype(
            int
        )
    )


def _types(ctx, x: int) -> set[str]:
    p = ctx.patterns.set_index("alert_id").alert_type
    return {p[a] for a in ctx.patterns_by_account.get(x, ())}


class _Ring(Family):
    level = 5
    reference = "ring"
    n_negatives: int

    def __init__(self) -> None:
        self.stats: dict[str, int] = {}

    def query_params(self, p):
        return super().query_params(p) | {
            "span": CYCLE_SPAN,
            "width": FAN_WIDTH,
            "min_senders": FAN_MIN_SENDERS,
            "cap": FAN_CAP,
        }

    def _positive_pool(self, ctx) -> list[int]:
        clean = _clean(ctx)
        return [a for a, ps in ctx.patterns_by_account.items() if ps <= clean]

    def _draw(self, ctx, rng, pool, n, solvable) -> list[int]:
        """Draw up to n seeds from pool (in a seeded random order) that pass `solvable`."""
        kept, tried = [], 0
        for x in pick(rng, pool, len(pool)):
            if len(kept) == n:
                break
            tried += 1
            if solvable(x):
                kept.append(x)
        self.stats["tried"] = self.stats.get("tried", 0) + tried
        self.stats["unsolvable_dropped"] = (
            self.stats.get("unsolvable_dropped", 0) + tried - len(kept)
        )
        return kept

    def _negatives(self, ctx, rng) -> list[int]:
        excluded = set(ctx.patterns_by_account) | ctx.flagged_accounts
        pool = [a for a in ctx.accounts if a not in excluded]
        empty = lambda x: not any(detect(ctx, x).values())  # noqa: E731
        return self._draw(ctx, rng, pool, self.n_negatives, empty)

    def _matches_labels(self, ctx, x) -> bool:
        found = detect(ctx, x)
        return sorted(set(found["cycle"]) | set(found["fan_in"])) == ctx.pattern_union(x)

    def from_rows(self, rows):
        """Rows are (account_id, scheme_type)."""
        accounts = sorted({int(r[0]) for r in rows})
        types = {r[1] for r in rows}
        return accounts, types


class RingFromSeed(_Ring):
    name = "ring_from_seed"
    answer_type = "set"
    n_negatives = 4

    def sample(self, ctx, rng, n):
        self.stats = {}
        pos = self._draw(
            ctx,
            rng,
            self._positive_pool(ctx),
            n - self.n_negatives,
            lambda x: self._matches_labels(ctx, x),
        )
        neg = self._negatives(ctx, rng)
        return [{"x": x} for x in pos] + [{"x": x, "negative_control": True} for x in neg]

    def question(self, p):
        return (
            f"Account {p['x']} has been flagged for review.\n{TYPOLOGY}\n"
            f"Return every account that belongs to any scheme account {p['x']} is part of "
            f"(including {p['x']}), or an empty list if it is part of none."
        )

    def ground_truth(self, ctx, p):
        return ctx.pattern_union(p["x"])

    def from_rows(self, rows):
        accounts, _ = super().from_rows(rows)
        return accounts


class RingType(_Ring):
    name = "ring_type"
    answer_type = "set_label"
    n_negatives = 3

    def sample(self, ctx, rng, n):
        self.stats = {}
        n_pos = n - self.n_negatives
        pool = self._positive_pool(ctx)
        out = []
        for i, kind in enumerate(("cycle", "fan_in")):
            want = n_pos // 2 + (n_pos % 2 if i == 0 else 0)
            typed = [a for a in pool if _types(ctx, a) == {kind}]
            out += self._draw(ctx, rng, typed, want, lambda x: self._matches_labels(ctx, x))
        neg = self._negatives(ctx, rng)
        return [{"x": x} for x in out] + [{"x": x, "negative_control": True} for x in neg]

    def question(self, p):
        return (
            f"Account {p['x']} has been flagged for review.\n{TYPOLOGY}\n"
            f"Return every account in the scheme account {p['x']} is part of (including "
            f'{p["x"]}) and classify the scheme as "cycle" or "fan_in". If it is part of no '
            'scheme, return an empty list with type "none".'
        )

    def ground_truth(self, ctx, p):
        accounts = ctx.pattern_union(p["x"])
        types = _types(ctx, p["x"])
        return {"accounts": accounts, "type": types.pop() if accounts else "none"}

    def from_rows(self, rows):
        accounts, types = super().from_rows(rows)
        if len(types) > 1:
            raise ValueError(f"reference query returned several scheme types: {types}")
        return {"accounts": accounts, "type": types.pop() if types else "none"}
