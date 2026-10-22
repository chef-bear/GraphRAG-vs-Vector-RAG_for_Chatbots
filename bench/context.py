"""Everything ground truth may read: staged data for one scale, labels included."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pandas as pd

from core.scales import max_step
from ingest.stage import StagedData, read_staged


@dataclass
class Context:
    scale: str
    staged: StagedData
    _cache: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, staged_dir: Path, scale: str) -> Context:
        return cls(scale, read_staged(staged_dir / scale, labels=True))

    @property
    def last_step(self) -> int:
        return max_step(self.scale)

    @property
    def tx(self) -> pd.DataFrame:
        return self.staged.transactions

    @property
    def accounts(self) -> list[int]:
        return sorted(self.staged.accounts.account_id.astype(int).tolist())

    @property
    def patterns(self) -> pd.DataFrame:
        return self.staged.patterns

    @cached_property
    def patterns_by_account(self) -> dict[int, set[int]]:
        """account_id -> alert_ids of patterns (fully inside this scale) it belongs to."""
        m = self.staged.pattern_members
        return {int(a): set(g.alert_id.astype(int)) for a, g in m.groupby("account_id")}

    @cached_property
    def members_by_pattern(self) -> dict[int, set[int]]:
        m = self.staged.pattern_members
        return {int(p): set(g.account_id.astype(int)) for p, g in m.groupby("alert_id")}

    @cached_property
    def pattern_amount(self) -> dict[int, float]:
        """alert_id -> amount of its first transaction (all equal for cycles)."""
        lab = self.staged.tx_labels
        fraud = lab[lab.alert_id != -1].merge(self.tx[["tx_id", "amount"]], on="tx_id")
        first = fraud.sort_values("tx_id").groupby("alert_id").amount.first()
        return {int(p): float(a) for p, a in first.items()}

    @cached_property
    def flagged_accounts(self) -> set[int]:
        """Accounts with IS_FRAUD=true, in a pattern or not."""
        lab = self.staged.account_labels
        return set(lab[lab.is_fraud].account_id.astype(int))

    def pattern_union(self, account_id: int) -> list[int]:
        """L5 ground truth: union of the members of every pattern containing the account."""
        out: set[int] = set()
        for p in self.patterns_by_account.get(account_id, ()):
            out |= self.members_by_pattern[p]
        return sorted(out)
