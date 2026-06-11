"""Phase-2 verification gauntlet (plan §2.3) — the three mechanical tests.

The decision-light tests; activation-proof is built separately against a settled
design. Each returns a `GauntletVerdict`; the engine's `verify` callback composes
them. NO API calls.

  - `compile_ok`            — iverilog compiles the infected module.
  - `functional_equivalence`— DORMANCY: infected ≡ clean on random (non-trigger)
    inputs, by sampled simulation through the shared `simulate` harness. A
    mismatch on a random input means the Trojan is not stealthy → reject. This is
    the dormancy half of the story; activation-proof is the trigger half and
    REUSES `simulate` (drive the witness stimulus, assert divergence).
  - `synth_survival`        — the Trojan is not optimized away: the synthesized
    infected netlist has strictly more cells than the clean one (a v1 proxy for
    "the inserted logic survives Yosys"; precise manifest-anchored survival is the
    netlist-side v1.1 work).

Port parsing and testbench generation are pilot-scale: ANSI-ish headers,
single-clock `clk`-style + active-low/high reset by name convention. Documented
heuristics, not a general elaborator — the pilot reveals what needs hardening.
"""

from __future__ import annotations

import random as _random
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_CLOCK_NAMES = {"clk", "clock", "clk_i", "i_clk", "clki"}
_RESET_NAMES = {"rst", "reset", "rst_n", "resetn", "rst_ni", "arst_n", "nrst", "reset_n"}

_PORT_RE = re.compile(
    r"\b(input|output)\b\s*(?:wire|reg|logic)?\s*(?:signed\s*)?"
    r"(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?([A-Za-z_]\w*)"
)


@dataclass
class GauntletVerdict:
    ok: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)


def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr


def parse_ports(rtl: str, top: str) -> dict:
    """Lightweight port extraction for the sim harness (pilot-scale heuristic).
    Returns inputs/outputs as (name, width), plus detected clk/rst."""
    seen: dict[str, tuple[str, int]] = {}
    for d, msb, lsb, name in _PORT_RE.findall(rtl):
        if name in seen:
            continue
        width = abs(int(msb) - int(lsb)) + 1 if msb != "" else 1
        seen[name] = (d, width)
    inputs = [(n, w) for n, (d, w) in seen.items() if d == "input"]
    outputs = [(n, w) for n, (d, w) in seen.items() if d == "output"]
    clk = next((n for n, _ in inputs if n.lower() in _CLOCK_NAMES), None)
    rst = next((n for n, _ in inputs if n.lower() in _RESET_NAMES), None)
    rst_active_low = bool(rst and rst.lower().endswith(("_n", "n")) and rst.lower() not in ("reset",))
    data_inputs = [(n, w) for n, w in inputs if n not in (clk, rst)]
    return {"inputs": inputs, "outputs": outputs, "data_inputs": data_inputs,
            "clk": clk, "rst": rst, "rst_active_low": rst_active_low}


def compile_ok(rtl: str, top: str, *, iverilog="iverilog") -> GauntletVerdict:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "dut.v"
        f.write_text(rtl)
        rc, _out, err = _run([iverilog, "-g2012", "-o", str(Path(d) / "a.out"), str(f)])
    return GauntletVerdict(rc == 0, "" if rc == 0 else f"compile failed: {err.strip()[:300]}")


def _gen_tb(top: str, ports: dict, vectors: list[dict]) -> str:
    decls, conns = [], []
    for n, w in ports["inputs"]:
        decls.append(f"  reg [{w-1}:0] {n};")
        conns.append(f".{n}({n})")
    for n, w in ports["outputs"]:
        decls.append(f"  wire [{w-1}:0] {n};")
        conns.append(f".{n}({n})")
    out_names = [n for n, _ in ports["outputs"]]
    disp_fmt = " ".join("%0d" for _ in out_names)
    disp_args = ", ".join(out_names) if out_names else '""'
    clk, rst = ports["clk"], ports["rst"]
    body = []
    if clk:
        body.append(f"    {clk} = 0;")
    if rst:
        av = 0 if ports["rst_active_low"] else 1
        dv = 1 if ports["rst_active_low"] else 0
        body.append(f"    {rst} = {av};")
    for n, _ in ports["data_inputs"]:
        body.append(f"    {n} = 0;")
    if rst:
        body.append("    #13;")
        body.append(f"    {rst} = {dv};")
    for vec in vectors:
        for n, _ in ports["data_inputs"]:
            body.append(f"    {n} = {vec.get(n, 0)};")
        body.append(f"    @(posedge {clk}); #1;" if clk else "    #2;")
        body.append(f'    $display("{disp_fmt}", {disp_args});')
    body.append("    $finish;")
    clk_drv = f"  always #5 {clk} = ~{clk};\n" if clk else ""
    return ("module tb;\n" + "\n".join(decls) + "\n"
            + f"  {top} dut(" + ", ".join(conns) + ");\n" + clk_drv
            + "  initial begin\n" + "\n".join(body) + "\n  end\nendmodule\n")


def simulate(rtl: str, top: str, ports: dict, vectors: list[dict], *,
             iverilog="iverilog", vvp="vvp"):
    """Shared sim harness: drive `vectors` into `top`, return the output trace
    (one line per step). Returns (trace, "") or (None, error). Reused by FE and
    (later) activation-proof — same harness, different stimulus + assertion."""
    tb = _gen_tb(top, ports, vectors)
    with tempfile.TemporaryDirectory() as d:
        Path(d, "dut.v").write_text(rtl)
        Path(d, "tb.v").write_text(tb)
        out_bin = str(Path(d, "sim.out"))
        rc, _o, err = _run([iverilog, "-g2012", "-o", out_bin,
                            str(Path(d, "dut.v")), str(Path(d, "tb.v"))])
        if rc != 0:
            return None, f"compile: {err.strip()[:200]}"
        rc, out, err = _run([vvp, out_bin])
        if rc != 0:
            return None, f"sim: {err.strip()[:200]}"
    # Keep only the $display output lines (space-separated decimals); this drops
    # the vvp/$finish banner ("...tb.v:N: $finish called at ...") whose tmp-path
    # differs between runs and would otherwise read as a spurious divergence.
    trace = [ln.strip() for ln in out.splitlines() if re.fullmatch(r"[0-9 ]+", ln.strip())]
    return trace, ""


def functional_equivalence(clean: str, infected: str, top: str, *,
                           n_vectors=64, seed=1234) -> GauntletVerdict:
    """Dormancy: infected ≡ clean on random non-trigger inputs. The SAME vector
    set drives both; any output mismatch means the Trojan is not stealthy."""
    ports = parse_ports(clean, top)
    rng = _random.Random(seed)
    vectors = [{n: rng.getrandbits(w) for n, w in ports["data_inputs"]}
               for _ in range(n_vectors)]
    tc, ec = simulate(clean, top, ports, vectors)
    if tc is None:
        return GauntletVerdict(False, f"clean sim error: {ec}")
    ti, ei = simulate(infected, top, ports, vectors)
    if ti is None:
        return GauntletVerdict(False, f"infected sim error: {ei}")
    mism = [i for i, (a, b) in enumerate(zip(tc, ti)) if a != b]
    if mism:
        return GauntletVerdict(False,
                               f"not dormant: diverges on {len(mism)}/{n_vectors} random vectors",
                               {"mismatch_steps": mism[:5]})
    return GauntletVerdict(True, "", {"vectors": n_vectors})


def _yosys_cells(rtl: str, top: str, *, yosys="yosys"):
    """Synthesized cell count, read from write_json (format-stable across Yosys
    versions, unlike the human `stat` table)."""
    import json
    with tempfile.TemporaryDirectory() as d:
        Path(d, "x.v").write_text(rtl)
        jf = Path(d, "net.json")
        script = (f"read_verilog -sv {Path(d, 'x.v')}; hierarchy -top {top}; "
                  f"synth -top {top} -flatten; write_json {jf}")
        rc, _out, _err = _run([yosys, "-q", "-p", script])
        if rc != 0 or not jf.exists():
            return None
        data = json.loads(jf.read_text())
    return sum(len(m.get("cells", {})) for m in data.get("modules", {}).values())


def synth_survival(clean: str, infected: str, top: str, *, yosys="yosys") -> GauntletVerdict:
    """The Trojan survives synthesis: infected must synthesize to strictly more
    cells than clean (v1 proxy — a Trojan Yosys folds away is dead code)."""
    cc = _yosys_cells(clean, top, yosys=yosys)
    ic = _yosys_cells(infected, top, yosys=yosys)
    if cc is None or ic is None:
        return GauntletVerdict(False, "synth error (clean or infected did not synthesize)")
    if ic > cc:
        return GauntletVerdict(True, "", {"clean_cells": cc, "infected_cells": ic})
    return GauntletVerdict(False,
                           f"Trojan optimized away (infected {ic} <= clean {cc} cells)",
                           {"clean_cells": cc, "infected_cells": ic})


def run_mechanical(clean: str, infected: str, top: str) -> GauntletVerdict:
    """Run the three mechanical tests cheap→expensive, short-circuiting on the
    first failure. Activation-proof (the trigger half of the dormancy story) is
    appended here once built against its settled design."""
    stages = (("compile", lambda: compile_ok(infected, top)),
              ("functional_equivalence", lambda: functional_equivalence(clean, infected, top)),
              ("synth_survival", lambda: synth_survival(clean, infected, top)))
    for name, run in stages:
        v = run()
        if not v.ok:
            return GauntletVerdict(False, f"{name}: {v.reason}", v.detail)
    return GauntletVerdict(True, "mechanical tests passed")
