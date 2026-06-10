"""HW2VEC converter + R9 collision-detector tests (spec §9, §15 round 4)."""
import json
from pathlib import Path

import pytest

from htbench import hw2vec_compat as HW

FX = Path(__file__).resolve().parent / "fixtures"


def _graph(sid):
    return json.loads((FX / sid / "graphs" / "dfg_rtl.json").read_text())


def test_assert_injective_raises_on_collision():
    with pytest.raises(ValueError, match="R9"):
        HW.assert_injective(["top.a_b", "top.ab"])


def test_assert_injective_passes_clean():
    HW.assert_injective(["top.x", "top.y", "expr:and(top.x,top.y)@top.z:"])


def test_to_hw2vec_roundtrips_shape():
    pytest.importorskip("torch")
    pytest.importorskip("torch_geometric")
    g = _graph("a_counter_modfunc")

    # Guard against off-by-one alignment bugs that hide on uniform/fully
    # connected graphs: require >1 distinct node type and at least one leaf
    # (a node that is never a source of an edge).
    assert len({n["x_code"] for n in g["nodes"]}) >= 2, "need heterogeneous node types"
    srcs = {s for s, _ in g["edges"]}
    assert any(i not in srcs for i in range(len(g["nodes"]))), "need at least one leaf node"

    data = HW.to_hw2vec(g)
    # node count matches
    assert data.x.shape[0] == len(g["nodes"])
    # edge_index shape matches the edge list
    assert tuple(data.edge_index.shape) == (2, len(g["edges"]))
    # label ordering aligns element-wise with the node array
    assert list(data.label) == [n["handle"] for n in g["nodes"]]
    # x values are the x_codes in node order
    assert data.x.tolist() == [n["x_code"] for n in g["nodes"]]
