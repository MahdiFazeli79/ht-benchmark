"""Independent ground-truth check for the extractor (closes the loop).

Every other fixture is extractor output validated by the extractor's own
contract, so a wrong-but-self-consistent handle would pass everywhere. Here the
expected handles and edges are written BY HAND, by reading the Verilog and
applying the spec §6 handle format, with no reference to extractor output. If
handles.py or extract.py mints a subtly wrong handle, this test catches it.
"""
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pyverilog", reason="extractor needs Pyverilog")

from htbench import extract  # noqa: E402

# --- the design, read by a human ---
#   module top(input a, input b, output y);
#     assign y = a & b;
#   endmodule
#
# DFG, by hand:
#   named signals: top.a, top.b, top.y
#   one AND node: root of y's binding (path ""), context "top.y:";
#   AND is commutative so its fan-in is sorted -> (top.a,top.b)
#   => expr:and(top.a,top.b)@top.y:
#   edges (data flow): a -> AND, b -> AND, AND -> y
SRC = "module top(input a, input b, output y);\n  assign y = a & b;\nendmodule\n"

AND = "expr:and(top.a,top.b)@top.y:"
EXPECTED_HANDLES = {"top.a", "top.b", "top.y", AND}
EXPECTED_EDGES = {("top.a", AND), ("top.b", AND), (AND, "top.y")}


def _extract():
    d = tempfile.mkdtemp()
    f = Path(d) / "infected.v"
    f.write_text(SRC)
    return extract.extract_rtl(str(f), top="top")


def test_handles_match_hand_authored_ground_truth():
    g = _extract()
    assert {n["handle"] for n in g["nodes"]} == EXPECTED_HANDLES


def test_edges_match_hand_authored_ground_truth():
    g = _extract()
    hs = [n["handle"] for n in g["nodes"]]
    edges = {(hs[s], hs[d]) for s, d in g["edges"]}
    assert edges == EXPECTED_EDGES
