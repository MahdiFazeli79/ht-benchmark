"""Phase-2 insertion-engine spine (insertion.py). No API calls — MockLLMClient.

Exercises prompt build, response parsing, structural-diff ground truth, and the
reject-and-repair loop's wiring through the CostGuard (caps + yield floor).
"""
import pytest

from htbench import insertion as I
from htbench import cost_guard as CG

CLEAN = "module m(input a, output y);\n  assign y = a;\nendmodule\n"
INFECTED = ("module m(input a, output y);\n  wire t;\n  assign t = a & 1'b0;\n"
            "  assign y = a ^ t;\nendmodule\n")


def _spec():
    return I.InsertionSpec(clean_rtl=CLEAN, top_module="m", activation="triggered",
                           trigger_source="internal", trigger_mechanism="combinational",
                           payload="degrade_performance")


def _wrap(rtl):
    return f"Here you go.\n<INFECTED>\n{rtl}</INFECTED>\nDone."


def _guard(**kw):
    base = dict(total_usd_cap=10.0, per_run_usd_cap=1.0, yield_floor=0.2,
                yield_window=10, min_attempts_before_floor=8)
    base.update(kw)
    return CG.CostGuard(**base)


# --- prompt / parse / ground truth ---

def test_prompt_encodes_taxonomy_and_demands_delimited_block():
    p = I.build_prompt(_spec())
    assert "triggered" in p and "degrade_performance" in p
    assert "<INFECTED>" in p


def test_parse_infected_extracts_block():
    assert I.parse_infected(_wrap(INFECTED)).startswith("module m")


def test_parse_infected_missing_block_raises():
    with pytest.raises(ValueError):
        I.parse_infected("no block here")


def test_ground_truth_is_structural_diff():
    gt = I.ground_truth(CLEAN, INFECTED)
    assert gt["line_ranges"]                       # lines were added
    assert any("1'b0" in t for t in gt["added_text"])   # the inserted text, by diff


# --- reject-and-repair loop ---

def test_accept_on_first_attempt():
    g = _guard()
    client = I.MockLLMClient([_wrap(INFECTED)])
    res = I.generate_sample(_spec(), client, g, lambda *_: I.Verdict(True), max_repairs=3)
    assert res.accepted and res.attempts == 1
    assert g.spent_usd > 0 and g.acceptance_rate() == 1.0


def test_repair_then_accept():
    g = _guard()
    # first response malformed (no block) -> repair -> good
    client = I.MockLLMClient(["garbage", _wrap(INFECTED)])
    res = I.generate_sample(_spec(), client, g, lambda *_: I.Verdict(True), max_repairs=3)
    assert res.accepted and res.attempts == 2


def test_reject_after_exhausting_repairs():
    g = _guard()
    client = I.MockLLMClient([_wrap(INFECTED)])           # always parses
    verify = lambda *_: I.Verdict(False, "synth optimized it away")
    res = I.generate_sample(_spec(), client, g, verify, max_repairs=2)
    assert not res.accepted and res.attempts == 3        # 1 + 2 repairs
    assert "optimized" in res.reason
    assert g.acceptance_rate() == 0.0


def test_cost_guard_blocks_overspend_before_call():
    # per-run cap tiny -> the very first call is refused before spending
    g = _guard(per_run_usd_cap=1e-9)
    client = I.MockLLMClient([_wrap(INFECTED)])
    with pytest.raises(CG.BudgetExceeded):
        I.generate_sample(_spec(), client, g, lambda *_: I.Verdict(True))
    assert g.spent_usd == 0.0                            # nothing spent


def test_yield_floor_aborts_a_bad_batch():
    g = _guard(yield_floor=0.2, yield_window=10, min_attempts_before_floor=8)
    client = I.MockLLMClient([_wrap(INFECTED)])
    verify = lambda *_: I.Verdict(False, "always fails")
    # each sample rejects; after enough rejects the floor trips
    with pytest.raises(CG.YieldFloorAbort):
        for _ in range(12):
            g.new_run()                                  # fresh per-run budget each sample
            I.generate_sample(_spec(), client, g, verify, max_repairs=0)
