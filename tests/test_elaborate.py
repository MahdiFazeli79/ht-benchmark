"""Yosys-elaboration RTL front-end (elaborate.py).

The fixture `fixtures/elab_src/packed_cfg.sv` reproduces the wall the sv2v canary
hit (docs/phase1_sv2v_canary.md): SystemVerilog plus a packed-parameter
generate-if. Raw Pyverilog cannot get past it; the elaborate stage
(sv2v -> yosys -chparam -> extract) can, and it keeps the intrinsic handles the
labels reference.
"""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("pyverilog", reason="extractor needs Pyverilog")
if shutil.which("yosys") is None or shutil.which("sv2v") is None:
    pytest.skip("yosys/sv2v not on PATH", allow_module_level=True)

from htbench import elaborate, extract, handles  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "elab_src" / "packed_cfg.sv"

AND_H = "expr:and(top.a,top.b)@top.combined:"
OR_H = "expr:or(top.a,top.b)@top.combined:"


def test_raw_pyverilog_hits_the_wall():
    # Documents WHY the stage exists: the raw extractor cannot ingest the SV /
    # parameterized generate. If this ever stops raising, the stage is moot.
    with pytest.raises(Exception):
        extract.extract_rtl(str(FIX), top="top")


def test_elaborate_then_extract_preserves_user_handles():
    g, res = elaborate.elaborate_and_extract(FIX, "top", chparams={"CFG": 1})
    hs = {n["handle"] for n in g["nodes"]}
    assert {"top.a", "top.b", "top.combined", "top.result", "top.rstn"} <= hs
    assert res.sv2v_used is True
    assert res.chparams == {"CFG": 1}


def test_no_gensyms_and_r9_injective():
    g, _ = elaborate.elaborate_and_extract(FIX, "top", chparams={"CFG": 1})
    hs = [n["handle"] for n in g["nodes"]]
    assert not [h for h in hs if handles.is_forbidden_key(h)]   # no $ gensym / int-only
    assert len(hs) == len(set(hs))                              # R9 injective


def test_chparam_selects_the_generate_branch():
    g1, _ = elaborate.elaborate_and_extract(FIX, "top", chparams={"CFG": 1})
    g0, _ = elaborate.elaborate_and_extract(FIX, "top", chparams={"CFG": 0})
    h1 = {n["handle"] for n in g1["nodes"]}
    h0 = {n["handle"] for n in g0["nodes"]}
    assert AND_H in h1 and OR_H not in h1   # CFG[0]=1 -> a & b
    assert OR_H in h0 and AND_H not in h0   # CFG[0]=0 -> a | b


def test_elaboration_failure_is_loud():
    # No silent fallback to raw Pyverilog: a bad top must raise, not degrade.
    with pytest.raises(elaborate.ElaborationError):
        elaborate.elaborate(FIX, "no_such_top", chparams={"CFG": 1})


def test_provenance_records_reproducibility_fields():
    _, res = elaborate.elaborate_and_extract(FIX, "top", chparams={"CFG": 1})
    prov = res.provenance()
    assert prov["stage"] == "yosys_elaborate"
    assert prov["chparams"] == {"CFG": 1}
    assert prov["sv2v_used"] is True
    assert "yosys" in prov["tool_versions"]
    assert "hierarchy -top top" in prov["yosys_script"]
    assert "chparam CFG 1" in prov["yosys_script"]


# --- synthetic-net policy (string-level units; the fixture is too small to
# force Yosys to mint a `_N_` net, so the predicate is tested directly) ---

def test_is_synthetic_net():
    assert elaborate.is_synthetic_net("top._0_")
    assert elaborate.is_synthetic_net("_3_")
    assert elaborate.is_synthetic_net("top.sub._12_")
    assert not elaborate.is_synthetic_net("top.combined")
    assert not elaborate.is_synthetic_net("top._myreg")   # not the _N_ shape


def test_synthetic_nets_are_not_forbidden_keys():
    # v1 policy: synthetic nets are reported, never rejected — they pass the
    # forbidden-key check (they are not $-gensyms or bare integers).
    assert not handles.is_forbidden_key("top._0_")


def test_partition_synthetic():
    intrinsic, synth = elaborate.partition_synthetic(
        ["top.a", "top._0_", "top.result", "_1_"])
    assert intrinsic == ["top.a", "top.result"]
    assert synth == ["top._0_", "_1_"]


# --- config-selection policy (Phase-1 decision 2026-06-10) ---

def test_single_config_is_not_leakage_linked():
    plans = elaborate.plan_variants("picorv32", [{"ENABLE_MUL": 1}])
    assert len(plans) == 1
    assert plans[0].leakage_linked is False
    assert plans[0].variant_group == "picorv32"
    assert plans[0].chparams == {"ENABLE_MUL": 1}


def test_multi_config_shares_variant_group_and_flags_leakage():
    cfgs = [{"ENABLE_MUL": 0}, {"ENABLE_MUL": 1}]
    plans = elaborate.plan_variants("picorv32", cfgs)
    assert len(plans) == 2
    assert all(p.leakage_linked for p in plans)        # split-atomicity (spec §8)
    assert len({p.variant_group for p in plans}) == 1  # one group -> one split side
    assert len({p.sample_id for p in plans}) == 2      # distinct samples


def test_plan_variants_rejects_duplicate_configs():
    with pytest.raises(ValueError):
        elaborate.plan_variants("picorv32", [{"X": 1}, {"X": 1}])


def test_plan_variants_requires_at_least_one_config():
    with pytest.raises(ValueError):
        elaborate.plan_variants("picorv32", [])
