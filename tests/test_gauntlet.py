"""Phase-2 mechanical verification gauntlet (gauntlet.py). Needs iverilog + yosys.

Fixtures: a combinational adder with a rare INPUT-SPACE Trojan (matches the locked
prompt's design) — dormant on random inputs, fires only on (a,b)=(0xDE,0xAD).
"""
import shutil

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


# --- activation-proof (the trigger-half of FE; reuses simulate + _mismatches) ---

# state-injection fixture: a counter whose alarm fires only at count==0xC7
CLEAN_CTR = ("module ctr(input clk, input rst_n, input en, output reg [7:0] count, output alarm);\n"
             "  assign alarm = 1'b0;\n"
             "  always @(posedge clk or negedge rst_n) if(!rst_n) count<=0; else if(en) count<=count+1;\n"
             "endmodule\n")
INF_CTR = ("module ctr(input clk, input rst_n, input en, output reg [7:0] count, output alarm);\n"
           "  assign alarm = (count == 8'hC7);\n"
           "  always @(posedge clk or negedge rst_n) if(!rst_n) count<=0; else if(en) count<=count+1;\n"
           "endmodule\n")


def test_activation_proof_input_driven_pass():
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8",
                           {"trigger": "a == 8'hDE with b == 8'hAD", "observable_effect": "sum=0"})
    assert v.ok
    assert v.detail["activation_proof_method"] == "input_driven"
    assert v.detail["reachability_established"] is True
    assert v.detail["divergence_attribution"] == "trigger_only"   # NOT payload_confirmed


def test_activation_proof_state_injection_pass():
    v = G.activation_proof(CLEAN_CTR, INF_CTR, "ctr",
                           {"trigger": "count == 8'hC7", "observable_effect": "alarm=1"})
    assert v.ok
    assert v.detail["activation_proof_method"] == "state_injection"
    assert v.detail["reachability_established"] is False          # forced, not reached


def test_activation_proof_input_driven_but_no_reset_is_not_reachable():
    # Stateful module with NO reset: input-driven divergence, but the state starts
    # at X -> reachability cannot be claimed even though method is input_driven.
    clean = ("module lat(input clk, input [7:0] d, output reg [7:0] q);\n"
             "  always @(posedge clk) q <= d;\nendmodule\n")
    inf = ("module lat(input clk, input [7:0] d, output reg [7:0] q);\n"
           "  always @(posedge clk) q <= (d == 8'h5A) ? 8'h00 : d;\nendmodule\n")
    v = G.activation_proof(clean, inf, "lat", {"trigger": "d == 8'h5A", "observable_effect": "q=0"})
    assert v.ok
    assert v.detail["activation_proof_method"] == "input_driven"
    assert v.detail["reachability_established"] is False        # no reset -> not established


def test_activation_proof_no_divergence_rejects():
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8", {"trigger": "a == 8'h01 with b == 8'h02"})
    assert not v.ok and "no divergence" in v.reason


def test_activation_proof_unparseable_rejects():
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8", {"trigger": "magic rare value"})
    assert not v.ok and "un-parseable" in v.reason


# divergence-window diagnostic: a sequential payload that surfaces N cycles after the
# forced trigger, which the single-sample decision TB observes too early.
_SEQ_CLEAN = ("module d(input clk, input rst_n, input [7:0] s_in, output reg [7:0] o);\n"
              "  reg [7:0] s;\n"
              "  always @(posedge clk or negedge rst_n)\n"
              "    if(!rst_n) begin s<=0; o<=0; end else begin s<=s_in; o<=s; end\nendmodule\n")
_SEQ_INF_NOW = ("module d(input clk, input rst_n, input [7:0] s_in, output reg [7:0] o);\n"
                "  reg [7:0] s;\n"
                "  always @(posedge clk or negedge rst_n)\n"
                "    if(!rst_n) begin s<=0; o<=0; end else begin s<=s_in; o<=(s==8'hC7)?8'hFF:s; end\n"
                "endmodule\n")
_SEQ_INF_DELAY = ("module d(input clk, input rst_n, input [7:0] s_in, output reg [7:0] o);\n"
                  "  reg [7:0] s; reg [2:0] dly;\n"
                  "  always @(posedge clk or negedge rst_n)\n"
                  "    if(!rst_n) begin s<=0; o<=0; dly<=0; end\n"
                  "    else begin s<=s_in; o<=s; dly<={dly[1:0],(s==8'hC7)}; if(dly[2]) o<=8'hAA; end\n"
                  "endmodule\n")


def test_divergence_cycle_diagnostic_measures_latency():
    ports = G.parse_ports(_SEQ_CLEAN, "d")
    f = {"s": 0xC7}                                              # force the host register at the trigger
    assert G._divergence_cycle(_SEQ_CLEAN, _SEQ_CLEAN, "d", ports, {}, f) is None    # identical
    assert G._divergence_cycle(_SEQ_CLEAN, _SEQ_INF_NOW, "d", ports, {}, f) == 0     # immediate
    assert G._divergence_cycle(_SEQ_CLEAN, _SEQ_INF_DELAY, "d", ports, {}, f) == 3   # 3-cycle latency


def test_activation_proof_no_divergence_carries_diagnostic():
    # the single-sample decision rejects (observes too early), but the diagnostic
    # records WHEN the sequential payload would surface — the TB-timing fix parameter.
    v = G.activation_proof(_SEQ_CLEAN, _SEQ_INF_DELAY, "d",
                           {"trigger": "s=8'hC7", "observable_effect": "o=AA"})
    assert not v.ok and "no divergence" in v.reason             # decision still rejects
    assert v.detail["divergence_cycle_diagnostic"] == 3         # latency captured in the grade
    assert "cycle 3" in v.reason                                # and surfaced in the reason/trail


def test_activation_proof_not_applicable_self_classifies_structural():
    # a Trojan-internal witness (net absent from clean) fails at COMPILE, and the
    # reason marks it structural so (c) auto-classifies without RTL inspection.
    v = G.activation_proof(CLEAN, INF_STEALTHY, "add8",
                           {"trigger": "trojan_secret = 8'h01", "observable_effect": "x"})
    assert not v.ok and "not applicable to clean" in v.reason
    assert "structural" in v.reason


def test_run_full_passes_and_carries_grade():
    v = G.run_full(CLEAN, INF_STEALTHY, "add8",
                   {"trigger": "a == 8'hDE with b == 8'hAD", "observable_effect": "sum=0"})
    assert v.ok and v.detail["activation_proof_method"] == "input_driven"


def test_run_full_fails_on_bad_witness():
    v = G.run_full(CLEAN, INF_STEALTHY, "add8", {"trigger": "a == 8'h00 with b == 8'h00"})
    assert not v.ok and v.reason.startswith("activation_proof:")
