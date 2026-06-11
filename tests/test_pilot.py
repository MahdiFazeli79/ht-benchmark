"""Pilot driver end-to-end with a MOCK client — real gauntlet (iverilog+yosys),
ZERO spend. Proves the held run_pilot wiring before any paid call."""
import json
import shutil
from pathlib import Path

import pytest

if shutil.which("iverilog") is None or shutil.which("yosys") is None:
    pytest.skip("iverilog/yosys not on PATH", allow_module_level=True)

from jsonschema import Draft202012Validator  # noqa: E402

from htbench import pilot as P  # noqa: E402
from htbench import insertion as I  # noqa: E402

CLEAN = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
         "  assign sum = a + b;\nendmodule\n")
INF = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
       "  wire trig = (a == 8'hDE) && (b == 8'hAD);\n"
       "  assign sum = trig ? 9'h000 : (a + b);\nendmodule\n")
INF_BROAD = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
             "  assign sum = (a + b) ^ {8'd0, a[0]};\nendmodule\n")
META = {"license": "MIT", "license_url": "https://opensource.org/licenses/MIT",
        "circuit_family": "adder", "variant_group": "pilot_add8"}
SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "schemas" / "trojan_manifest.schema.json").read_text()))


def _resp(rtl, trigger="a == 8'hDE with b == 8'hAD", effect="sum forced to 0"):
    return (f"<INFECTED>\n{rtl}</INFECTED>\n"
            f"<ACTIVATION>\ntrigger: {trigger}\nobservable_effect: {effect}\n</ACTIVATION>\n")


def _spec():
    return I.InsertionSpec(CLEAN, "add8", "triggered", "internal", "combinational",
                           "degrade_performance")


def test_run_pilot_accepts_and_writes_schema_valid_sample(tmp_path):
    client = I.MockLLMClient([_resp(INF)])               # no API, no spend
    specs = [("s_add8_001", CLEAN, _spec(), META)]
    rep = P.run_pilot(specs, tmp_path, api_model="claude-sonnet-x",
                      pricing_key="claude-sonnet-4", total_usd_cap=10.0,
                      per_run_usd_cap=1.0, client=client)
    assert len(rep.accepted) == 1 and not rep.rejected
    assert rep.spent_usd > 0 and rep.yield_rate == 1.0
    d = tmp_path / "s_add8_001"
    assert (d / "clean.v").exists() and (d / "infected.v").exists()
    man = json.loads((d / "trojan_manifest.json").read_text())
    assert [e.message for e in SCHEMA.iter_errors(man)] == []          # schema-valid
    assert man["verification"]["activation_proof_method"] == "input_driven"
    assert rep.accepted[0]["method"] == "input_driven"


def test_run_pilot_rejects_non_stealthy_trojan(tmp_path):
    client = I.MockLLMClient([_resp(INF_BROAD)])
    rep = P.run_pilot([("s_bad", CLEAN, _spec(), META)], tmp_path,
                      api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1.0, client=client, max_repairs=0)
    assert not rep.accepted and len(rep.rejected) == 1
    assert "functional_equivalence" in rep.rejected[0]["reason"]
    assert not (tmp_path / "s_bad").exists()              # nothing written for a reject
