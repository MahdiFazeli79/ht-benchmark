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


# --- handle classification (spec §10 R11, round 9) -------------------------- #
#
# The CVA6 canary (docs/phase1_sv2v_r9_canary.md) found tool-artifact classes the
# original denylist had never seen (`_sv2v_N`, `$func$`). The lesson: across 500
# designs from heterogeneous toolchains, MORE unseen artifact shapes will appear,
# and a denylist that is merely *current* silently lets a synthetic node
# masquerade as an intrinsic handle — the exact quiet corruption the identity
# scheme refuses. So classification is INVERTED toward an allowlist: a handle is
# intrinsic only if POSITIVELY identifiable as source-derived; anything that is
# neither positively-intrinsic nor known-synthetic is `unclassified` and FAILS
# LOUD (R11) instead of defaulting to intrinsic.

# Known tool-generated (synthetic) shapes — non-source-intrinsic, never a
# manifest signal, deterministic within pinned tools. Tolerated (classified
# synthetic, excluded from intrinsic, never a label key), not rejected.
_SYNTHETIC_PATTERNS = (
    re.compile(r"(?:^|\.)_\d+_$"),        # Yosys proc/flatten nets: top._0_
    re.compile(r"(?:^|\.)_sv2v_\d+$"),    # sv2v lowering temporaries
    re.compile(r"\$"),                    # sv2v/yosys inlined-fn & gensym symbols
)

# Positive intrinsic shape: a dotted hierarchical path of Verilog identifiers,
# each optionally yosys-escaped (leading backslash), with an optional trailing
# bit/part-select. This is what a declared source signal looks like after any
# conformant front end; it traces back to the RTL.
_INTRINSIC_SEGMENT = r"\\?[A-Za-z_][A-Za-z0-9_]*"
_INTRINSIC_SIGNAL = re.compile(
    rf"^{_INTRINSIC_SEGMENT}(?:\.{_INTRINSIC_SEGMENT})*(?:\[\d+(?::\d+)?\])?$"
)


def is_synthetic(handle: str) -> bool:
    """True if `handle` is a known tool-generated artifact (denylist)."""
    base = handle.split("[", 1)[0]
    return any(p.search(base) for p in _SYNTHETIC_PATTERNS)


def classify_handle(handle: str) -> str:
    """Classify a handle as one of:

    - ``"structural"`` — an extractor-minted ``expr:``/``const:`` node (intrinsic
      by construction; never a manifest signal);
    - ``"synthetic"`` — a known tool artifact (`_N_`, `_sv2v_N`, `$…`);
    - ``"intrinsic"`` — positively source-derived (a declared-signal path);
    - ``"unclassified"`` — none of the above. R11 fails loud on this rather than
      letting an unseen artifact class masquerade as intrinsic.

    Order matters: structural first, then the synthetic denylist (so `_sv2v_0`,
    which also matches the intrinsic-segment shape, is caught as synthetic), then
    the positive intrinsic test, else unclassified.
    """
    if handle.startswith(("expr:", "const:")):
        return "structural"
    if is_synthetic(handle):
        return "synthetic"
    if _INTRINSIC_SIGNAL.match(handle):
        return "intrinsic"
    return "unclassified"


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

    Form: ``expr:<op>(<fan-in,handles>)@<context>`` (spec §6). Fan-in handles
    are joined in the order the CALLER provides; the caller is responsible for
    canonicalizing operand order (sorted for commutative operators so identity
    is order-independent; source order for non-commutative operators where
    operand order is semantic, e.g. ``a-b`` differs from ``b-a``). This module
    must NOT re-sort: sorting non-commutative operands would alias distinct
    nodes onto one handle.

    `context` is the AST-structural position ``<dest>:<child-index-path>`` that
    disambiguates structurally identical expressions and keeps handles injective
    within a graph (R9 / §9 uniqueness). Pyverilog dataflow nodes do not carry
    source line numbers, so structural position replaces the source line shown
    illustratively in the spec.
    """
    inner = ",".join(fanin_handles)
    return f"expr:{op.lower()}({inner})@{context}"
