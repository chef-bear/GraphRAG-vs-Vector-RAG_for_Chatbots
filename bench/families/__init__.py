"""Registry of task families, in generation order (the order is part of the seed)."""

from __future__ import annotations

from bench.families.base import Family
from bench.families.l1_lookup import AcctCounterparties, AcctTotalOut
from bench.families.l2_aggregate import FanInCandidates, TopReceivers
from bench.families.l3_path import KS, SameAmountChain, TimeRespectingReach
from bench.families.l4_cycle import CycleEnumerationWindow, CycleMembership
from bench.families.l5_investigation import RingFromSeed, RingType

# family -> number of instances per scale (~120 total, SPEC §6.1)
PLAN: list[tuple[type[Family], int]] = [
    (AcctTotalOut, 10),
    (AcctCounterparties, 10),
    (TopReceivers, 10),
    (FanInCandidates, 10),
    (SameAmountChain, SameAmountChain.per_k * len(KS)),
    (TimeRespectingReach, TimeRespectingReach.per_k * len(KS)),
    (CycleMembership, 12),
    (CycleEnumerationWindow, 8),
    (RingFromSeed, 12),
    (RingType, 8),
]

FAMILIES: dict[str, Family] = {cls.name: cls() for cls, _ in PLAN}
