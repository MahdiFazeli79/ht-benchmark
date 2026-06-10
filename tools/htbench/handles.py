"""Canonical handle format — the identity contract (spec v1.0 §6, R9).

A *handle* is a circuit-intrinsic identifier for a graph node, derived from the
Verilog AST (Pyverilog scoped names) UPSTREAM of any tool preprocessing. It is
never a positional index and never a tool-generated symbol (Yosys gensym,
HW2VEC mangled name). Both the reference extractor shipped here and any future
production extractor are clients of these primitives, so identity is defined in
exactly one place.

This module is pure: no Pyverilog, no torch, no I/O. The canonical DFG
*decomposition* (which expression sub-nodes exist) is defined by the reference
extractor (`htbench.extract`); for unnamed-expression handles that decomposition
is part of the contract a conformant extractor must reproduce. Named-signal and
constant handles are decomposition-independent.
"""

from __future__ import annotations

import re

# Forbidden handle/key shapes the validator rejects (spec §10 step 4):
#   - integer-only keys            -> positional index leaking in
#   - Yosys gensyms                -> tool-generated symbol
_FORBIDDEN_PATTERNS = (
    re.compile(r"^\d+$"),     # net bit-IDs / integer-only
    re.compile(r"^\$"),       # Yosys gensym, e.g. $abc$...
)


def is_forbidden_key(key: str) -> bool:
    """True if `key` is a positional index or tool-generated symbol that must
    never appear as a handle."""
    return any(p.search(key) for p in _FORBIDDEN_PATTERNS)


def signal_handle(scoped_name: str, bit: int | None = None) -> str:
    """Handle for a named signal node.

    `scoped_name` is the Pyverilog fully-qualified name, e.g. ``top.uart_rx.cnt``.
    `bit` optionally selects a single bit, yielding ``top.uart_rx.cnt[3]``.
    The scoped name is used verbatim: any conformant Verilog front-end
    reconstructs the same hierarchy, which is what makes identity
    tool-independent.
    """
    h = scoped_name.strip()
    if not h:
        raise ValueError("empty scoped_name")
    if bit is not None:
        h = f"{h}[{int(bit)}]"
    return h


def const_handle(value: str, context: str) -> str:
    """Handle for a constant leaf node.

    Constants carry no name, so identity is (value, structural context).
    `context` is the AST-structural position ``<dest>:<child-index-path>``
    (e.g. ``top.y:0/1``), which is unique within a graph, stable across
    re-extraction, and invariant under node emission-order shuffle.
    """
    return f"const:{value}@{context}"


def expr_handle(op: str, fanin_handles: list[str], context: str) -> str:
    """Handle for an unnamed intermediate-expression node.

    Form: ``expr:<op>(<sorted,fan-in,handles>)@<context>`` (spec §6). Fan-in
    handles are sorted so the handle is independent of operand emission order;
    `context` is the AST-structural position ``<dest>:<child-index-path>`` that
    disambiguates structurally identical expressions and keeps handles injective
    within a graph (R9 / §9 uniqueness). Pyverilog dataflow nodes do not carry
    source line numbers, so structural position replaces the source line shown
    illustratively in the spec.
    """
    inner = ",".join(sorted(fanin_handles))
    return f"expr:{op.lower()}({inner})@{context}"
