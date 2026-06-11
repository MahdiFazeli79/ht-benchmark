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
