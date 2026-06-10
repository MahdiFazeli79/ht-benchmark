"""Handle <-> positional-index resolution and neighborhood-at-load (spec §8).

Labels store intrinsic handles and `core` only. This module joins handles to the
current graph's positional indices, derives the `neighborhood` set at load from
a `k` parameter (never persisted), and writes the disposable per-release
index-map cache. A handle that does not resolve is a hard error: a label
pointing at a non-existent node is corruption, not a warning.
"""

from __future__ import annotations

import json
from pathlib import Path


def _handle_to_index(graph: dict) -> dict[str, int]:
    return {n["handle"]: i for i, n in enumerate(graph["nodes"])}


def resolve_rtl(graph: dict, labels_rtl: dict) -> dict[int, str]:
    """Map current RTL-DFG indices -> label value for every labeled handle.

    Returns {index: "core"}. Raises KeyError if a labeled handle is absent from
    the graph.
    """
    h2i = _handle_to_index(graph)
    out: dict[int, str] = {}
    for handle, role in labels_rtl.get("labels", {}).items():
        if handle not in h2i:
            raise KeyError(f"labels_rtl handle not in graph: {handle!r}")
        out[h2i[handle]] = role
    return out


def resolve_netlist(graph: dict, labels_netlist: dict) -> dict[int, str]:
    """Same as resolve_rtl for the netlist graph."""
    h2i = _handle_to_index(graph)
    out: dict[int, str] = {}
    for handle, role in labels_netlist.get("labels", {}).items():
        if handle not in h2i:
            raise KeyError(f"labels_netlist handle not in graph: {handle!r}")
        out[h2i[handle]] = role
    return out


def core_handles(labels: dict) -> set[str]:
    """The set of handles labeled `core` (storage only ever contains core)."""
    return {h for h, role in labels.get("labels", {}).items() if role == "core"}


def neighborhood(graph: dict, core_indices: set[int], k: int = 2) -> set[int]:
    """k-hop neighborhood of `core_indices`, derived at load.

    Edges are treated as undirected for neighborhood expansion. `k` is a caller
    parameter, default 2; it is never persisted (spec inversion #4). Returns
    indices in the neighborhood EXCLUDING the core itself.
    """
    adj: dict[int, set[int]] = {i: set() for i in range(len(graph["nodes"]))}
    for s, d in graph["edges"]:
        adj[s].add(d)
        adj[d].add(s)
    frontier = set(core_indices)
    seen = set(core_indices)
    for _ in range(k):
        nxt: set[int] = set()
        for n in frontier:
            nxt |= adj[n]
        nxt -= seen
        seen |= nxt
        frontier = nxt
    return seen - set(core_indices)


def build_index_map(sample_dir: str, version: str = "v1.0") -> Path:
    """Write graphs/index_map.<version>.json: handle -> index for each graph.

    A regenerable cache, never a source of truth. Returns the written path.
    """
    sd = Path(sample_dir)
    graphs_dir = sd / "graphs"
    out = {"version": version, "graphs": {}}
    for name in ("dfg_rtl", "netlist"):
        gp = graphs_dir / f"{name}.json"
        if gp.exists():
            g = json.loads(gp.read_text())
            out["graphs"][name] = _handle_to_index(g)
    dest = graphs_dir / f"index_map.{version}.json"
    dest.write_text(json.dumps(out, indent=2))
    return dest
