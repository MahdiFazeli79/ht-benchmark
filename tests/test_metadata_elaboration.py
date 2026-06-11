"""Round-8 elaboration provenance block in metadata.json.

Schema-only (jsonschema) so it runs in CI's light job. Verifies the block is
optional (backward-compatible), validates when well-formed, and is rejected when
malformed — and that elaborate.metadata_block() emits a conforming shape.
"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from htbench import elaborate

SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "schemas" / "metadata.schema.json").read_text()))

BASE = {
    "sample_id": "x", "n_nodes_rtl": 10, "n_edges_rtl": 9, "n_cells_netlist": None,
    "area_um2": None, "logic_depth": None, "trigger_activation_prob": None,
    "difficulty_bin": "m", "split": "train",
}


def _errs(md):
    return [e.message for e in SCHEMA.iter_errors(md)]


def test_metadata_without_elaboration_still_valid():
    # Backward compatibility: existing samples have no elaboration block.
    assert _errs(BASE) == []


def test_good_elaboration_block_validates():
    md = {**BASE, "elaboration": {
        "front_end": "yosys_elaborate", "sv2v_used": True,
        "sv2v_version": "sv2v 0.0.13", "yosys_version": "Yosys 0.65",
        "top_module": "cva6", "chparams": {"CVA6Cfg": "33"}, "synthetic_nets": 2,
    }}
    assert _errs(md) == []


def test_elaboration_null_is_allowed():
    assert _errs({**BASE, "elaboration": None}) == []


def test_bad_front_end_value_rejected():
    md = {**BASE, "elaboration": {"front_end": "magic"}}
    assert _errs(md)


def test_missing_front_end_rejected():
    md = {**BASE, "elaboration": {"sv2v_used": True}}
    assert _errs(md)


def test_unknown_elaboration_field_rejected():
    md = {**BASE, "elaboration": {"front_end": "yosys_elaborate", "bogus": 1}}
    assert _errs(md)


def test_metadata_block_helper_conforms_to_schema():
    res = elaborate.ElaborationResult(
        verilog_path="/tmp/e.v", top="top", chparams={"CFG": 1}, sv2v_used=True,
        yosys_script="...", tool_versions={"yosys": "Yosys 0.65", "sv2v": "sv2v 0.0.13"},
        work_dir="/tmp",
    )
    graph = {"nodes": [{"handle": "top.a"}, {"handle": "top._0_"}], "edges": []}
    block = elaborate.metadata_block(res, graph)
    assert block["synthetic_nets"] == 1            # top._0_ counted
    assert block["chparams"] == {"CFG": "1"}
    # The block must validate inside a full metadata document.
    assert _errs({**BASE, "elaboration": block}) == []
