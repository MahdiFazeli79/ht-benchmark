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


def _wrap(rtl, trigger="count == 8'hC7 with en=1", effect="count freezes"):
    return (f"Sure.\n<INFECTED>\n{rtl}</INFECTED>\n"
            f"<ACTIVATION>\ntrigger: {trigger}\nobservable_effect: {effect}\n</ACTIVATION>\n")


def _guard(**kw):
    base = dict(total_usd_cap=10.0, per_run_usd_cap=1.0, yield_floor=0.2,
                yield_window=10, min_attempts_before_floor=8)
    base.update(kw)
    return CG.CostGuard(**base)


# --- prompt / parse / ground truth ---

def test_prompt_defensive_framing_taxonomy_and_two_blocks():
    p = I.build_prompt(_spec())
    assert "DETECTORS" in p and "defensive" in p            # framing leads with defense
    assert "triggered" in p and "degrade_performance" in p  # spec-driven taxonomy
    assert "<INFECTED>" in p and "<ACTIVATION>" in p         # two-block contract
    assert "INPUT/STATE SPACE" in p                          # rarity biased off time-depth


def test_repair_addendum_mentions_both_blocks():
    p = I.build_prompt(_spec(), repair_feedback="synth folded it away")
    assert "both blocks again" in p and "synth folded it away" in p


def test_parse_infected_extracts_block():
    assert I.parse_infected(_wrap(INFECTED)).startswith("module m")


def test_parse_infected_missing_block_raises():
    with pytest.raises(ValueError):
        I.parse_infected("no block here")


def test_parse_activation_extracts_fields():
    a = I.parse_activation(
        "<ACTIVATION>\ntrigger: count==8'hC7 with en=1\nobservable_effect: count freezes\n</ACTIVATION>")
    assert a["trigger"] == "count==8'hC7 with en=1"
    assert a["observable_effect"] == "count freezes"


def test_parse_activation_missing_or_incomplete_raises():
    with pytest.raises(ValueError):
        I.parse_activation("<INFECTED>x</INFECTED>")            # no witness block
    with pytest.raises(ValueError):
        I.parse_activation("<ACTIVATION>\ntrigger: x\n</ACTIVATION>")   # no effect


def test_spec_feasibility_guard_blocks_forbidden_cells():
    # R3: always_on payload must be leak/degrade
    with pytest.raises(ValueError):
        I.InsertionSpec(CLEAN, "m", "always_on", None, None, "change_functionality")
    # R1: always_on must have null triggers
    with pytest.raises(ValueError):
        I.InsertionSpec(CLEAN, "m", "always_on", "internal", None, "leak_information")
    # R2: triggered must have non-null triggers
    with pytest.raises(ValueError):
        I.InsertionSpec(CLEAN, "m", "triggered", None, None, "degrade_performance")
    # a feasible always_on cell constructs fine
    I.InsertionSpec(CLEAN, "m", "always_on", None, None, "leak_information")


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
    assert res.activation["trigger"] == "count == 8'hC7 with en=1"   # witness carried
    assert g.spent_usd > 0 and g.acceptance_rate() == 1.0
    assert res.steered is False                                      # no steering on a clean accept


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


# --- prompt_v2: host-observable witness steering (no spend) ---

def test_prompt_version_is_v2():
    # Guards an accidental bump; the manifest stamps this value.
    assert I.PROMPT_VERSION == "v2"


def test_locked_base_body_has_no_steering():
    # v2 keeps the v1 base body byte-identical: the steering lives ONLY in the
    # repair channel, never in the base prompt.
    base = I.build_prompt(_spec())
    assert "replayed against the clean module" not in base
    assert "INPUT/STATE SPACE" in base                     # locked body intact


def test_steer_feedback_fires_only_on_trojan_internal_witness():
    internal = I._steer_feedback("witness not applicable to clean: cannot bind dut.trojan_cnt")
    assert "ONLY signals that exist in the clean module" in internal
    assert "replayed against the clean module" in internal
    other = I._steer_feedback("synth optimized it away")
    assert other == "synth optimized it away"              # unrelated reasons pass through


def test_repair_prompt_carries_host_observable_steering():
    # A witness that keys on Trojan-internal state fails clean-applicability on
    # attempt 1; the SECOND prompt the model sees must carry the steering.
    class _RecordingMock(I.MockLLMClient):
        prompts: list = None
        def complete(self, prompt):
            (self.prompts if self.prompts is not None else []).append(prompt)
            return super().complete(prompt)

    seen = []
    client = _RecordingMock([_wrap(INFECTED), _wrap(INFECTED)])
    client.prompts = seen
    calls = {"n": 0}
    def verify(*_):
        calls["n"] += 1
        return (I.Verdict(False, "witness not applicable to clean: cannot bind dut.trojan_cnt")
                if calls["n"] == 1 else I.Verdict(True))
    res = I.generate_sample(_spec(), client, _guard(), verify, max_repairs=3)
    assert res.accepted and res.attempts == 2
    assert res.steered is True                              # flag set for the conversion metric
    assert len(seen) == 2
    assert "replayed against the clean module" in seen[1]   # steering reached attempt 2
    assert "replayed against the clean module" not in seen[0]
    assert "witness not applicable to clean" not in res.reason  # accepted: reason clean


def test_cost_guard_blocks_overspend_before_call():
    # per-run cap tiny -> the very first call is refused before spending
    g = _guard(per_run_usd_cap=1e-9)
    client = I.MockLLMClient([_wrap(INFECTED)])
    with pytest.raises(CG.BudgetExceeded):
        I.generate_sample(_spec(), client, g, lambda *_: I.Verdict(True))
    assert g.spent_usd == 0.0                            # nothing spent


def test_anthropic_client_wires_tokens_without_sdk_or_spend():
    # Inject a fake SDK client -> no anthropic import, no network, no cost.
    class _Block:
        type = "text"
        text = _wrap(INFECTED)

    class _Resp:
        content = [_Block()]
        usage = type("U", (), {"input_tokens": 120, "output_tokens": 47})()

    class _FakeSDK:
        def __init__(self):
            self.messages = self
            self.seen = {}

        def create(self, **kw):
            self.seen = kw
            return _Resp()

    sdk = _FakeSDK()
    c = I.AnthropicClient(model="claude-sonnet-x", _client=sdk)
    r = c.complete("hello")
    assert r.in_tokens == 120 and r.out_tokens == 47 and r.model == "claude-sonnet-x"
    assert "<INFECTED>" in r.text
    assert sdk.seen["model"] == "claude-sonnet-x"          # model id forwarded
    assert sdk.seen["temperature"] == 1.0                  # temperature pinned, not API-default


def test_load_env_sets_without_override(tmp_path, monkeypatch):
    import os
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("HTBENCH_TEST_KEY=from_file\n# comment\n")
    monkeypatch.delenv("HTBENCH_TEST_KEY", raising=False)
    I.load_env()
    assert os.environ["HTBENCH_TEST_KEY"] == "from_file"
    # does not override an already-set var
    os.environ["HTBENCH_TEST_KEY"] = "preset"
    I.load_env()
    assert os.environ["HTBENCH_TEST_KEY"] == "preset"


def test_yield_floor_aborts_a_bad_batch():
    g = _guard(yield_floor=0.2, yield_window=10, min_attempts_before_floor=8)
    client = I.MockLLMClient([_wrap(INFECTED)])
    verify = lambda *_: I.Verdict(False, "always fails")
    # each sample rejects; after enough rejects the floor trips
    with pytest.raises(CG.YieldFloorAbort):
        for _ in range(12):
            g.new_run()                                  # fresh per-run budget each sample
            I.generate_sample(_spec(), client, g, verify, max_repairs=0)
