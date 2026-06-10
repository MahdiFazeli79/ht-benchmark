"""R9 collision-rate instrument (r9_rate.py, task #27).

The pure measurement is tested on synthetic handle sets (no Pyverilog needed);
the full elaborate->extract->measure driver is smoke-tested on the elaborate
fixture when the toolchain is present.
"""
import shutil
from pathlib import Path

import pytest

from htbench import r9_rate as R


def _graph(handles):
    return {"graph_kind": "dfg_rtl",
            "nodes": [{"handle": h, "x_code": 0} for h in handles],
            "edges": []}


# --- pure measurement ---

def test_collisions_in_detects_underscore_aliasing():
    # The adversarial case: top.a_b and top.ab both mangle to "topab".
    cols = R.collisions_in(["top.a_b", "top.ab", "top.c"])
    assert len(cols) == 1
    transformed, hs = cols[0]
    assert hs == ["top.a_b", "top.ab"]


def test_no_collision_on_distinct_names():
    assert R.collisions_in(["top.alpha", "top.beta", "top.gamma"]) == []


def test_expr_and_const_handles_do_not_collide():
    # expr/const handles are not name-mangled; structurally distinct -> no alias.
    hs = ["expr:and(top.a,top.b)@top.y:", "expr:or(top.a,top.b)@top.y:",
          "const:8'h00@top.r:0"]
    assert R.collisions_in(hs) == []


def test_measure_graph_counts_named_vs_total():
    g = _graph(["top.a", "top.b", "expr:and(top.a,top.b)@top.y:", "const:1@top.y:0"])
    d = R.measure_graph("d0", g)
    assert d.n_handles == 4
    assert d.n_named == 2
    assert not d.has_collision


def test_design_collision_rate_aggregates():
    graphs = {
        "clean1": _graph(["top.a", "top.b"]),
        "clean2": _graph(["top.x", "top.y"]),
        "dirty": _graph(["top.a_b", "top.ab"]),
    }
    rep = R.measure_graphs(graphs)
    assert rep.n_measured == 3
    assert rep.n_with_collision == 1
    assert abs(rep.design_collision_rate - 1 / 3) < 1e-9


def test_render_flags_finding_above_threshold():
    # 1 of 1 designs collides -> 100% >= threshold -> FINDING.
    rep = R.measure_graphs({"d": _graph(["top.a_b", "top.ab"])})
    out = rep.render()
    assert "FINDING" in out
    assert "design collision rate: 100%" in out


def test_failed_design_is_recorded_not_fatal():
    rep = R.R9RateReport([R.DesignR9("ok", 2, 2, []),
                          R.DesignR9("bad", 0, 0, [], error="ParseError: boom")])
    assert rep.n_measured == 1
    assert rep.n_failed == 1
    assert rep.design_collision_rate == 0.0
    assert "bad" in rep.render()


# --- full-chain driver smoke test ---

@pytest.mark.skipif(
    shutil.which("yosys") is None or shutil.which("sv2v") is None,
    reason="yosys/sv2v not on PATH",
)
def test_measure_design_specs_on_fixture():
    pytest.importorskip("pyverilog", reason="extractor needs Pyverilog")
    fix = Path(__file__).parent / "fixtures" / "elab_src" / "packed_cfg.sv"
    specs = [{"design_id": "packed_cfg", "sources": [str(fix)], "top": "top",
              "chparams": {"CFG": 1}}]
    rep = R.measure_design_specs(specs)
    assert rep.n_measured == 1
    assert rep.n_failed == 0
    # The fixture has clean intrinsic names -> no R9 collision.
    assert rep.design_collision_rate == 0.0


def test_measure_design_specs_records_failure():
    specs = [{"design_id": "nope", "sources": ["/does/not/exist.v"], "top": "top"}]
    rep = R.measure_design_specs(specs)
    assert rep.n_failed == 1
    assert rep.measured == []
