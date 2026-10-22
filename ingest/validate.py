"""Re-derive the SPEC §2 facts and fail loudly on any difference."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ingest.expected import EXPECTED
from ingest.profile import compute_profile
from ingest.raw import RawData

log = logging.getLogger(__name__)


class ValidationError(RuntimeError):
    pass


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def compare(profile: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return one message per expected fact that is missing or different."""
    got = flatten(profile)
    problems = []
    for key, want in flatten(expected).items():
        if key not in got:
            problems.append(f"{key}: missing from profile (expected {want!r})")
        elif got[key] != want:
            problems.append(f"{key}: expected {want!r}, got {got[key]!r}")
    return problems


def validate(raw: RawData, report_path: Path | None = None) -> dict[str, Any]:
    """Profile `raw`, optionally write the report, and raise if any fact differs."""
    profile = compute_profile(raw)
    problems = compare(profile, EXPECTED)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {"ok": not problems, "problems": problems, "profile": profile}
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        log.info("wrote %s", report_path)
    dq = profile["data_quality"]
    log.info(
        "sentinel amounts=%d, amounts>1e6=%d, zero amounts=%d, self-loops=%d",
        dq["sentinel_amount"],
        dq["amount_gt_1e6"],
        dq["amount_zero"],
        dq["self_loops"],
    )
    if problems:
        raise ValidationError("dataset does not match SPEC §2:\n  " + "\n  ".join(problems))
    return profile
