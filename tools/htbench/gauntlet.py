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
    # NAME-HEURISTIC reset detection (v1, disclosed in spec §15 round 10): a port
    # named rst/reset_n/... is assumed to initialize state, which is what lets
    # reachability_established=True for input-driven proofs. A name-matched input
    # that doesn't actually reset could let that through; v1 discloses rather than
    # behaviorally verifying post-reset state (the grade-and-disclose posture).
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


def _compile_run_extract(rtl: str, tb: str, *, iverilog="iverilog", vvp="vvp"):
    """Compile dut+tb, run, extract the $display output trace. The SINGLE place
    trace handling lives (drops the vvp/`$finish` banner, whose tmp-path differs
    between runs and would otherwise read as a spurious divergence) — FE and
    activation-proof both go through here, so their notion of an output trace can
    never drift apart."""
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
    trace = [ln.strip() for ln in out.splitlines() if re.fullmatch(r"[0-9 ]+", ln.strip())]
    return trace, ""


def simulate(rtl: str, top: str, ports: dict, vectors: list[dict], **kw):
    """Shared sim harness: drive `vectors` into `top`, return (trace, "") or
    (None, error). Reused by FE and activation-proof."""
    return _compile_run_extract(rtl, _gen_tb(top, ports, vectors), **kw)


def _mismatches(trace_a, trace_b) -> list[int]:
    """The SINGLE divergence notion shared by FE and activation-proof. If these
    two tests compared traces differently, their mutual-protection guarantee
    (FE backstops the parser; a mis-parse can only false-reject) would silently
    break — so both call this."""
    return [i for i, (a, b) in enumerate(zip(trace_a, trace_b)) if a != b]


def functional_equivalence(clean: str, infected: str, top: str, *,
                           n_vectors=64, seed=1234) -> GauntletVerdict:
    """Dormancy: infected ≡ clean on random non-trigger inputs (bounded by the
    vector budget — "equal on N random vectors", not proven-equivalent). The SAME
    vector set drives both; any mismatch means the Trojan is not stealthy."""
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
    mism = _mismatches(tc, ti)
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


# --------------------------------------------------------------------------- #
# Activation-proof — the trigger-half of FE (built against the round-9/10 design)
# --------------------------------------------------------------------------- #

_VAL = r"([0-9]+'[bBhHdD][0-9a-fA-F_xXzZ]+|0[xX][0-9a-fA-F_]+|\d+)"
_ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:==|=)\s*" + _VAL)


def _parse_value(tok: str) -> int:
    tok = tok.strip().replace("_", "")
    m = re.fullmatch(r"(\d+)'([bBhHdD])([0-9a-fA-FxXzZ]+)", tok)
    if m:
        base = {"b": 2, "h": 16, "d": 10}[m.group(2).lower()]
        return int(re.sub(r"[xXzZ]", "0", m.group(3)), base)   # x/z → 0 for stimulus
    if tok.lower().startswith("0x"):
        return int(tok, 16)
    return int(tok, 10)


def parse_witness(trigger_text: str, ports: dict) -> dict:
    """Lenient parse of the witness trigger into a stimulus: each ``sig=val`` is
    an APPLIED INPUT (a top-level input port) or a FORCED internal signal. Fail
    LOUD on an un-parseable witness (reject the sample, don't guess) — a mis-parse
    can only false-reject because FE backstops it and clean is the reference. The
    parser only reproduces the trigger; it never interprets it semantically."""
    input_names = {n for n, _ in ports["inputs"]}
    inputs, forces = {}, {}
    for name, val in _ASSIGN_RE.findall(trigger_text):
        (inputs if name in input_names else forces)[name] = _parse_value(val)
    if not inputs and not forces:
        raise ValueError(f"un-parseable witness trigger: {trigger_text!r}")
    return {"inputs": inputs, "forces": forces,
            "method": "state_injection" if forces else "input_driven"}


def _gen_witness_tb(top: str, ports: dict, inputs: dict, forces: dict, observe_cycles: int = 1) -> str:
    """`observe_cycles == 1` (default) samples outputs once, one edge after the force —
    the DECISION testbench, unchanged. `observe_cycles > 1` (clocked designs only)
    samples every cycle for that many cycles, for the divergence-window DIAGNOSTIC
    (when does a sequential payload first surface after the trigger?)."""
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
    for n, v in inputs.items():
        body.append(f"    {n} = {v};")
    body.append(f"    @(posedge {clk}); #1;" if clk else "    #2;")
    for n, v in forces.items():
        body.append(f"    force dut.{n} = {v};")     # state injection
    if clk and observe_cycles > 1:                   # divergence-window diagnostic: sample each cycle
        body.append(f"    repeat({observe_cycles}) begin @(posedge {clk}); #1; "
                    f'$display("{disp_fmt}", {disp_args}); end')
    else:                                            # decision TB: one sample, one edge after the force
        body.append(f"    @(posedge {clk}); #1;" if clk else "    #2;")
        body.append(f'    $display("{disp_fmt}", {disp_args});')
    body.append("    $finish;")
    clk_drv = f"  always #5 {clk} = ~{clk};\n" if clk else ""
    return ("module tb;\n" + "\n".join(decls) + "\n"
            + f"  {top} dut(" + ", ".join(conns) + ");\n" + clk_drv
            + "  initial begin\n" + "\n".join(body) + "\n  end\nendmodule\n")


def activation_proof(clean: str, infected: str, top: str, witness: dict) -> GauntletVerdict:
    """The trigger-half of FE: the witnessed trigger produces a divergence the
    clean circuit does not, under identical stimulus. v1 proves TRIGGER-attributable
    divergence (something diverged at the trigger), NOT payload-confirmed (that the
    claimed effect fired) — graded as `divergence_attribution=trigger_only`.
    input-driven (real inputs, reachable) vs state-injection (forced state,
    reachability not established) is graded too. Reuses the SHARED trace handling
    and comparison so it cannot drift from FE."""
    ports = parse_ports(clean, top)
    try:
        st = parse_witness(witness.get("trigger", ""), ports)
    except ValueError as e:
        return GauntletVerdict(False, f"activation-proof: {e}")
    # reachability holds only if the trigger state was reached FROM RESET: a
    # combinational design has no state, and a reset-driven design starts known.
    # A stateful design with no detectable reset starts at X — input-driven is NOT
    # enough to claim reachability there (it would overclaim). So:
    combinational = ports["clk"] is None
    reset_driven = ports["rst"] is not None
    reachable = st["method"] == "input_driven" and (combinational or reset_driven)
    grade = {"activation_proof_method": st["method"],
             "reachability_established": reachable,
             "divergence_attribution": "trigger_only"}
    tb = _gen_witness_tb(top, ports, st["inputs"], st["forces"])
    tc, ec = _compile_run_extract(clean, tb)
    if tc is None:
        # Clean produced no trace. Carry the STAGE so the failure self-classifies:
        # a compile (bind) failure ⇒ the witness names a signal absent from clean
        # (structural / pre-sim — the Trojan-internal-witness case); a sim failure ⇒
        # clean ran but crashed (a different bucket). Either way "silent on clean"
        # can't be established → reject (honest, lost yield not bad data).
        stage = "references a signal absent from clean (structural)" if ec.startswith("compile:") \
            else "clean sim error (runtime)"
        return GauntletVerdict(False, f"witness not applicable to clean — {stage}: {ec}", grade)
    ti, ei = _compile_run_extract(infected, tb)
    if ti is None:
        return GauntletVerdict(False, f"infected sim error: {ei}", grade)
    if not _mismatches(tc, ti):
        # Post-sim: clean and infected matched at the single sample point. If the
        # payload is sequential it may surface only later — measure WHEN with the
        # divergence-window diagnostic. The cycle is the gauntlet-TB fix parameter
        # (sample window = first divergence + margin); None ⇒ no divergence in cap.
        dc = _divergence_cycle(clean, infected, top, ports, st["inputs"], st["forces"])
        grade["divergence_cycle_diagnostic"] = dc
        tail = (f"; diagnostic: diverges at cycle {dc} within window (TB-timing fix parameter)"
                if dc is not None else "; diagnostic: no divergence within window cap")
        return GauntletVerdict(False,
                               "witness produced no divergence (infected == clean under trigger)" + tail,
                               grade)
    return GauntletVerdict(True, "", grade)


def _divergence_cycle(clean, infected, top, ports, inputs, forces, *, cycles=16):
    """Diagnostic ONLY — never changes a verdict. Re-runs the witness stimulus but
    observes outputs every cycle for `cycles` after the trigger, and returns the first
    cycle where infected diverges from clean (or None: no divergence within the cap).
    That cycle IS the sample-window fix parameter for a sequential payload that the
    single-sample decision TB observes too early. Combinational designs (no clk) have
    no window, so this collapses to the single-sample answer."""
    tb = _gen_witness_tb(top, ports, inputs, forces, observe_cycles=cycles)
    tc, _ = _compile_run_extract(clean, tb)
    ti, _ = _compile_run_extract(infected, tb)
    if tc is None or ti is None:
        return None
    mism = _mismatches(tc, ti)
    return mism[0] if mism else None


def run_full(clean: str, infected: str, top: str, witness: dict) -> GauntletVerdict:
    """The complete gauntlet: three mechanical tests, then activation-proof. The
    passing verdict's `detail` carries the round-10 grading for the manifest."""
    v = run_mechanical(clean, infected, top)
    if not v.ok:
        return v
    ap = activation_proof(clean, infected, top, witness)
    if not ap.ok:
        return GauntletVerdict(False, f"activation_proof: {ap.reason}", ap.detail)
    return GauntletVerdict(True, "all gauntlet tests passed", ap.detail)
