"""Validator + schema-strictness tests (spec §10, §12)."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from htbench import validate

FX = Path(__file__).resolve().parent / "fixtures"
SPEC = Path(__file__).resolve().parents[1] / "spec"


def _errs(sid):
    errors, _ = validate.validate_sample(FX / sid, rtl_only=True)
    return errors


@pytest.mark.parametrize("sid", ["a_counter_modfunc", "b_extkill_dos",
                                 "c_alwayson_leak", "e_clean"])
def test_valid_fixtures_pass(sid):
    assert _errs(sid) == []


def test_d_rejected_for_R3():
    errs = _errs("d_invalid_alwayson_modfunc")
    assert any("R3" in e for e in errs), errs


def test_collision_rejected_for_R9():
    errs = _errs("z_collision")
    assert any("R9" in e for e in errs), errs


def test_copyleft_license_rejected_for_R10(tmp_path):
    # A GPL circuit must be rejected at intake (incompatible with CC-BY benchmark).
    import shutil
    src = FX / "a_counter_modfunc"
    dst = tmp_path / "gpl"
    shutil.copytree(src, dst)
    m = json.loads((dst / "trojan_manifest.json").read_text())
    m["license"] = "GPL-3.0-only"
    (dst / "trojan_manifest.json").write_text(json.dumps(m))
    errors, _ = validate.validate_sample(dst, rtl_only=True)
    assert any("R10" in e for e in errors), errors


def test_handle_uniqueness_guard(tmp_path):
    # Duplicate a handle in a copy of a valid fixture -> validator must fail.
    import shutil
    src = FX / "a_counter_modfunc"
    dst = tmp_path / "dup"
    shutil.copytree(src, dst)
    g = json.loads((dst / "graphs" / "dfg_rtl.json").read_text())
    g["nodes"].append(dict(g["nodes"][0]))          # duplicate first node
    (dst / "graphs" / "dfg_rtl.json").write_text(json.dumps(g))
    errors, _ = validate.validate_sample(dst, rtl_only=True)
    assert any("duplicate handles" in e for e in errors), errors


# --- graph-schema negative fixtures f, g (spec §12) ---
_GS = Draft202012Validator(json.loads((SPEC / "schemas" / "graph.schema.json").read_text()))


def test_graph_negative_f_dfg_with_cell_type():
    bad = {"sample_id": "x", "graph_kind": "dfg_rtl",
           "nodes": [{"handle": "top.a", "x_code": 11, "cell_type": "and2"}], "edges": []}
    assert not _GS.is_valid(bad)


def test_graph_negative_g_netlist_with_x_code():
    bad = {"sample_id": "x", "graph_kind": "netlist",
           "nodes": [{"handle": "top.u1", "x_code": 3}], "edges": []}
    assert not _GS.is_valid(bad)
