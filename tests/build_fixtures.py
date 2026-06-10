"""Generate the test fixtures under tests/fixtures/ (spec §12).

Each sample carries a REAL extracted dfg_rtl.json (so resolve/roundtrip run on
genuine data), an authored manifest/labels, and line ranges computed from the
actual clean/infected diff so R6 holds by construction. Fixtures are RTL-only;
full-mode netlist fixtures arrive with the Phase-0.3 spike.

Run:  PYTHONPATH=tools python tests/build_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

from htbench import extract                       # noqa: E402
from htbench import handles as H                   # noqa: E402
from htbench.validate import _added_line_ranges    # noqa: E402

FX = HERE / "fixtures"

CLEAN_BASE = """module top(input clk, input rstn, input [3:0] a, output reg [3:0] y);
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a;
endmodule
"""

# (clean, infected, inserted_signals, taxonomy, class, payload-note)
SAMPLES = {
    "a_counter_modfunc": dict(
        clean=CLEAN_BASE,
        infected="""module top(input clk, input rstn, input [3:0] a, output reg [3:0] y);
  reg [3:0] tcount;
  always @(posedge clk or negedge rstn)
    if(!rstn) tcount <= 0; else tcount <= tcount + 1;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= (tcount == 4'hf) ? ~a : a;
endmodule
""",
        inserted=["top.tcount"],
        cls="infected",
        taxonomy=dict(activation="triggered", trigger_source="internal",
                      trigger_mechanism="sequential_counter", payload="modify_functionality"),
    ),
    "b_extkill_dos": dict(
        clean="""module top(input clk, input rstn, input en, input [3:0] a, output reg [3:0] y);
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= en ? a : y;
endmodule
""",
        infected="""module top(input clk, input rstn, input en, input kill, input [3:0] a, output reg [3:0] y);
  wire force0 = kill & en;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= force0 ? 4'h0 : (en ? a : y);
endmodule
""",
        inserted=["top.force0"],
        cls="infected",
        taxonomy=dict(activation="triggered", trigger_source="external",
                      trigger_mechanism="combinational", payload="denial_of_service"),
    ),
    "c_alwayson_leak": dict(
        clean=CLEAN_BASE,
        infected="""module top(input clk, input rstn, input [3:0] a, output reg [3:0] y, output wire leak);
  assign leak = a[0];
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a;
endmodule
""",
        inserted=["top.leak"],
        cls="infected",
        taxonomy=dict(activation="always_on", trigger_source=None,
                      trigger_mechanism=None, payload="leak_information"),
    ),
    # (d) invalid: always_on + modify_functionality -> R3 reject. Mirrors (c).
    "d_invalid_alwayson_modfunc": dict(
        clean=CLEAN_BASE,
        infected="""module top(input clk, input rstn, input [3:0] a, output reg [3:0] y, output wire leak);
  assign leak = a[0];
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a;
endmodule
""",
        inserted=["top.leak"],
        cls="infected",
        taxonomy=dict(activation="always_on", trigger_source=None,
                      trigger_mechanism=None, payload="modify_functionality"),
    ),
    "e_clean": dict(
        clean=CLEAN_BASE,
        infected=CLEAN_BASE,            # byte-identical for a clean sample
        inserted=[],
        cls="clean",
        taxonomy=None,
    ),
    # collision: top.a_b and top.ab collapse under HW2VEC underscore removal -> R9.
    "z_collision": dict(
        clean="""module top(input clk, input rstn, input [3:0] x, output reg [3:0] y);
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= x;
endmodule
""",
        infected="""module top(input clk, input rstn, input [3:0] x, output reg [3:0] y);
  wire [3:0] a_b = x + 1;
  wire [3:0] ab = x + 2;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a_b ^ ab;
endmodule
""",
        inserted=["top.a_b", "top.ab"],
        cls="infected",
        taxonomy=dict(activation="triggered", trigger_source="internal",
                      trigger_mechanism="combinational", payload="modify_functionality"),
    ),
}


def build_one(sid: str, spec: dict) -> None:
    d = FX / sid
    (d / "graphs").mkdir(parents=True, exist_ok=True)
    (d / "clean.v").write_text(spec["clean"])
    (d / "infected.v").write_text(spec["infected"])

    g = extract.extract_rtl(str(d / "infected.v"), top="top")
    g["sample_id"] = sid
    (d / "graphs" / "dfg_rtl.json").write_text(json.dumps(g, indent=2))

    node_handles = {n["handle"] for n in g["nodes"]}
    core = {H.signal_handle(s): "core" for s in spec["inserted"] if H.signal_handle(s) in node_handles}

    labels = {"sample_id": sid, "handle_scheme": "rtl_signal_or_expr_signature",
              "labels": core if spec["cls"] == "infected" else {}}
    (d / "labels_rtl.json").write_text(json.dumps(labels, indent=2))

    manifest = {
        "sample_id": sid, "class": spec["cls"], "source": "fixture",
        "source_kind": "academic_benchmark", "circuit_family": "fixture",
        "top_module": "top",
        "verification": {"compile_pass": True, "synth_pass": True,
                         "functional_equiv_pass": True, "synth_survival_pass": True,
                         "activation_proof_pass": True, "sim_tool": "iverilog",
                         "synth_tool": "yosys"},
    }
    if spec["cls"] == "infected":
        added = _added_line_ranges(spec["clean"], spec["infected"])
        tax = spec["taxonomy"]
        manifest["taxonomy"] = {
            "taxonomy_version": "1.0", "taxonomy_ref": "Karri 2010; Trust-Hub 2017",
            "insertion_phase": "design", "insertion_level": "rtl", **tax,
        }
        manifest["inserted_rtl"] = {"signals": spec["inserted"], "line_ranges": added,
                                    "module_instances": []}
        manifest["generator"] = {"model": "none", "prompt_hash": "0" * 64, "attempt_count": 1}
    (d / "trojan_manifest.json").write_text(json.dumps(manifest, indent=2))

    meta = {"sample_id": sid, "n_nodes_rtl": len(g["nodes"]), "n_edges_rtl": len(g["edges"]),
            "n_cells_netlist": None, "area_um2": None, "logic_depth": None,
            "trigger_activation_prob": None,
            "difficulty_bin": "xs", "split": "train"}
    (d / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"built {sid}: {len(g['nodes'])} nodes, core={sorted(core)}")


def main():
    for sid, spec in SAMPLES.items():
        build_one(sid, spec)


if __name__ == "__main__":
    main()
