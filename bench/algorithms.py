"""Ground-truth graph algorithms over a transactions frame (pure; no DB access).

Every function takes `tx` with at least sender_id, receiver_id, amount, step and
is_self_loop, already restricted to the scale being evaluated.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd


def in_window(tx: pd.DataFrame, a: int, b: int) -> pd.DataFrame:
    return tx[(tx.step >= a) & (tx.step <= b)]


def total_out(tx: pd.DataFrame, x: int, a: int, b: int) -> float:
    w = in_window(tx, a, b)
    sel = w[(w.sender_id == x) & ~w.amount_is_sentinel]
    return round(float(sel.amount.sum()), 2)


def counterparties(tx: pd.DataFrame, x: int) -> int:
    sel = tx[(tx.sender_id == x) & (tx.receiver_id != x)]
    return int(sel.receiver_id.nunique())


def top_receivers(tx: pd.DataFrame, a: int, b: int, n: int) -> list[int]:
    """Top n receivers by distinct senders (self-transfers ignored); ties -> smaller id."""
    w = in_window(tx, a, b)
    w = w[~w.is_self_loop]
    counts = w.groupby("receiver_id").sender_id.nunique().reset_index(name="k")
    counts = counts.sort_values(["k", "receiver_id"], ascending=[False, True])
    return counts.receiver_id.head(n).astype(int).tolist()


def fan_in_candidates(tx: pd.DataFrame, lo: int, hi: int, width: int, min_senders: int,
                      cap: float) -> list[int]:
    """Receivers R with some window [w, w+width-1] inside [lo, hi] in which at least
    `min_senders` distinct accounts each sent R exactly one transfer (any amount), and
    that transfer was below `cap`. Self-transfers are ignored."""
    base = in_window(tx, lo, hi)
    base = base[~base.is_self_loop]
    found: set[int] = set()
    for w in range(lo, hi - width + 2):
        x = in_window(base, w, w + width - 1)
        g = x.groupby(["receiver_id", "sender_id"]).amount.agg(["size", "max"])
        ok = g[(g["size"] == 1) & (g["max"] < cap)].reset_index()
        k = ok.groupby("receiver_id").size()
        found |= set(k[k >= min_senders].index.astype(int))
    return sorted(found)


def same_amount_reach(tx: pd.DataFrame, x: int, amount: float, a: int, b: int, k: int) -> list[int]:
    """Accounts (other than x) reachable from x in <= k hops along transfers of exactly
    `amount` within [a, b], in any time order."""
    w = in_window(tx, a, b)
    w = w[w.amount == amount]
    adj: dict[int, set[int]] = defaultdict(set)
    for s, r in zip(w.sender_id.tolist(), w.receiver_id.tolist(), strict=True):
        adj[s].add(r)
    seen, frontier = {x}, {x}
    for _ in range(k):
        frontier = {r for s in frontier for r in adj.get(s, ())} - seen
        seen |= frontier
    return sorted(seen - {x})


def time_respecting_reach(tx: pd.DataFrame, x: int, a: int, b: int, k: int) -> list[int]:
    """Accounts (other than x) reachable from x in <= k hops where every transfer is in
    [a, b] and each transfer's step is strictly greater than the previous one's.

    Earliest-arrival DP: arrival[v] after h hops is the smallest step at which v can be
    reached with <= h hops; an edge u->v at step s is usable iff s > arrival[u].
    """
    w = in_window(tx, a, b)
    out: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for s, r, st in zip(w.sender_id.tolist(), w.receiver_id.tolist(), w.step.tolist(),
                        strict=True):
        out[s].append((r, st))
    arrival = {x: a - 1}
    for _ in range(k):
        nxt = dict(arrival)
        for u, t_u in arrival.items():
            for v, s in out.get(u, ()):
                if s > t_u and s < nxt.get(v, b + 1):
                    nxt[v] = s
        arrival = nxt
    return sorted(set(arrival) - {x})


def _amount_adjacency(w: pd.DataFrame) -> dict[tuple[int, float], set[int]]:
    """(sender, amount) -> receivers, ignoring self-transfers."""
    w = w[~w.is_self_loop]
    adj: dict[tuple[int, float], set[int]] = defaultdict(set)
    for s, r, amt in zip(w.sender_id.tolist(), w.receiver_id.tolist(), w.amount.tolist(),
                         strict=True):
        adj[(s, amt)].add(r)
    return adj


def loops_through(tx: pd.DataFrame, x: int, a: int, b: int, max_len: int = 5) -> list[list[int]]:
    """Simple directed loops through x of 2..max_len transfers, all with the same amount
    and all within [a, b]. Each loop is returned starting at x."""
    w = in_window(tx, a, b)
    w = w[~w.is_self_loop]
    adj = _amount_adjacency(w)
    first = w[w.sender_id == x][["receiver_id", "amount"]].drop_duplicates()
    loops: set[tuple[int, ...]] = set()

    def extend(path: list[int], amt: float) -> None:
        for r in adj.get((path[-1], amt), ()):
            if r == x and len(path) >= 2:
                loops.add(tuple(path))
            elif r not in path and len(path) < max_len:
                extend([*path, r], amt)

    for r, amt in zip(first.receiver_id.tolist(), first.amount.tolist(), strict=True):
        extend([x, r], amt)
    return [list(p) for p in sorted(loops)]


def loops_in_window(tx: pd.DataFrame, a: int, b: int, min_len: int = 3,
                    max_len: int = 5) -> list[list[int]]:
    """All simple directed loops of min_len..max_len transfers with identical amounts,
    every transfer within [a, b]. Each loop starts at its smallest account_id."""
    w = in_window(tx, a, b)
    adj = _amount_adjacency(w)
    loops: set[tuple[int, ...]] = set()

    def extend(path: list[int], amt: float) -> None:
        start = path[0]
        for r in adj.get((path[-1], amt), ()):
            if r == start and len(path) >= min_len:
                loops.add(tuple(path))
            elif r > start and r not in path and len(path) < max_len:
                extend([*path, r], amt)

    for (s, amt), receivers in list(adj.items()):
        for r in receivers:
            if r > s:
                extend([s, r], amt)
    return [list(p) for p in sorted(loops)]


def loops_within_span(tx: pd.DataFrame, x: int, span: int, min_len: int = 3,
                      max_len: int = 5) -> list[list[int]]:
    """Simple loops through x of min_len..max_len transfers with identical amounts whose
    steps satisfy max(step) - min(step) <= span. No fixed window. Loops start at x."""
    w = tx[~tx.is_self_loop]
    adj: dict[tuple[int, float], list[tuple[int, int]]] = defaultdict(list)
    for s, r, amt, st in zip(w.sender_id.tolist(), w.receiver_id.tolist(), w.amount.tolist(),
                             w.step.tolist(), strict=True):
        adj[(s, amt)].append((r, st))
    loops: set[tuple[int, ...]] = set()

    def extend(path: list[int], amt: float, lo: int, hi: int) -> None:
        for r, st in adj.get((path[-1], amt), ()):
            lo2, hi2 = min(lo, st), max(hi, st)
            if hi2 - lo2 > span:
                continue
            if r == x and len(path) >= min_len:
                loops.add(tuple(path))
            elif r != x and r not in path and len(path) < max_len:
                extend([*path, r], amt, lo2, hi2)

    first = w[w.sender_id == x]
    for r, amt, st in zip(first.receiver_id.tolist(), first.amount.tolist(), first.step.tolist(),
                          strict=True):
        extend([x, r], amt, st, st)
    return [list(p) for p in sorted(loops)]


def scheme_members(tx: pd.DataFrame, x: int, *, cycle_span: int, fan_width: int,
                   fan_min_senders: int, fan_cap: float) -> dict[str, list[int]]:
    """The L5 detection rule stated in the ring prompts, by scheme type.

    cycle:  accounts on simple loops of 3..5 transfers through x with identical amounts
            whose steps all lie within `cycle_span` + 1 consecutive steps.
    fan_in: for any receiver R and window [w, w + fan_width - 1] in which at least
            `fan_min_senders` distinct accounts each sent R a transfer below `fan_cap`:
            if x is R or one of those senders, R and those senders.
    """
    no_self = tx[~tx.is_self_loop]
    cycle: set[int] = set()
    for loop in loops_within_span(no_self, x, cycle_span):
        cycle |= set(loop)

    small = no_self[no_self.amount < fan_cap]
    touching = set(small[(small.sender_id == x)].receiver_id) | {x}
    fan: set[int] = set()
    cand = small[small.receiver_id.isin(touching)]
    for r, g in cand.groupby("receiver_id"):
        steps = sorted(set(g.step.tolist()))
        for w0 in {s - d for s in steps for d in range(fan_width)}:
            win = g[(g.step >= w0) & (g.step <= w0 + fan_width - 1)]
            senders = set(win.sender_id)
            if len(senders) >= fan_min_senders and (x == r or x in senders):
                fan |= senders | {int(r)}
    return {"cycle": sorted(cycle), "fan_in": sorted(fan)}
