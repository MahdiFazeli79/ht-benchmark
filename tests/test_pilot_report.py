"""Pilot report + manifest builder (pure — no toolchain, light CI job)."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from htbench import pilot as P
from htbench import insertion as I

SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "schemas" / "trojan_manifest.schema.json").read_text()))


def _result():
    return I.InsertionResult(
        True, "module m(input a, output y);\n  wire t;\n  assign y = a;\nendmodule\n",
        {"line_ranges": [[2, 2]], "added_text": ["  wire t;"]}, 2,
        activation={"trigger": "a==8'hDE", "observable_effect": "y flips"},
        verification={"activation_proof_method": "input_driven",
                      "reachability_established": True, "divergence_attribution": "trigger_only"})


def _spec():
    return I.InsertionSpec("module m...", "m", "triggered", "internal", "combinational",
                           "degrade_performance")


def test_build_manifest_is_schema_valid_and_carries_grade():
    man = P.build_manifest("s_001", _spec(), _result(), model="claude-sonnet-x",
                           prompt_hash="abc123", license="MIT",
                           license_url="https://opensource.org/licenses/MIT",
                           circuit_family="adder", variant_group="pilot_add8")
    assert [e.message for e in SCHEMA.iter_errors(man)] == []
    assert man["class"] == "infected"
    assert man["verification"]["activation_proof_method"] == "input_driven"
    assert man["verification"]["divergence_attribution"] == "trigger_only"
    assert man["inserted_rtl"]["line_ranges"] == [[2, 2]]    # from the structural diff


def test_report_metrics():
    r = P.PilotReport()
    cell = "triggered/combinational/degrade_performance"
    r.accepted = [
        {"sample_id": "a", "cell": cell, "sig": "x", "method": "input_driven", "witness": {}},
        {"sample_id": "b", "cell": cell, "sig": "x", "method": "input_driven", "witness": {}},
        {"sample_id": "c", "cell": "always_on/None/leak_information", "sig": "y",
         "method": "state_injection", "witness": {}}]
    r.rejected = [{"cell": cell, "reason": "witness not applicable to clean: ..."},
                  {"cell": cell, "reason": "functional_equivalence: not dormant"}]
    assert r.yield_rate == 3 / 5
    assert r.taxonomy_spread()[cell] == 2
    assert r.near_duplicate_clusters() == {"x": ["a", "b"]}      # a,b identical insertion
    assert r.method_spread()["input_driven"] == 2
    assert r.trojan_only_reject_rate() == 0.5                    # 1 of 2 rejects
    assert "pilot report" in r.render().lower()


# --- the structural near-dup signature (rename-robust) ---

def test_structural_signature_is_rename_and_const_robust():
    a = P._structural_signature("wire trig = (a==8'hDE)&&(b==8'hAD);\nassign sum = trig?9'h000:(a+b);")
    b = P._structural_signature("wire t0 = (a==8'hC1)&&(b==8'h22);\nassign sum = t0?9'h000:(a+b);")
    c = P._structural_signature("assign sum = (a+b)^{8'd0,a[0]};")
    assert a == b      # renamed signals + different magic constants -> same structure
    assert a != c      # genuinely different structure -> different


# --- proposed spec set ---

def test_default_pilot_specs_feasible_spans_taxonomy_and_repeats_a_cell():
    from collections import Counter
    specs = P.default_pilot_specs()                         # raises if any cell is R1-R3 infeasible
    assert len(specs) == 12
    cells = {(s.activation, s.trigger_mechanism, s.payload) for _, _, s, _ in specs}
    assert len(cells) >= 6                                  # breadth across the taxonomy
    counts = Counter((s.activation, s.trigger_source, s.trigger_mechanism, s.payload)
                     for _, _, s, _ in specs)
    assert max(counts.values()) >= 4                        # one cell repeated >=4x (mode-collapse probe)
    ids = [sid for sid, _, _, _ in specs]
    assert len(set(ids)) == len(ids)                        # unique sample ids


# --- GUARD-TRIP: prove the cost guard is ACTIVE inside run_pilot (no toolchain) ---

def test_run_pilot_yield_floor_aborts(tmp_path):
    # every response is unparseable -> every sample rejects -> after min_attempts the
    # yield floor trips and the pilot stops (no gauntlet/toolchain needed).
    client = I.MockLLMClient(["no blocks here"])
    specs = [(f"p_{i:03d}", "module m(input a, output y); assign y=a; endmodule", _spec(), {})
             for i in range(10)]
    rep = P.run_pilot(specs, tmp_path, api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1.0,
                      yield_floor=0.20, yield_window=10, min_attempts_before_floor=8,
                      client=client, max_repairs=0)
    assert rep.aborted.startswith("yield-floor")
    assert not rep.accepted and len(rep.rejected) < 10      # stopped early


def test_run_pilot_budget_refuses_before_spending(tmp_path):
    # per-run cap is below any call's cost -> pre_call_check refuses the FIRST call,
    # before the client is invoked. Nothing spends.
    client = I.MockLLMClient(["whatever"])
    specs = [("p_001", "module m(input a, output y); assign y=a; endmodule", _spec(), {})]
    rep = P.run_pilot(specs, tmp_path, api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1e-9, client=client)
    assert rep.aborted.startswith("budget")
    assert not rep.accepted and rep.spent_usd == 0.0
