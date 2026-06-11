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


# a counter: en is the held stimulus; clk/rst are TB-owned; count is host-observable.
PORTS = {"inputs": [("clk", 1), ("rst_n", 1), ("en", 1)], "data_inputs": [("en", 1)],
         "outputs": [("count", 8)], "clk": "clk", "rst": "rst_n"}
CLEAN_SIGS = {"clk", "rst_n", "en", "count"}


def test_drive_witness_splits_held_reach_internal():
    w = G.parse_drive_witness("count == 8'hA5 with en=1", PORTS, CLEAN_SIGS)
    assert w["held_inputs"] == {"en": 1}             # data input held during the drive
    assert w["reach"] == ("count", 0xA5)             # host-observable predicate to drive to
    assert w["internal_refs"] == []


def test_drive_witness_drops_clk_rst_and_flags_internal():
    w = G.parse_drive_witness("rst_n=0 then count == 8'hAA with en=1 and trojan_cnt == 2'b11",
                              PORTS, CLEAN_SIGS)
    assert "rst_n" not in w["held_inputs"]           # reset is TB-owned, not a held stimulus
    assert w["held_inputs"] == {"en": 1}
    assert w["reach"] == ("count", 0xAA)             # host predicate preferred
    assert w["internal_refs"] == ["trojan_cnt"]      # Trojan-internal flagged, not driven to


def test_extract_settle_is_consecutive_not_drive_length():
    assert G._extract_settle("keep en=1 for 3 consecutive rising clock edges") == 3
    assert G._extract_settle("apply en=1 for 254 clock cycles") == 0   # drive length, NOT settle
    assert G._extract_settle("count reaches 8'hA5 after 165 increments") == 0
    assert G._extract_settle("hold for 9000 more cycles", cap=64) == 64  # capped


def test_drive_witness_unparseable_fails_loud():
    with pytest.raises(ValueError):
        G.parse_drive_witness("fires on a rare magic condition", PORTS, CLEAN_SIGS)
