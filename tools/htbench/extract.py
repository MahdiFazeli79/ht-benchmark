"""Reference RTL DFG extractor (spec v1.0 §9, §11).

Parses a Verilog file with Pyverilog's dataflow analyzer and emits the canonical
`dfg_rtl.json` graph: each node carries an AST-derived `handle` (via
`htbench.handles`) and an `x_code` (the 38-class HW2VEC DFG vocabulary), plus
positional `edges`. It deliberately does NOT route through HW2VEC's
`preprocess()` (flatten / remove_underscores), which mangles names and would
destroy intrinsic identity.

This is the round-trip gate's extractor, not the production extractor (spec
§14). The shared identity contract lives in `htbench.handles`; the canonical
DFG *decomposition* is defined here and is part of the contract for
unnamed-expression handles.

Determinism: handles are minted in a fixed canonical pre-order walk of each
binding tree, independent of the final node emission order. `shuffle_seed`
permutes only the emission order (and edge endpoints follow), proving handles
are emission-order-independent (spec §11 `--perturb`).
"""

from __future__ import annotations

import random

from . import handles as H

# 38-class HW2VEC DFG vocabulary, copied verbatim from
# Project/hw2vec/hw2graph.py:51-54 so x_code stays HW2VEC-compatible.
_DFG_VOCAB = [
    "concat", "input", "unand", "unor", "uxor", "signal", "uand", "ulnot",
    "uxnor", "numeric", "partselect", "and", "unot", "branch", "or", "uor",
    "output", "plus", "eq", "minus", "uminus", "xor", "lor", "noteq", "land",
    "greatereq", "greaterthan", "sll", "lessthan", "times", "srl", "pointer",
    "mod", "divide", "sra", "sla", "xnor", "lesseq",
]
_VOCAB_IDX = {t: i for i, t in enumerate(_DFG_VOCAB)}

# Pyverilog DFOperator.operator strings -> DFG vocab token.
_OP2VOCAB = {
    "And": "and", "Or": "or", "Xor": "xor", "Xnor": "xnor", "Land": "land",
    "Lor": "lor", "Unot": "unot", "Ulnot": "ulnot", "Uand": "uand",
    "Uor": "uor", "Unand": "unand", "Unor": "unor", "Uxor": "uxor",
    "Uxnor": "uxnor", "Uminus": "uminus", "Plus": "plus", "Minus": "minus",
    "Times": "times", "Divide": "divide", "Mod": "mod", "Eq": "eq",
    "NotEq": "noteq", "GreaterThan": "greaterthan", "LessThan": "lessthan",
    "GreaterEq": "greatereq", "LessEq": "lesseq", "Sll": "sll", "Srl": "srl",
    "Sra": "sra", "Sla": "sla",
}


def _vocab_token_for(df_node) -> str:
    """Map a Pyverilog dataflow node to its DFG vocab token."""
    cls = type(df_node).__name__
    if cls == "DFTerminal":
        return "signal"
    if cls == "DFIntConst" or cls == "DFFloatConst" or cls == "DFEvalValue":
        return "numeric"
    if cls == "DFBranch":
        return "branch"
    if cls == "DFConcat":
        return "concat"
    if cls == "DFPartselect":
        return "partselect"
    if cls == "DFPointer":
        return "pointer"
    if cls == "DFOperator":
        return _OP2VOCAB.get(getattr(df_node, "operator", ""), "signal")
    return "signal"


def _children(df_node):
    try:
        return [k for k in df_node.children() if k is not None]
    except Exception:
        return []


class _Builder:
    """Walks binding trees, mints handles, accumulates nodes and edges.

    nodes: list of (handle, x_code), built in canonical order.
    handle_to_idx: handle -> canonical node index.
    edges: set of (src_handle, dst_handle), resolved to indices at the end.
    """

    def __init__(self):
        self.handle_to_x: dict[str, int] = {}
        self.order: list[str] = []          # canonical insertion order of handles
        self.edges: set[tuple[str, str]] = set()

    def _add(self, handle: str, token: str) -> str:
        if handle not in self.handle_to_x:
            self.handle_to_x[handle] = _VOCAB_IDX[token]
            self.order.append(handle)
        return handle

    def visit(self, node, dest: str, path: str) -> str:
        """Return the handle of `node`; record it and its fan-in edges.

        `dest` is the binding destination scoped name; `path` is the
        child-index path from the binding root (canonical structural position).
        """
        cls = type(node).__name__
        if cls == "DFTerminal":
            h = H.signal_handle(str(node.name))
            self._add(h, "signal")
            return h
        if cls in ("DFIntConst", "DFFloatConst", "DFEvalValue"):
            val = str(getattr(node, "value", getattr(node, "eval", "?")))
            h = H.const_handle(val, f"{dest}:{path}")
            self._add(h, "numeric")
            return h

        # Composite node (operator / branch / concat / partselect / pointer):
        # visit children first so we can name this node by its fan-in.
        kids = _children(node)
        child_handles = []
        for i, k in enumerate(kids):
            child_path = f"{path}/{i}" if path else str(i)
            child_handles.append(self.visit(k, dest, child_path))

        token = _vocab_token_for(node)
        op = getattr(node, "operator", None) or token
        h = H.expr_handle(op, child_handles, f"{dest}:{path}")
        self._add(h, token)
        for ch in child_handles:
            self.edges.add((ch, h))   # fan-in -> this node
        return h

    def add_binding(self, dest: str, tree) -> None:
        if tree is None:
            return
        self._add(H.signal_handle(dest), "signal")          # the LHS signal node
        root = self.visit(tree, dest, "")                    # RHS expression tree
        self.edges.add((root, H.signal_handle(dest)))        # RHS -> LHS


def extract_rtl(verilog_path: str, top: str | None = None, shuffle_seed: int | None = None) -> dict:
    """Extract the canonical RTL DFG from `verilog_path`.

    Returns a dict conforming to spec/schemas/graph.schema.json with
    graph_kind == "dfg_rtl". `shuffle_seed` permutes node emission order to
    exercise the round-trip gate; handles are unaffected.
    """
    # Lazy import: keep the package importable without Pyverilog for pure
    # schema/validate work.
    from pyverilog.dataflow.dataflow_analyzer import VerilogDataflowAnalyzer

    topname = top or "top"
    analyzer = VerilogDataflowAnalyzer([verilog_path], topname)
    analyzer.generate()
    binddict = analyzer.getBinddict()

    b = _Builder()
    # Deterministic binding order: sorted by destination name.
    for dest in sorted(binddict.keys(), key=str):
        for bind in binddict[dest]:
            b.add_binding(str(dest), getattr(bind, "tree", None))

    emit_order = list(b.order)
    if shuffle_seed is not None:
        rng = random.Random(shuffle_seed)
        rng.shuffle(emit_order)

    idx = {h: i for i, h in enumerate(emit_order)}
    nodes = [{"handle": h, "x_code": b.handle_to_x[h]} for h in emit_order]
    edges = sorted([[idx[s], idx[d]] for (s, d) in b.edges])

    sample_id = topname  # caller overrides when writing into a sample dir
    return {"sample_id": sample_id, "graph_kind": "dfg_rtl", "nodes": nodes, "edges": edges}
