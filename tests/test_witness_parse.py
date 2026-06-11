"""Activation-witness parsing (pure — no toolchain, runs in the light CI job).

The parser only turns the witness into a stimulus (applied inputs vs forced
state); it never interprets the trigger. Lenient, fail-loud on un-parseable.
"""
import pytest

from htbench import gauntlet as G


def test_parse_value_verilog_literals():
    assert G._parse_value("8'hC7") == 0xC7
    assert G._parse_value("3'b101") == 5
    assert G._parse_value("8'd42") == 42
    assert G._parse_value("0xFF") == 255
    assert G._parse_value("12") == 12
    assert G._parse_value("8'hA_7") == 0xA7          # underscores ignored
    assert G._parse_value("4'bxx01") == 1            # x/z → 0 for stimulus


PORTS = {"inputs": [("a", 8), ("b", 8), ("en", 1)], "data_inputs": [("a", 8), ("b", 8), ("en", 1)]}


def test_applied_input_vs_forced_state_classification():
    # a, b, en are input ports -> applied; count is not a port -> forced (state)
    w = G.parse_witness("a == 8'hDE with b == 8'hAD and en=1", PORTS)
    assert w["inputs"] == {"a": 0xDE, "b": 0xAD, "en": 1}
    assert w["forces"] == {}
    assert w["method"] == "input_driven"

    w2 = G.parse_witness("count == 8'hC7 with en=1", PORTS)
    assert w2["inputs"] == {"en": 1}
    assert w2["forces"] == {"count": 0xC7}           # internal -> force
    assert w2["method"] == "state_injection"


def test_unparseable_witness_fails_loud():
    with pytest.raises(ValueError):
        G.parse_witness("fires on a rare magic condition", PORTS)


def test_witness_tb_windowed_vs_single_sample():
    # The decision TB (observe_cycles=1) is unchanged: one sample. The diagnostic TB
    # (observe_cycles>1, clocked) samples every cycle for the divergence-window probe.
    ports = G.parse_ports(
        "module c(input clk, input rst_n, output reg [7:0] q);\n"
        "  always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=q+1;\n"
        "endmodule\n", "c")
    single = G._gen_witness_tb("c", ports, {}, {"q": 0xC7})
    windowed = G._gen_witness_tb("c", ports, {}, {"q": 0xC7}, observe_cycles=8)
    assert "repeat(" not in single and single.count("$display") == 1   # decision TB unchanged
    assert "repeat(8)" in windowed                                     # per-cycle observation
