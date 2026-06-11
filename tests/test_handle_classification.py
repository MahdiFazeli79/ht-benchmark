"""Handle classification + R11 fail-loud (spec round 9).

classify_handle is the canary's lesson generalized: a handle is intrinsic only if
POSITIVELY source-derived; anything neither positively-intrinsic nor known-
synthetic is `unclassified` and fails loud (R11) rather than defaulting to
intrinsic. Pure tests (no toolchain) + one validator integration test.
"""
import json
import shutil
from pathlib import Path

from htbench import handles as H

FIX = Path(__file__).resolve().parent / "fixtures"


# --- classify_handle ---

def test_structural_handles():
    assert H.classify_handle("expr:and(top.a,top.b)@top.y:") == "structural"
    assert H.classify_handle("const:8'h00@top.r:0") == "structural"


def test_intrinsic_signal_handles():
    assert H.classify_handle("top.a") == "intrinsic"
    assert H.classify_handle("top.uart_rx.cnt") == "intrinsic"
    assert H.classify_handle("top.bus[3]") == "intrinsic"
    assert H.classify_handle("top.slice[7:0]") == "intrinsic"
    # yosys-escaped flattened hierarchical name (real signal)
    assert H.classify_handle("mul_top.\\i_mul.clk_i") == "intrinsic"


def test_synthetic_handles():
    assert H.classify_handle("top._0_") == "synthetic"                     # yosys
    assert H.classify_handle("mul_top.\\i_mul._sv2v_0") == "synthetic"     # sv2v
    assert H.classify_handle(
        "mul_top.\\i_mul.ariane_pkg_sext32to64$func$mul_flat.v:111$81.operand"
    ) == "synthetic"                                                       # inlined fn


def test_unclassified_fails_loud_not_intrinsic():
    # The whole point: an unseen artifact shape must NOT default to intrinsic.
    assert H.classify_handle("top.123abc") == "unclassified"   # segment starts with digit
    assert H.classify_handle("top.weird name") == "unclassified"  # space
    assert H.classify_handle("top.a#b") == "unclassified"      # stray symbol


def test_synthetic_checked_before_intrinsic():
    # `_sv2v_0` also matches the intrinsic-segment shape; denylist must win.
    assert H.is_synthetic("top._sv2v_3")
    assert H.classify_handle("top._sv2v_3") == "synthetic"


# --- R11 in the validator ---

def test_validator_flags_unclassified_handle(tmp_path):
    from htbench import validate

    src = FIX / "e_clean"
    dst = tmp_path / "e_clean"
    shutil.copytree(src, dst)
    g = json.loads((dst / "graphs" / "dfg_rtl.json").read_text())
    g["nodes"].append({"handle": "top.123bogus", "x_code": 0})   # unclassified shape
    (dst / "graphs" / "dfg_rtl.json").write_text(json.dumps(g))

    errors, _ = validate.validate_sample(dst, rtl_only=True)
    assert any("R11 unclassified handle" in e for e in errors), errors
