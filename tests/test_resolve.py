"""Resolver + neighborhood tests (spec §8)."""
import json
from pathlib import Path

import pytest

from htbench import resolve as R

FX = Path(__file__).resolve().parent / "fixtures"


def _load(sid):
    d = FX / sid
    g = json.loads((d / "graphs" / "dfg_rtl.json").read_text())
    lbl = json.loads((d / "labels_rtl.json").read_text())
    return g, lbl


def test_resolve_rtl_maps_core_handles():
    g, lbl = _load("a_counter_modfunc")
    out = R.resolve_rtl(g, lbl)
    assert out                                  # at least one core node
    assert all(v == "core" for v in out.values())
    # the resolved index points at the right handle
    h2i = {n["handle"]: i for i, n in enumerate(g["nodes"])}
    assert h2i["top.tcount"] in out


def test_unresolved_handle_is_hard_error():
    g, _ = _load("a_counter_modfunc")
    bad = {"labels": {"top.does_not_exist": "core"}}
    with pytest.raises(KeyError):
        R.resolve_rtl(g, bad)


def test_neighborhood_expands_and_excludes_core():
    g, lbl = _load("a_counter_modfunc")
    core = set(R.resolve_rtl(g, lbl).keys())
    n1 = R.neighborhood(g, core, k=1)
    n2 = R.neighborhood(g, core, k=2)
    assert core.isdisjoint(n1)                  # neighborhood excludes core
    assert n1.issubset(n2)                      # k=2 contains k=1
    assert len(n1) >= 1                         # tcount has neighbors


def test_neighborhood_not_persisted_in_labels():
    # Stored labels contain only "core" (spec inversion #4).
    _, lbl = _load("a_counter_modfunc")
    assert set(lbl["labels"].values()) == {"core"}
