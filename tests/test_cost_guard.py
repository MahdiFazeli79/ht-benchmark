"""Phase-2 spend + yield circuit breaker (cost_guard.py). No API calls."""
import pytest

from htbench import cost_guard as G


def _guard(**kw):
    base = dict(total_usd_cap=10.0, per_run_usd_cap=3.0, yield_floor=0.25,
                yield_window=10, min_attempts_before_floor=10)
    base.update(kw)
    return G.CostGuard(**base)


# --- construction refuses a permissive/zero grant ---
def test_zero_or_negative_caps_rejected():
    with pytest.raises(ValueError):
        _guard(total_usd_cap=0)
    with pytest.raises(ValueError):
        _guard(per_run_usd_cap=-1)


def test_yield_floor_must_be_a_fraction():
    with pytest.raises(ValueError):
        _guard(yield_floor=0)
    with pytest.raises(ValueError):
        _guard(yield_floor=1.0)


# --- spend caps raise BEFORE the call ---
def test_pre_call_check_blocks_per_run_cap():
    g = _guard()
    g.pre_call_check(2.5)            # ok
    with pytest.raises(G.BudgetExceeded):
        g.pre_call_check(3.5)        # > per-run cap 3.0


def test_pre_call_check_blocks_total_cap():
    g = _guard(per_run_usd_cap=100.0)
    for _ in range(3):
        g.pre_call_check(3.0)
        g.record_spend(3.0)
        g.new_run()
    # spent 9, total cap 10
    g.pre_call_check(1.0)
    with pytest.raises(G.BudgetExceeded):
        g.pre_call_check(1.5)


def test_new_run_resets_per_run_not_total():
    g = _guard()
    g.pre_call_check(3.0); g.record_spend(3.0)
    g.new_run()
    g.pre_call_check(3.0); g.record_spend(3.0)   # new run allows another 3
    assert g.spent_usd == 6.0
    assert g.remaining_usd() == 4.0


# --- yield-floor circuit breaker ---
def test_yield_floor_does_not_trip_before_min_attempts():
    g = _guard(min_attempts_before_floor=10)
    for _ in range(9):
        g.record_outcome(False)     # all rejects, but below min_attempts
    assert g.acceptance_rate() == 0.0   # no raise yet


def test_yield_floor_aborts_when_rate_drops():
    g = _guard(yield_floor=0.25, yield_window=10, min_attempts_before_floor=10)
    # 2 accepts then 8 rejects -> last-10 window = 20% < 25% floor
    seq = [True, True] + [False] * 7
    for o in seq:
        g.record_outcome(o)
    with pytest.raises(G.YieldFloorAbort):
        g.record_outcome(False)     # 10th -> window rate 20% < floor


def test_healthy_yield_does_not_abort():
    g = _guard(yield_floor=0.25, yield_window=10, min_attempts_before_floor=10)
    for i in range(30):
        g.record_outcome(i % 2 == 0)   # 50% acceptance
    assert g.acceptance_rate() == 0.5


# --- cost estimation never silently zero ---
def test_estimate_cost_known_model():
    c = G.estimate_cost("claude-sonnet-4", 10_000, 2_000)
    assert c == pytest.approx(10_000 / 1e6 * 3.0 + 2_000 / 1e6 * 15.0)


def test_estimate_cost_unknown_model_raises():
    with pytest.raises(KeyError):
        G.estimate_cost("gpt-9", 1000, 1000)


def test_summary_shape():
    g = _guard()
    g.record_spend(1.25)
    g.record_outcome(True); g.record_outcome(False)
    s = g.summary()
    assert s["spent_usd"] == 1.25 and s["attempts"] == 2 and s["accepted"] == 1
    assert s["remaining_usd"] == 8.75
