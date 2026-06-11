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


DRIVE_BUDGET = 4096          # admissibility constant: a trigger must be input-reachable
DRIVE_OBSERVE = 16           # within this many cycles; payload observed over this window
_SETTLE_CAP = 64             # extra hold cycles a witness may request (FSM arm), capped


def _clean_signals(rtl: str, ports: dict) -> set:
    """Identifier namespace DECLARED in clean (ports + reg/wire/logic). A drive
    predicate on a signal NOT here is Trojan-internal — there is nothing in clean to
    drive to, so it is structural."""
    names = {n for n, _ in ports["inputs"]} | {n for n, _ in ports["outputs"]}
    for m in re.finditer(r"\b(?:reg|wire|logic)\b\s*(?:signed\s*)?(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)", rtl):
        names.add(m.group(1))
    return names


def _extract_settle(text: str, cap: int = _SETTLE_CAP) -> int:
    """Conservative: only an explicit 'N consecutive/more/additional … edge/cycle' is a
    settle (FSM arm after the trigger). 'apply en=1 for 254 cycles' is a DRIVE length,
    not a settle, so it must NOT match. Default 0, capped."""
    m = re.search(r"(\d+)\s+(?:more |additional |consecutive )(?:\w+\s+){0,3}(?:edge|cycle)",
                  text, re.I)
    return min(int(m.group(1)), cap) if m else 0


def parse_drive_witness(trigger_text: str, ports: dict, clean_signals: set) -> dict:
    """Drive-to-state parse (pure; no force). Splits the witness's sig=val pairs into
    held inputs (the stimulus to hold), a host-observable reach predicate (the state to
    DRIVE to), and Trojan-internal references (signals in neither inputs nor clean).
    clk/rst assignments are dropped — the TB owns reset and clocking. Fail-loud on a
    witness with no parseable assignment."""
    data_inputs = {n for n, _ in ports["data_inputs"]}     # held stimulus (excludes clk/rst)
    all_inputs = {n for n, _ in ports["inputs"]}
    pairs = _ASSIGN_RE.findall(trigger_text)
    if not pairs:
        raise ValueError(f"un-parseable witness trigger: {trigger_text!r}")
    held, reach_candidates, internal = {}, [], []
    for name, val in pairs:
        v = _parse_value(val)
        if name in data_inputs:
            held[name] = v
        elif name in all_inputs:
            continue                                       # clk/rst — TB handles reset+clock
        elif name in clean_signals:
            reach_candidates.append((name, v))             # host-observable predicate to drive to
        else:
            internal.append(name)                          # Trojan-internal
    return {"held_inputs": held,
            "reach": reach_candidates[0] if reach_candidates else None,
            "settle": _extract_settle(trigger_text),
            "internal_refs": internal}


def _tb_io(ports):
    decls, conns = [], []
    for n, w in ports["inputs"]:
        decls.append(f"  reg [{w-1}:0] {n};"); conns.append(f".{n}({n})")
    for n, w in ports["outputs"]:
        decls.append(f"  wire [{w-1}:0] {n};"); conns.append(f".{n}({n})")
    return decls, conns, [n for n, _ in ports["outputs"]]


def _gen_apply_tb(top, ports, held_inputs):
    """Combinational degenerate case: apply the input vector, observe once. No clock,
    no force — the v1 input-driven path, minus the force."""
    decls, conns, out_names = _tb_io(ports)
    fmt = " ".join("%0d" for _ in out_names)
    args = ", ".join(out_names) if out_names else '""'
    body = [f"    {n} = 0;" for n, _ in ports["data_inputs"]]
    body += [f"    {n} = {v};" for n, v in held_inputs.items()]
    body += ["    #2;", f'    $display("{fmt}", {args});', "    $finish;"]
    return ("module tb;\n" + "\n".join(decls) + "\n"
            + f"  {top} dut(" + ", ".join(conns) + ");\n"
            + "  initial begin\n" + "\n".join(body) + "\n  end\nendmodule\n")


def _gen_drive_tb(top, ports, held_inputs, reach_signal, budget):
    """Sequential drive-to-state: reset, hold the inputs, clock up to `budget` cycles,
    and each cycle display the reach signal (col 0, read via dut.<sig> — observed, NOT
    forced) then the outputs. Python finds the cycle the reach predicate is met and
    compares the OUTPUT columns from there."""
    decls, conns, out_names = _tb_io(ports)
    fmt = " ".join("%0d" for _ in range(1 + len(out_names)))   # reach + outputs
    args = ", ".join([f"dut.{reach_signal}"] + out_names)
    clk, rst = ports["clk"], ports["rst"]
    body = [f"    {clk} = 0;"]
    if rst:
        av = 0 if ports["rst_active_low"] else 1
        dv = 1 if ports["rst_active_low"] else 0
        body.append(f"    {rst} = {av};")
    body += [f"    {n} = 0;" for n, _ in ports["data_inputs"]]
    if rst:
        body += ["    #13;", f"    {rst} = {dv};"]
    body += [f"    {n} = {v};" for n, v in held_inputs.items()]
    body.append(f'    repeat({budget}) begin @(posedge {clk}); #1; $display("{fmt}", {args}); end')
    body.append("    $finish;")
    return ("module tb;\n" + "\n".join(decls) + "\n"
            + f"  {top} dut(" + ", ".join(conns) + ");\n"
            + f"  always #5 {clk} = ~{clk};\n"
            + "  initial begin\n" + "\n".join(body) + "\n  end\nendmodule\n")


def _split_trace(trace):
    return [[int(x) for x in ln.split()] for ln in trace if ln.split()]


def activation_proof(clean: str, infected: str, top: str, witness: dict,
                     *, budget: int = DRIVE_BUDGET, observe: int = DRIVE_OBSERVE) -> GauntletVerdict:
    """Drive-to-state trigger proof (pure — no force). For a sequential trigger, DRIVE
    the inputs to a host-observable reach predicate within `budget` cycles, then observe
    whether infected diverges from clean over `observe` cycles. No force, so forcing the
    payload's own register can't mask it. Three reject classes self-classify:
    `structural` (no host-observable trigger to drive to), `not-reachable-in-budget`
    (the trigger is genuinely deep), `masking/unobservable` (reached but never surfaces).
    An accept grades input_driven + reachability_established (the stronger tier)."""
    ports = parse_ports(clean, top)
    clean_sigs = _clean_signals(clean, ports)
    try:
        w = parse_drive_witness(witness.get("trigger", ""), ports, clean_sigs)
    except ValueError as e:
        return GauntletVerdict(False, f"activation-proof: {e}")
    grade = {"divergence_attribution": "trigger_only"}

    if ports["clk"] is None:                               # combinational: apply + observe once
        tb = _gen_apply_tb(top, ports, w["held_inputs"])
        tc, _ = _compile_run_extract(clean, tb)
        ti, _ = _compile_run_extract(infected, tb)
        if tc is None or ti is None:
            return GauntletVerdict(False, "activation-proof: combinational sim error", grade)
        grade.update(activation_proof_method="input_driven", reachability_established=True)
        if _mismatches(tc, ti):
            return GauntletVerdict(True, "", grade)
        return GauntletVerdict(False, "masking/unobservable: trigger applied, no divergence at outputs", grade)

    # sequential: pure drive-to-state to a host-observable predicate
    if w["reach"] is None:
        refs = w["internal_refs"] or ["(none)"]
        return GauntletVerdict(False, f"structural: witness names {refs} absent from clean and not an "
                               "input — no host-observable trigger to drive to", grade)
    reach_sig, reach_val = w["reach"]
    tb = _gen_drive_tb(top, ports, w["held_inputs"], reach_sig, budget)
    tc, ec = _compile_run_extract(clean, tb)
    if tc is None:
        return GauntletVerdict(False, f"activation-proof: clean drive sim error: {ec}", grade)
    rows_c = _split_trace(tc)
    T = next((i for i, r in enumerate(rows_c) if r and r[0] == reach_val), None)
    if T is None:
        return GauntletVerdict(False, f"not-reachable-in-budget: {reach_sig}=={reach_val} not reached "
                               f"within {budget} cycles", grade)
    ti, ei = _compile_run_extract(infected, tb)
    if ti is None:
        return GauntletVerdict(False, f"activation-proof: infected drive sim error: {ei}", grade)
    rows_i = _split_trace(ti)
    grade.update(activation_proof_method="input_driven", reachability_established=True,
                 reached_cycle=T, settle_cycles=w["settle"])
    start = T + w["settle"]
    for i in range(start, min(start + observe, len(rows_c), len(rows_i))):
        if rows_c[i][1:] != rows_i[i][1:]:                 # output columns (skip col 0 = reach)
            return GauntletVerdict(True, "", grade)
    return GauntletVerdict(False, f"masking/unobservable: reached {reach_sig}=={reach_val} at cycle {T}, "
                           f"no divergence in {observe} cycles", grade)


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
