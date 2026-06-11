"""Phase-2 spend + yield circuit breaker — the Tier-3 guard, encoded not trusted.

The paid LLM insertion loop (Phase 2) is the project's one unbounded, irreversible
action. This guard makes the limits STRUCTURAL: every LLM call routes through it,
it raises BEFORE a call that would breach a cap, and it aborts the reject-and-
repair loop the moment the acceptance rate proves the corpus is one the model is
bad at. The two failure shapes it stops:

  - Overspend — a per-run cap and a total cap. `pre_call_check(est_usd)` refuses a
    call that would cross either, so spend can never exceed the ceiling (a dollar
    cap that only checks *after* the call stops you after the waste).
  - Runaway retry — a yield-floor abort. If acceptance over the recent window
    falls below the floor, the loop stops and reports. A dollar cap stops you
    after the waste; the yield floor stops you at the moment the waste becomes
    predictable (the circuit breaker a pure dollar cap doesn't give).

No standing grant: the caps are passed in per session, never defaulted to
something permissive. This module performs NO API calls and imports no SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Anthropic list prices (USD per 1M tokens), for pre-call cost estimation. Update
# when prices change; pinned here so an estimate is never silently wrong.
PRICING = {
    "claude-opus-4":   {"in": 15.0, "out": 75.0},
    "claude-sonnet-4": {"in": 3.0,  "out": 15.0},
    "claude-haiku-4":  {"in": 1.0,  "out": 5.0},
}


class BudgetExceeded(RuntimeError):
    """A call would cross the per-run or total spend cap. Raised BEFORE the call."""


class YieldFloorAbort(RuntimeError):
    """Acceptance rate fell below the floor — stop and report, do not keep retrying."""


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    """Estimate USD for a call from token counts. Unknown model raises (never
    silently price at zero)."""
    if model not in PRICING:
        raise KeyError(f"no pricing for model {model!r}; add it to cost_guard.PRICING")
    p = PRICING[model]
    return in_tokens / 1e6 * p["in"] + out_tokens / 1e6 * p["out"]


@dataclass
class CostGuard:
    """Per-session spend + yield circuit breaker. Construct with explicit caps;
    route every paid call through `pre_call_check` → (make call) → `record_spend`,
    and every sample outcome through `record_outcome`."""

    total_usd_cap: float
    per_run_usd_cap: float
    yield_floor: float                       # min acceptance rate, e.g. 0.25
    yield_window: int = 20                    # measured over the last N attempts
    min_attempts_before_floor: int = 20       # don't trip on early-sample noise

    spent_usd: float = 0.0
    run_spent_usd: float = 0.0
    _outcomes: list[bool] = field(default_factory=list)

    def __post_init__(self):
        for name, v in (("total_usd_cap", self.total_usd_cap),
                        ("per_run_usd_cap", self.per_run_usd_cap)):
            if v <= 0:
                raise ValueError(f"{name} must be > 0 (no standing/zero grant): {v}")
        if not 0.0 < self.yield_floor < 1.0:
            raise ValueError(f"yield_floor must be in (0,1): {self.yield_floor}")

    # --- spend ---
    def pre_call_check(self, est_usd: float) -> None:
        """Raise BEFORE a call whose estimated cost would breach either cap."""
        if est_usd < 0:
            raise ValueError("est_usd must be >= 0")
        if self.run_spent_usd + est_usd > self.per_run_usd_cap:
            raise BudgetExceeded(
                f"per-run cap ${self.per_run_usd_cap:.2f} would be exceeded "
                f"(run spent ${self.run_spent_usd:.2f} + est ${est_usd:.2f})")
        if self.spent_usd + est_usd > self.total_usd_cap:
            raise BudgetExceeded(
                f"total cap ${self.total_usd_cap:.2f} would be exceeded "
                f"(spent ${self.spent_usd:.2f} + est ${est_usd:.2f})")

    def record_spend(self, actual_usd: float) -> None:
        self.spent_usd += actual_usd
        self.run_spent_usd += actual_usd

    def new_run(self) -> None:
        """Reset the per-run counter at the start of a generation run."""
        self.run_spent_usd = 0.0

    def remaining_usd(self) -> float:
        return max(0.0, self.total_usd_cap - self.spent_usd)

    # --- yield ---
    def record_outcome(self, accepted: bool) -> None:
        """Record one sample's accept/reject outcome; raise if the recent
        acceptance rate has fallen below the floor."""
        self._outcomes.append(bool(accepted))
        if len(self._outcomes) < self.min_attempts_before_floor:
            return
        window = self._outcomes[-self.yield_window:]
        rate = sum(window) / len(window)
        if rate < self.yield_floor:
            raise YieldFloorAbort(
                f"acceptance {rate:.0%} over last {len(window)} < floor "
                f"{self.yield_floor:.0%}; stopping rather than burning budget")

    def acceptance_rate(self) -> float:
        return sum(self._outcomes) / len(self._outcomes) if self._outcomes else 0.0

    def summary(self) -> dict:
        return {
            "spent_usd": round(self.spent_usd, 4),
            "total_cap_usd": self.total_usd_cap,
            "remaining_usd": round(self.remaining_usd(), 4),
            "attempts": len(self._outcomes),
            "accepted": sum(self._outcomes),
            "acceptance_rate": round(self.acceptance_rate(), 4),
        }
