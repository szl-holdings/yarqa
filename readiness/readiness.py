"""Fail-closed declared-source readiness evaluation (propose-only).

Doctrine (leader-study card r1, docs/leader-study-r1.md):
- readiness is NOT liveness: a process may be alive yet not ready to
  serve traffic;
- every declared dependency must be PROVEN (declared-source contract),
  not merely reachable;
- freshness is first-class: every input carries an observation window
  and a last-seen timestamp;
- absent data and empty declarations yield UNKNOWN, never green.

Pure Python, stdlib only. PROPOSAL_ONLY, unsigned; merges are owned by
the estate signature wall. No status claims are made about any other
pull request.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

PROVEN = "proven"
UNPROVEN = "unproven"

FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"

READY = "READY"
NOT_READY = "NOT_READY"
UNKNOWN_STATUS = "UNKNOWN"


class DeclarationError(ValueError):
    """A dependency declaration is malformed."""


@dataclass
class DeclaredDependency:
    """One declared source with its freshness contract."""

    name: str
    proven: str = UNPROVEN
    last_seen_ts: Optional[float] = None
    window_s: Optional[float] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise DeclarationError("dependency name must be a non-empty string")
        if self.proven not in (PROVEN, UNPROVEN):
            raise DeclarationError("proven must be 'proven' or 'unproven'")
        if self.window_s is not None and (not math.isfinite(self.window_s) or self.window_s <= 0):
            raise DeclarationError("window_s must be positive and finite when provided")

    def freshness(self, now_ts: float):
        """Return (freshness, age_s); absent data is unknown, never green."""
        if self.last_seen_ts is None or self.window_s is None:
            return (UNKNOWN, None)
        age = now_ts - self.last_seen_ts
        if age < 0:
            return (UNKNOWN, None)
        if age <= self.window_s:
            return (FRESH, age)
        return (STALE, age)


@dataclass
class ReadinessReport:
    status: str
    evaluated_at: float
    reasons: List[str] = field(default_factory=list)
    per_dependency: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "evaluated_at": self.evaluated_at,
            "reasons": list(self.reasons),
            "per_dependency": {k: dict(v) for k, v in self.per_dependency.items()},
        }


class ReadinessEvaluator:
    """Evaluates readiness fail-closed from declared observations only."""

    def __init__(self, dependencies: Optional[List[DeclaredDependency]] = None):
        self.dependencies = list(dependencies or [])

    def evaluate(self, now_ts: Optional[float] = None) -> ReadinessReport:
        now = time.time() if now_ts is None else float(now_ts)
        if not self.dependencies:
            return ReadinessReport(
                status=UNKNOWN_STATUS,
                evaluated_at=now,
                reasons=["no declared dependencies: nothing is proven, never green"],
            )
        per = {}
        reasons: List[str] = []
        hard_failure = False
        unknown_freshness = False
        for dep in self.dependencies:
            freshness, age = dep.freshness(now)
            per[dep.name] = {
                "proven": dep.proven,
                "freshness": freshness,
                "age_s": age,
                "window_s": dep.window_s,
                "last_seen_ts": dep.last_seen_ts,
            }
            if dep.proven == UNPROVEN:
                hard_failure = True
                reasons.append("unproven declared dependency: " + dep.name)
            if freshness == STALE:
                hard_failure = True
                reasons.append("stale declared dependency: " + dep.name)
            elif freshness == UNKNOWN:
                unknown_freshness = True
                reasons.append("freshness unknown for declared dependency: " + dep.name)
        # Order-independent aggregate: a hard failure (unproven or stale) dominates
        # unknown freshness regardless of declaration order; unknown freshness
        # dominates READY. Never green unless every dependency is proven and fresh.
        if hard_failure:
            status = NOT_READY
        elif unknown_freshness:
            status = UNKNOWN_STATUS
        else:
            status = READY
        return ReadinessReport(status=status, evaluated_at=now, reasons=reasons, per_dependency=per)
