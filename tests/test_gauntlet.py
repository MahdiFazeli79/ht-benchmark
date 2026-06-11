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
