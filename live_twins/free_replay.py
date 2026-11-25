"""Replay the free-start (eq_free) counterexamples of the power_up_only twins on the netlists (24 Nov 2026).

The eq_free miter (lt.equiv_free) gives every flop without an init value a free first-cycle value: write_aiger -zinit
adds one AIGER input per such flop, and the map names it with an `init <input> 0 <net>` line. The value of that input
in frame 0 of the witness is the flop's power-up value. Unnamed init inputs belong to host flops whose state wires are
private after flatten; all of them have a reset, which the wrapper forces in cycle 0, so they are left X here.

Per netlist: both sides are modelled in x_init mode (lt.model, no init values), the named power-up values are set at
time 0 on the matching `<cell>.IQ` registers (and `<cell>.IQ_N` to the complement, where present), and the witness
inputs are applied as in lt.replay. A control runs gold against gold with the gold-side values. Outputs are compared
in every frame; the miter masks frame 0, so a confirming divergence is one at frame >= 1.
Run inside the container: /opt/research-venv/bin/python free_replay.py"""
import importlib.util, json, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
spec = importlib.util.spec_from_file_location("lt", "/foss/designs/outputs/live_twins_20261124/lt.py")
lt = importlib.util.module_from_spec(spec); spec.loader.exec_module(lt)
R = lt.R


def witness(aiw):
    ls = [l.strip() for l in Path(aiw).read_text().splitlines() if l.strip() and not l.startswith("#") and l.strip() != "."]
    return ls[0], ls[1:]                      # latch line, frames


def init_values(mapf, frame0):
    """{side: {net: value}} for every named init input; net is the name below <side>.eqv_dut."""
    out = {"gold": {}, "gate": {}}
    for l in Path(mapf).read_text().splitlines():
        p = l.split()
        if len(p) == 4 and p[0] == "init":
            side, _, net = p[3].partition(".eqv_dut.")
            if side in out and net:
                out[side][net] = (int(p[1]), frame0[int(p[1])])
    return out


def deposits(model_v, nets):
    """Map init nets to model registers: a net `<cell>.IQ` is the register itself; other aliases of the same input
    (`<cell>.Q`, `<cell2>.D`, `trj_t[k]`) are skipped because one alias per input is enough when it is a register."""
    regs = set(re.findall(r"^\s*reg\s+(?:\[[^\]]+\]\s*)?(\\\S+|\w+)\s*;", Path(model_v).read_text(), re.M))
    regs = {r.lstrip("\\") for r in regs}
    dep, covered = [], set()
    for net, (idx, v) in nets.items():
        if net.endswith(".IQ") and net in regs:
            dep.append((net, v)); covered.add(idx)
            if net + "_N" in regs:
                dep.append((net + "_N", "1" if v == "0" else "0"))
        elif net in regs:
            dep.append((net, v)); covered.add(idx)
    return dep, covered


def esc(n):
    return n if re.fullmatch(r"[A-Za-z_]\w*", n) else f"\\{n} "


def sim(h, gold_v, gate_v, vecs, dep_g, dep_t, d, tag, port_src):
    clk = lt.HOSTS[h]["clk"]
    ps = lt.ports(port_src, h)
    ins = [(n, w) for k, n, w in ps if k == "input"]
    outs = [(n, w) for k, n, w in ps if k == "output"]
    decl = "".join(f"  reg [{w-1}:0] {n};\n" for n, w in ins) + "".join(f"  wire [{w-1}:0] g_{n}, t_{n};\n" for n, w in outs)
    conn = lambda p: ", ".join([f".{n}({n})" for n, _ in ins] + [f".{n}({p}_{n})" for n, _ in outs])
    init = "".join(f"    u_g.{esc(n)} = 1'b{v};\n" for n, v in dep_g) + "".join(f"    u_t.{esc(n)} = 1'b{v};\n" for n, v in dep_t)
    steps = ""
    for k, v in enumerate(vecs):
        asg = "".join(f"    {n} = {w}'b{v.get(n, '0' * w).zfill(w)[-w:]};\n" for n, w in ins if n != clk)
        chk = "".join(f"    $display(\"F {k} {n} %b %b\", g_{n}, t_{n});\n" for n, _ in outs)
        steps += f"    #1;\n{asg}    #3;\n{chk}    #1 {clk} = 1;\n    #5 {clk} = 0;\n"
    tb = (f"`timescale 1ns/1ps\nmodule tb;\n{decl}  gold u_g ({conn('g')});\n  gate u_t ({conn('t')});\n"
          f"  initial begin\n    {clk} = 0;\n{init}{steps}    $finish;\n  end\nendmodule\n")
    (d / f"tb_{tag}.v").write_text(tb)
    rc, _, _ = lt.run(["iverilog", "-g2012", "-o", d / f"a_{tag}.out", d / f"tb_{tag}.v", gold_v, gate_v], d / f"build_{tag}.log")
    if rc:
        return {"status": "error", "log": str(d / f"build_{tag}.log")}
    rc, txt, _ = lt.run(["vvp", "-n", d / f"a_{tag}.out"], d / f"sim_{tag}.log", timeout=600)
    Path(d / f"a_{tag}.out").unlink(missing_ok=True)
    if rc or not re.search(r"^F ", txt, re.M):
        return {"status": "error", "log": str(d / f"sim_{tag}.log")}
    divs, xb = [], 0
    for k, n, g, t in re.findall(r"^F (\d+) (\S+) (\S+) (\S+)$", txt, re.M):
        for i, (a, b) in enumerate(zip(g, t)):
            if a in "01" and b in "01" and a != b:
                divs.append({"frame": int(k), "port": n, "bit_from_msb": i, "gold": a, "gate": b})
            elif a not in "01" or b not in "01":
                xb += 1
    later = [x for x in divs if x["frame"] >= 1]
    st = "diverged" if later else ("diverged_frame0_only" if divs else ("x_blocked" if xb else "no_divergence"))
    return {"status": st, "first": (later or divs or [None])[0], "x_bits": xb, "frames": len(vecs)}


def job(r):
    edir = Path(r["cex_file"]).parent
    tag = f"{r['flow']}__{r['id']}"
    d = R / "eq_free_replay" / tag
    d.mkdir(parents=True, exist_ok=True)
    try:
        nls = [l.split()[-1] for l in (edir / "miter.ys").read_text().splitlines() if l.startswith("read_verilog") and "-sv" not in l]
        gold, gate = nls[0], nls[1]
        h = r["host"]
        _, frames = witness(r["cex_file"])
        vecs = lt.cex_to_vectors(r["cex_file"], edir / "map.txt", lt.HOSTS[h]["rst"])
        iv = init_values(edir / "map.txt", frames[0])
        mg, mt = lt.model(gold, h, "gold", "x_init", d), lt.model(gate, h, "gate", "x_init", d)
        if not (mg and mt):
            return {**base(r), "status": "error", "error": "model"}
        dg, cg = deposits(mg, iv["gold"])
        dt, ct = deposits(mt, iv["gate"])
        named = {i for i, _ in iv["gate"].values()} | {i for i, _ in iv["gold"].values()}
        res = {**base(r), "init_inputs_named": len(named), "init_inputs_uncovered": sorted(named - cg - ct),
               "deposits_gate": dt, "deposits_gold": dg}
        res["replay"] = sim(h, mg, mt, vecs, dg, dt, d, "free", gold)
        # control: gold against gold, gold-side values on both instances
        mgg = d / "gold_as_gate_x_init.v"
        mgg.write_text(re.sub(r"^module\s+gold\b", "module gate", Path(mg).read_text(), count=1, flags=re.M))
        res["control"] = sim(h, mg, mgg, vecs, dg, dg, d, "ctl", gold)
        res["no_init"] = sim(h, mg, mt, vecs, [], [], d, "noinit", gold)   # same witness, flops left X
        for f in (mg, mt, mgg):
            Path(f).unlink(missing_ok=True)
        return res
    except Exception as ex:
        return {**base(r), "status": "error", "error": f"{type(ex).__name__}: {ex}"[:300]}


def base(r):
    return {"id": r["id"], "host": r["host"], "flow": r["flow"], "eq_free_frame": r.get("frame")}


if __name__ == "__main__":
    rows = [json.loads(l) for fn in ("free.jsonl", "free_big.jsonl") for l in open(R / fn)]
    rows = [r for r in rows if r["kind"] == "twin" and r["status"] == "different"]
    if len(sys.argv) > 1:
        rows = [r for r in rows if f"{r['flow']}__{r['id']}" in sys.argv[1:]]
    print("jobs:", len(rows), flush=True)
    out = R / "free_replay.jsonl"
    out.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(job, rows):
            with open(out, "a") as fh:
                fh.write(json.dumps(res) + "\n")
    print("done", flush=True)
