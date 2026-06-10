"""Phase-1 circuit-list gate (circuit_list.py, task #28).

Pure dict-driven tests — no PyYAML, no filesystem — so this runs in CI's light
job. The R10 allowlist is passed in directly.
"""
from htbench import circuit_list as C

ALLOW = {"Apache-2.0", "MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Solderpad-2.1"}


def _row(**kw):
    base = dict(variant_group="vg", circuit_family="aes", source="github:x/y",
                license="MIT", language="verilog", parse_path="verilog_direct", bin="m")
    base.update(kw)
    return base


def test_clean_list_is_structurally_valid():
    data = {"candidates": [_row(variant_group="a"), _row(variant_group="b")], "rejected": []}
    rep = C.check_circuit_list(data, ALLOW)
    assert rep.structurally_valid
    assert rep.n_candidates == 2
    assert rep.n_eligible == 2
    assert not rep.blocked


def test_missing_required_field_is_structural_error():
    bad = _row(variant_group="a"); bad.pop("license")
    rep = C.check_circuit_list({"candidates": [bad]}, ALLOW)
    assert not rep.structurally_valid
    assert any("missing required field 'license'" in e for e in rep.errors)


def test_bad_parse_path_and_bin_are_errors():
    rep = C.check_circuit_list(
        {"candidates": [_row(variant_group="a", parse_path="vhdl", bin="xl")]}, ALLOW)
    assert any("parse_path" in e for e in rep.errors)
    assert any("bin" in e for e in rep.errors)


def test_exclude_parse_path_must_live_in_rejected():
    rep = C.check_circuit_list(
        {"candidates": [_row(variant_group="a", parse_path="EXCLUDE")]}, ALLOW)
    assert any("EXCLUDE belongs in 'rejected'" in e for e in rep.errors)


def test_duplicate_variant_group_is_error():
    rep = C.check_circuit_list(
        {"candidates": [_row(variant_group="dup"), _row(variant_group="dup")]}, ALLOW)
    assert any("duplicate variant_group" in e for e in rep.errors)


def test_r10_blocks_non_allowlisted_license_default_closed():
    data = {"candidates": [
        _row(variant_group="ok", license="MIT"),
        _row(variant_group="copyleft", license="GPL-3.0"),
        _row(variant_group="unknown", license="unconfirmed"),
    ]}
    rep = C.check_circuit_list(data, ALLOW)
    assert rep.structurally_valid          # R10 block is not a structural error
    assert rep.n_eligible == 1
    blocked = {vg for vg, _ in rep.blocked}
    assert blocked == {"copyleft", "unknown"}   # unconfirmed blocks (default-closed)


def test_l_floor_is_warning_not_structural_error():
    # One l-bin design: well below the ≥25 floor, but the manifest is valid.
    data = {"candidates": [_row(variant_group="big", bin="l")]}
    rep = C.check_circuit_list(data, ALLOW)
    assert rep.structurally_valid
    assert rep.l_distinct == 1
    assert rep.l_floor_ok is False


def test_metrics_distinct_per_bin_and_shares():
    data = {"candidates": [
        _row(variant_group="cpu1", circuit_family="riscv_cpu", parse_path="sv2v", bin="l",
             source="github:openhwgroup/cva6"),
        _row(variant_group="cpu2", circuit_family="riscv_cpu", parse_path="verilog_direct", bin="l",
             source="github:YosysHQ/picorv32"),
        _row(variant_group="ot1", circuit_family="aes", parse_path="sv2v", bin="m",
             source="github:lowRISC/opentitan (hw/ip/aes)"),
        _row(variant_group="dsp1", circuit_family="fft", parse_path="verilog_direct", bin="s",
             source="github:someone/fft"),
    ]}
    rep = C.check_circuit_list(data, ALLOW)
    assert rep.bin_distinct == {"l": 2, "m": 1, "s": 1, "xs": 0}
    assert rep.l_distinct == 2
    assert rep.riscv_share == 0.5                 # 2/4
    assert rep.opentitan_share == 0.25            # 1/4 (source contains 'opentitan')
    assert rep.sv2v_share == 0.5                  # 2/4
    assert rep.top_family[0] == "riscv_cpu"


def test_render_is_markdown_and_mentions_the_four_numbers():
    data = {"candidates": [_row(variant_group="a", bin="l")], "rejected": [{"name": "x"}]}
    out = C.check_circuit_list(data, ALLOW).render()
    assert "four headline numbers" in out
    assert "l-bin distinct" in out
    assert "Rejected-on-intake" in out
