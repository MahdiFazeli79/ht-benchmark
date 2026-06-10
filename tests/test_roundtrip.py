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
