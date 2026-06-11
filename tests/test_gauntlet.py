"""Phase-2 mechanical verification gauntlet (gauntlet.py). Needs iverilog + yosys.

Fixtures: a combinational adder with a rare INPUT-SPACE Trojan (matches the locked
prompt's design) — dormant on random inputs, fires only on (a,b)=(0xDE,0xAD).
"""
import json
import shutil
from pathlib import Path

import pytest

if shutil.which("iverilog") is None or shutil.which("yosys") is None:
    pytest.skip("iverilog/yosys not on PATH", allow_module_level=True)

from htbench import gauntlet as G  # noqa: E402

CLEAN = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
         "  assign sum = a + b;\nendmodule\n")
# stealthy: rare input-space trigger -> corrupt sum; dormant everywhere else
INF_STEALTHY = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
                "  wire trig = (a == 8'hDE) && (b == 8'hAD);\n"
                "  assign sum = trig ? 9'h000 : (a + b);\nendmodule\n")
# not stealthy: diverges on ~half of inputs
INF_BROAD = ("module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n"
             "  assign sum = (a + b) ^ {8'd0, a[0]};\nendmodule\n")
# does not compile
INF_BADSYNTAX = "module add8(input a, output y); assign y = ;\nendmodule\n"


def test_compile_ok_pass_and_fail():
    assert G.compile_ok(INF_STEALTHY, "add8").ok
    assert not G.compile_ok(INF_BADSYNTAX, "add8").ok


def test_parse_ports_combinational():
    p = G.parse_ports(CLEAN, "add8")
    assert ("a", 8) in p["inputs"] and ("sum", 9) in p["outputs"]
    assert p["clk"] is None


def test_functional_equivalence_dormant_passes():
    # A stealthy Trojan is dormant on random inputs -> FE passes.
    assert G.functional_equivalence(CLEAN, INF_STEALTHY, "add8").ok


def test_functional_equivalence_broad_divergence_fails():
    v = G.functional_equivalence(CLEAN, INF_BROAD, "add8")
    assert not v.ok and "not dormant" in v.reason


def test_synth_survival_pass_and_fail():
    assert G.synth_survival(CLEAN, INF_STEALTHY, "add8").ok          # added logic survives
    v = G.synth_survival(CLEAN, CLEAN, "add8")                       # no added logic
    assert not v.ok and "optimized away" in v.reason


def test_run_mechanical_passes_stealthy_and_reports_stage_on_fail():
    assert G.run_mechanical(CLEAN, INF_STEALTHY, "add8").ok
    v = G.run_mechanical(CLEAN, INF_BROAD, "add8")
    assert not v.ok and v.reason.startswith("functional_equivalence:")


# --- activation-proof: drive-to-state (pure, no force) ---

# counter with a freeze-on-count==0xA5 Trojan (the seqrecheck 001 recovery case):
# DRIVE count to 0xA5 via en=1, then the freeze diverges from clean — observable
# precisely because count is reached, not forced.
_CTR_CLEAN = ("module counter8(input clk, input rst_n, input en, output reg [7:0] count);\n"
              "  always @(posedge clk or negedge rst_n) if(!rst_n) count<=0; else if(en) count<=count+1;\n"
              "endmodule\n")
_CTR_FREEZE = ("module counter8(input clk, input rst_n, input en, output reg [7:0] count);\n"
               "  reg trojan_lock;\n"
               "  always @(posedge clk or negedge rst_n) begin\n"
               "    if(!rst_n) begin count<=0; trojan_lock<=0; end\n"
               "    else begin if(count==8'hA5 && en) trojan_lock<=1'b1;\n"
               "      if(trojan_lock) count<=count; else if(en) count<=count+1; end\n"
               "  end\nendmodule\n")


def test_activation_proof_combinational_input_driven_pass():
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8",
                           {"trigger": "a == 8'hDE with b == 8'hAD", "observable_effect": "sum=0"})
    assert v.ok
    assert v.detail["activation_proof_method"] == "input_driven"
    assert v.detail["reachability_established"] is True
    assert v.detail["divergence_attribution"] == "trigger_only"   # NOT payload_confirmed


def test_drive_to_state_reaches_and_accepts():
    # the recovery: a sequential freeze Trojan the old force path masked now accepts,
    # graded the STRONGER input_driven + reachability_established tier.
    v = G.activation_proof(_CTR_CLEAN, _CTR_FREEZE, "counter8",
                           {"trigger": "count == 8'hA5 with en=1", "observable_effect": "count freezes"})
    assert v.ok
    assert v.detail["activation_proof_method"] == "input_driven"
    assert v.detail["reachability_established"] is True
    assert v.detail["reached_cycle"] >= 0


def test_drive_to_state_structural_when_no_host_predicate():
    # a witness keyed on a Trojan-internal net (absent from clean) has nothing host-
    # observable to drive to -> structural, not a force.
    v = G.activation_proof(_CTR_CLEAN, _CTR_FREEZE, "counter8",
                           {"trigger": "trojan_lock == 1 with en=1", "observable_effect": "x"})
    assert not v.ok and v.reason.startswith("structural")


def test_drive_to_state_not_reachable_in_budget():
    # en held 0 -> count never advances -> the predicate is genuinely unreachable.
    v = G.activation_proof(_CTR_CLEAN, _CTR_FREEZE, "counter8",
                           {"trigger": "count == 8'hA5 with en=0", "observable_effect": "x"}, budget=64)
    assert not v.ok and v.reason.startswith("not-reachable-in-budget")


def test_drive_to_state_payload_unobservable_when_reached_but_no_divergence():
    # clean vs clean: the trigger is reached but nothing diverges -> payload_unobservable
    # (a Trojan that cannot fire lands here too — the seqrecheck 002 case).
    v = G.activation_proof(_CTR_CLEAN, _CTR_CLEAN, "counter8",
                           {"trigger": "count == 8'hA5 with en=1", "observable_effect": "x"}, budget=256)
    assert not v.ok and v.reason.startswith("payload_unobservable")


def test_activation_proof_unparseable_rejects():
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8", {"trigger": "magic rare value"})
    assert not v.ok and "un-parseable" in v.reason


def test_drive_to_state_does_not_regress_committed_accepts():
    # §4 regression gate: every previously-accepted sample (pilot 1 + batch 2, all
    # combinational input-vector witnesses) must still accept via the degenerate path.
    import glob
    root = Path(__file__).resolve().parents[1]
    n = ok = 0
    for sd in sorted(glob.glob(str(root / "batch2_out/*/")) + glob.glob(str(root / "pilot_out/*/"))):
        man = Path(sd, "trojan_manifest.json")
        if not man.exists():
            continue
        top = json.loads(man.read_text())["top_module"]
        clean = (Path(sd) / "clean.v").read_text()
        inf = (Path(sd) / "infected.v").read_text()
        wit = json.loads((Path(sd) / "activation_witness.json").read_text())
        n += 1
        ok += 1 if G.activation_proof(clean, inf, top, wit).ok else 0
    assert n >= 17 and ok == n          # superset: no committed accept regresses


def test_run_full_passes_and_carries_grade():
    v = G.run_full(CLEAN, INF_STEALTHY, "add8",
                   {"trigger": "a == 8'hDE with b == 8'hAD", "observable_effect": "sum=0"})
    assert v.ok and v.detail["activation_proof_method"] == "input_driven"


def test_run_full_fails_on_bad_witness():
    v = G.run_full(CLEAN, INF_STEALTHY, "add8", {"trigger": "a == 8'h00 with b == 8'h00"})
    assert not v.ok and v.reason.startswith("activation_proof:")
