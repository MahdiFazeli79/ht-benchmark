"""HW2VEC interop: downstream view + R9 collision guard (spec §9, §15 round 4).

Two responsibilities, both keeping HW2VEC strictly downstream of identity:

1. `to_hw2vec(graph)` converts a canonical graph JSON into the
   `torch_geometric.data.Data` shape HW2VEC consumes. JSON is the store of
   record; this is a derived view produced at load time. Pickle is never the
   canonical store.

2. `hw2vec_name_transform` / `assert_injective` model HW2VEC's lossy name
   mangling (`remove_underscores`, hierarchy flattening) and detect when two
   distinct AST handles would collapse to one HW2VEC name. A collision is a
   rejected sample at build time (R9), never a silently merged label.
"""

from __future__ import annotations

import re


def _cell_type_vocab(graph: dict) -> dict[str, int]:
    """Deterministic cell-type -> id map for a netlist graph (sorted unique).

    A production release replaces this with a versioned library vocab; for the
    enforcement work unit a per-graph sorted vocab is deterministic and enough.
    """
    types = sorted({n["cell_type"] for n in graph["nodes"]})
    return {t: i for i, t in enumerate(types)}


def to_hw2vec(graph: dict):
    """Convert a canonical graph JSON to a torch_geometric.data.Data.

    Produces `x` (int64 node features), `edge_index` (2 x E long), and `label`
    (the list of handles, ordered to match the node array). torch is imported
    lazily so the core package stays importable without it.
    """
    import torch  # lazy
    from torch_geometric.data import Data

    nodes = graph["nodes"]
    kind = graph["graph_kind"]
    if kind == "dfg_rtl":
        x_vals = [n["x_code"] for n in nodes]
    elif kind == "netlist":
        vocab = _cell_type_vocab(graph)
        x_vals = [vocab[n["cell_type"]] for n in nodes]
    else:
        raise ValueError(f"unknown graph_kind: {kind!r}")

    labels = [n["handle"] for n in nodes]
    x = torch.tensor(x_vals, dtype=torch.int64)
    if graph["edges"]:
        edge_index = torch.tensor(graph["edges"], dtype=torch.int64).t().contiguous()
    else:
        edge_index = torch.empty((2, 0), dtype=torch.int64)

    data = Data(x=x, edge_index=edge_index)
    data.label = labels
    return data


def hw2vec_name_transform(handle: str) -> str:
    """Model HW2VEC's lossy name transform on a handle.

    HW2VEC flattens hierarchy and strips ALL underscores (`remove_underscores`).
    We conservatively collapse scope/hierarchy separators and underscores and
    lowercase, so two source signals differing only in underscore/hierarchy
    placement map to the same string. Applied to named-signal handles; expr/
    const handles are returned unchanged (their structure is not name-mangled).
    """
    if handle.startswith(("expr:", "const:")):
        return handle
    return re.sub(r"[_.]", "", handle).lower()


def assert_injective(handles) -> None:
    """Raise if HW2VEC's name transform aliases two distinct handles (R9).

    The error names both colliding handles so the offending sample can be
    rejected at build time.
    """
    seen: dict[str, str] = {}
    for h in handles:
        t = hw2vec_name_transform(h)
        if t in seen and seen[t] != h:
            raise ValueError(
                f"R9 violation: handles {seen[t]!r} and {h!r} collide under "
                f"HW2VEC name transform (both -> {t!r}); sample must be rejected."
            )
        seen[t] = h
