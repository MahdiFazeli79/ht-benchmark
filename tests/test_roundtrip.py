"""Round-trip gate tests (spec §11). Requires the Pyverilog front-end."""
from pathlib import Path

import pytest

pytest.importorskip("pyverilog", reason="reference extractor needs Pyverilog")

from htbench import roundtrip  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.parametrize("sid", ["a_counter_modfunc", "e_clean"])
def test_roundtrip_perturb_holds(sid):
    ok, msg = roundtrip.roundtrip_sample(FX / sid, perturb=True)
    assert ok, msg


def test_roundtrip_all_fixtures():
    results = roundtrip.roundtrip_path(FX, perturb=True)
    bad = {sid: msg for sid, (ok, msg) in results.items() if not ok}
    assert not bad, bad


def test_commutative_operand_shuffle_invariant():
    """Handles of nested commutative expressions are invariant to operand
    emission order (the axis the expr-handle context path depends on)."""
    import tempfile
    from htbench import extract

    src = "module top(input a, input b, output y);\n  assign y = (a & b) ^ (a | b);\nendmodule\n"
    d = tempfile.mkdtemp()
    f = Path(d) / "infected.v"
    f.write_text(src)

    def hset(**kw):
        return {n["handle"] for n in extract.extract_rtl(str(f), top="top", **kw)["nodes"]}

    base = hset()
    for seed in range(1, 6):
        assert hset(child_shuffle_seed=seed, shuffle_seed=seed * 7 + 1) == base


def test_noncommutative_operands_do_not_alias():
    """a-b and b-a must mint distinct handles (no blind sort)."""
    import tempfile
    from htbench import extract

    def minus_handle(expr):
        src = f"module top(input [3:0] a, input [3:0] b, output [3:0] y);\n  assign y = {expr};\nendmodule\n"
        d = tempfile.mkdtemp()
        f = Path(d) / "infected.v"
        f.write_text(src)
        hs = [n["handle"] for n in extract.extract_rtl(str(f), top="top")["nodes"]]
        return next(h for h in hs if h.startswith("expr:minus"))

    assert minus_handle("a - b") != minus_handle("b - a")
