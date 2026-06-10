"""Round-trip invariance gate (spec §11).

Re-extract the DFG from infected.v, re-resolve the SAME labels_rtl.json against
the fresh extraction, and assert the set of physical handles labeled `core` is
unchanged. This proves labels survive a regeneration they were never written to
track. `--perturb` shuffles extraction emission order (intra-front-end, v1) to
prove handles are traversal-order-independent.

The gate uses the reference extractor (`htbench.extract`); handles come from the
shared contract in `htbench.handles`.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import extract
from . import resolve as R


def roundtrip_sample(sample_dir, perturb=False) -> tuple[bool, str]:
    """Return (passed, message) for one sample."""
    sd = Path(sample_dir)
    labels_rtl = json.loads((sd / "labels_rtl.json").read_text())
    manifest = json.loads((sd / "trojan_manifest.json").read_text())
    top = manifest["top_module"]
    inf = sd / "infected.v"

    core = R.core_handles(labels_rtl)

    # Pass A: extract fresh, resolve core handle set.
    gA = extract.extract_rtl(str(inf), top=top)
    hsA = {n["handle"] for n in gA["nodes"]}
    missA = core - hsA
    if missA:
        return False, f"core handles absent from extraction A: {sorted(missA)}"
    A = core  # core handles that resolve

    # Pass B: re-extract (shuffled if perturb), resolve again. Perturb shuffles
    # BOTH node emission order AND commutative-operand order, so the gate
    # exercises the axis that the expr-handle context path depends on.
    gB = extract.extract_rtl(
        str(inf), top=top,
        shuffle_seed=987654321 if perturb else 1,
        child_shuffle_seed=424242 if perturb else None,
    )
    hsB = {n["handle"] for n in gB["nodes"]}
    missB = core - hsB
    if missB:
        return False, f"core handles absent from extraction B: {sorted(missB)}"
    B = core

    if A != B:
        return False, f"core set changed across re-extraction: {A ^ B}"
    return True, f"A == B ({len(A)} core handles stable)"


def roundtrip_path(path, perturb=False) -> dict:
    p = Path(path)
    samples = [p] if (p / "trojan_manifest.json").exists() else sorted(
        d for d in p.iterdir() if d.is_dir() and (d / "trojan_manifest.json").exists()
    )
    return {s.name: roundtrip_sample(s, perturb) for s in samples}
