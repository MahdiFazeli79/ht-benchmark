"""Live twins on the host-population hosts (24 Nov 2026).

For each host and each of the 19 Study 2 sub-variants, trojan_gen.GEN_LIVE builds a twin whose trigger the inputs
or reset can reach and whose payload reaches one output bit. Each twin goes through LL, Y_sat and Y_seq with the
same scripts as the campaign, and is compared with that campaign's golden netlist of the same flow:

  * eq_rst miter (as trojan_lib.Campaign.equiv_abc with clk/rst) plus `write_cex -a`; the AIGER counterexample is
    converted to one primary-input vector per cycle (reset forced in cycle 0, as in the miter);
  * replay of that witness on both netlists in two modes (spec section 3.4): `reset` (every flop without an init
    value starts at 0) and `x_init` (no init values at all). The simulated model is each netlist flattened with the
    Liberty cell functions (read_liberty -ignore_miss_func), written back as Verilog, run in Icarus (four-state);
  * remnant probe against the golden netlist.
Container paths.
"""
import json, random, re, shutil, subprocess, sys, time, importlib.util
from pathlib import Path

sys.path.insert(0, "/foss/designs/scripts")
import wblib as wb
import trojan_lib as tl

def _load(name):
    spec = importlib.util.spec_from_file_location(name, f"/foss/designs/scripts/{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
tg = _load("trojan_gen")

HP = Path("/foss/designs/outputs/host_population_20261122_153549")
R = Path("/foss/designs/outputs/live_twins_20261124")
SEED = 20261124
FLOWS = ("LL", "Y_sat", "Y_seq")
LIB = wb.LIB_COMMON
HOSTS = json.loads((HP / "hosts.json").read_text())
C = tl.Campaign(R)          # rtl/, cfg/, ll/, eq/, probe/, logs/
LLC = {r["id"]: r for r in map(json.loads, open(HP / "res_LL.jsonl"))}


def run(cmd, log, timeout=1800):
    t0 = time.time()
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
        txt, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        txt, rc = "TIMEOUT", 124
    Path(log).write_text(txt)
    return rc, txt, round(time.time() - t0, 1)


# ------------------------------------------------------------------ RTL
def bitref(n, w, off, i):
    return n if w == 1 else f"{n}[{off + i}]"


def make_rtl(h, sub_cls, sub):
    """Twin RTL: the campaign's golden wrapper of host h plus the twin body; one output assign rewritten."""
    H = HOSTS[h]
    gold = (HP / "rtl" / h / f"{h}__golden.v").read_text()
    bits = H["din"] + H["dout"]
    data = "    wire [63:0] trj_data = {" + ", ".join(bits[j % len(bits)] for j in range(63, -1, -1)) + "};\n"
    outbit = random.Random(f"{SEED}-{h}-{sub_cls}-{sub}-out").choice(H["dout"])
    rng = random.Random(f"{SEED}-{h}-{sub_cls}-{sub}")
    bm = dict(SEQ=f"always @(posedge {H['clk']} or posedge {H['rst']})", RSTC=H["rst"], OUTBIT=outbit,
              CLK=H["clk"], NIN=len(H["din"]))
    body, out0, params = tg.GEN_LIVE[sub_cls](rng, bm, sub)
    tgt = outbit.removeprefix("core_")
    line = f"    assign {tgt} = {outbit};\n"
    top = gold.rindex(f"\nmodule {h}(")
    assert gold.count(line, top) == 1, (h, line)
    first_assign = gold.index("    assign ", top)
    src = gold[:first_assign] + data + body + gold[first_assign:].replace(line, f"    assign {tgt} = {out0};\n", 1)
    iid = f"{h}__L{sub_cls}_{sub}"
    f = R / "rtl" / h / f"{iid}.v"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(src)
    return dict(id=iid, host=h, cls=sub_cls, sub=sub, outbit=outbit, params=params, rtl=str(f))


# ------------------------------------------------------------------ flows
def golden_nl(h, flow):
    if flow == "LL":
        r = LLC.get(f"{h}__golden", {})
        return r.get("syn_nl") if r.get("syn_sha") else None
    p = HP / flow / f"{h}__golden" / "nl.v"
    return str(p) if p.exists() else None


def synth(inst, flow):
    iid, h = inst["id"], inst["host"]
    if flow == "LL":
        C.write_cfg(iid, {"CLOCK_PERIOD": 20, "FP_CORE_UTIL": 40, "PL_TARGET_DENSITY_PCT": 55,
                          "ERROR_ON_LINTER_ERRORS": False, "DESIGN_NAME": h, "VERILOG_FILES": [inst["rtl"]],
                          "CLOCK_PORT": HOSTS[h]["clk"]})
        r = C.synth(iid, h)
        return r.get("syn_nl") if r.get("syn_sha") else None, r.get("syn_sha")
    d = R / flow / iid
    d.mkdir(parents=True, exist_ok=True)
    # the campaign's own script for this host's golden, with only the RTL and output paths changed
    ys = (HP / flow / f"{h}__golden" / "s.ys").read_text()
    ys = re.sub(r"^read_verilog -sv \S+", f"read_verilog -sv {inst['rtl']}", ys, count=1, flags=re.M)
    ys = re.sub(r"^write_verilog -noattr \S+", f"write_verilog -noattr {d / 'nl.v'}", ys, count=1, flags=re.M)
    (d / "s.ys").write_text(ys)
    rc, _, _ = run(["yosys", "-q", "-l", d / "yosys.log", "-s", d / "s.ys"], d / "run.log", timeout=7200)
    nl = d / "nl.v"
    return (str(nl), wb.sha256(nl)) if rc == 0 and nl.exists() else (None, None)


# ------------------------------------------------------------------ eq_rst with counterexample
def equiv_cex(h, gold, gate, tag, timeout=600):
    """Same miter as Campaign.equiv_abc(clk=, rst=); additionally writes the AIGER map and, on `different`,
    the counterexample, converted to a list of per-cycle {input: bitstring} dicts."""
    H = HOSTS[h]; clk, rst = H["clk"], H["rst"]
    out = R / "eq" / tag
    out.mkdir(parents=True, exist_ok=True)
    (out / "rst_wrap.v").write_text(C._reset_wrappers(gold, h, clk, rst))
    ys = (f"read_liberty -ignore_miss_func {LIB}\nread_verilog {gold}\nrename {h} gold\n"
          f"read_verilog {gate}\nrename {h} gate\ndelete {tl.PHYS_SEL}\n"
          f"read_verilog {out / 'rst_wrap.v'}\nproc\n"
          "miter -equiv -flatten gold_w gate_w miter\nhierarchy -top miter\n"
          "select -assert-none t:sky130_fd_sc_hd__*\nflatten\nsetundef -init -zero\nasync2sync\ntechmap\nopt -fast\n"
          "dfflegalize -cell $_DFF_P_ 01\ntechmap\nopt_clean\n"
          "select -assert-none t:$_DLATCH_*\nsetundef -init -zero\naigmap\n"
          f"write_aiger -zinit -map {out / 'map.txt'} {out / 'miter.aig'}\n")
    (out / "miter.ys").write_text(ys)
    rc, _, _ = run(["yosys", "-q", "-l", out / "miter.log", "-s", out / "miter.ys"], out / "run.log")
    if rc or not (out / "miter.aig").exists():
        return {"status": "error", "engine": None}
    res = {}
    for engine in ("dprove", f"pdr -T {timeout}"):
        cex = out / f"cex_{engine.split()[0]}.aiw"
        cex.unlink(missing_ok=True)
        rc, txt, el = run(["yosys-abc", "-c", f"read_aiger {out / 'miter.aig'}; {engine}; write_cex -a {cex}"],
                          out / f"{engine.split()[0]}.log", timeout=timeout + 60)
        if re.search(r"Networks are equivalent|Property proved|UNSAT", txt) and not re.search(r"NOT EQUIVALENT|asserted", txt):
            res = {"status": "proved", "engine": engine.split()[0], "elapsed_s": el}; break
        if re.search(r"UNDECIDED|Counter-example is not available|Reached timeout", txt):
            res = {"status": "undecided", "engine": engine.split()[0], "elapsed_s": el}; continue
        if re.search(r"not equivalent|was asserted in frame", txt, re.I) and cex.exists():
            res = {"status": "different", "engine": engine.split()[0], "elapsed_s": el}
            if cex.exists() and cex.stat().st_size:
                res["witness"] = cex_to_vectors(cex, out / "map.txt", rst)
                res["cex_file"] = str(cex)
            break
        res = {"status": "undecided", "engine": engine.split()[0], "elapsed_s": el}
    return res


def cex_to_vectors(aiw, mapf, rst):
    """AIGER 1.9 witness -> [{port: bitstring MSB first}] per frame. Reset is set to 1 in frame 0 (the miter's
    wrapper forces it there whatever the input value)."""
    lines = [l.strip() for l in Path(aiw).read_text().splitlines()
             if l.strip() and not l.startswith("#") and l.strip() != "."]
    while lines and re.fullmatch(r"[01]|b\d+", lines[0]):    # optional AIGER 1.9 header lines
        lines.pop(0)
    frames = lines[1:]                                       # first line: latch initial values
    imap = {}
    for l in Path(mapf).read_text().splitlines():
        p = l.split()
        if p and p[0] == "input":
            imap[int(p[1])] = (p[3].removeprefix("in_"), int(p[2]))
    width = {}
    for n, b in imap.values():
        width[n] = max(width.get(n, 0), b + 1)
    vecs = []
    for f in frames:
        v = {n: ["0"] * w for n, w in width.items()}
        for idx, (n, b) in imap.items():
            if idx < len(f) and f[idx] in "01":
                v[n][width[n] - 1 - b] = f[idx]
        vecs.append({n: "".join(bits) for n, bits in v.items()})
    if vecs and rst in vecs[0]:
        vecs[0][rst] = "1"
    return vecs


# ------------------------------------------------------------------ replay
def model(nl, h, side, mode, d):
    """Flatten the netlist with the Liberty functions and write it as plain Verilog. mode `reset`: flops without an
    init value get 0 (as in the miter); mode `x_init`: every init value removed."""
    f = d / f"{side}_{mode}.v"
    # Same preprocessing as the eq_rst miter. A Liberty flop is read as two internal flops (IQ and IQ_N); right after
    # flatten, setundef gave an init value to only one of them, so outputs stayed X in `reset` mode (24 Nov, first
    # run: 238 rows `different` but no divergence). After techmap every flop is a $_DFF_P_ and gets its init value.
    # x_init: no opt step, because opt_dff folds a flop with undefined init and constant D into a constant (X-optimistic).
    if mode == "reset":
        prep = ("flatten\nsetundef -init -zero\nasync2sync\ntechmap\nopt -fast\ndfflegalize -cell $_DFF_P_ 01\n"
                "techmap\nopt_clean\nsetundef -init -zero\n")
    else:
        prep = "flatten\nsetattr -unset init w:*\nasync2sync\ntechmap\nopt_clean\n"
    ys = (f"read_liberty -ignore_miss_func {LIB}\nread_verilog {nl}\nhierarchy -top {h}\ndelete {tl.PHYS_SEL}\n"
          f"{prep}rename {h} {side}\nwrite_verilog -noattr {f}\n")
    (d / f"{side}_{mode}.ys").write_text(ys)
    rc, _, _ = run(["yosys", "-q", "-s", d / f"{side}_{mode}.ys"], d / f"{side}_{mode}.log")
    return f if rc == 0 else None


def ports(nl, h):
    src = Path(nl).read_text()
    m = re.search(r"\bmodule\s+\\?" + re.escape(h) + r"\s*\((.*?)\);(.*?)\bendmodule", src, re.S)
    res = []
    for d, w, ns in re.findall(r"^\s*(input|output)\s+(?:wire\s+)?(\[[^\]]+\]\s*)?([^;]+);", m.group(2), re.M):
        width = 1
        if w:
            a, b = re.findall(r"-?\d+", w)
            width = abs(int(a) - int(b)) + 1
        for n in ns.split(","):
            res.append((d, n.strip(), width))
    return res


def replay(h, gold, gate, vecs, tag):
    d = R / "replay" / tag
    d.mkdir(parents=True, exist_ok=True)
    clk = HOSTS[h]["clk"]
    ps = ports(gold, h)
    ins = [(n, w) for k, n, w in ps if k == "input"]
    outs = [(n, w) for k, n, w in ps if k == "output"]
    (d / "witness.json").write_text(json.dumps(vecs))
    res = {}
    for mode in ("reset", "x_init"):
        mg, mt = model(gold, h, "gold", mode, d), model(gate, h, "gate", mode, d)
        if not (mg and mt):
            res[mode] = {"status": "error"}; continue
        decl = "".join(f"  reg [{w-1}:0] {n};\n" for n, w in ins) + \
               "".join(f"  wire [{w-1}:0] g_{n}, t_{n};\n" for n, w in outs)
        conn = lambda p: ", ".join([f".{n}({n})" for n, _ in ins] + [f".{n}({p}_{n})" for n, _ in outs])
        steps = ""
        for k, v in enumerate(vecs):
            asg = "".join(f"    {n} = {w}'b{v.get(n, '0' * w).zfill(w)[-w:]};\n" for n, w in ins if n != clk)
            chk = "".join(f"    $display(\"F {k} {n} %b %b\", g_{n}, t_{n});\n" for n, _ in outs)
            steps += f"    #1;\n{asg}    #3;\n{chk}    #1 {clk} = 1;\n    #5 {clk} = 0;\n"
        tb = (f"`timescale 1ns/1ps\nmodule tb;\n{decl}  gold u_g ({conn('g')});\n  gate u_t ({conn('t')});\n"
              f"  initial begin\n    {clk} = 0;\n{steps}    $finish;\n  end\nendmodule\n")
        (d / f"tb_{mode}.v").write_text(tb)
        rc, txt, _ = run(["iverilog", "-g2012", "-o", d / f"a_{mode}.out", d / f"tb_{mode}.v", mg, mt], d / f"build_{mode}.log")
        if rc:
            res[mode] = {"status": "error", "log": str(d / f"build_{mode}.log")}; continue
        rc, txt, _ = run(["vvp", "-n", d / f"a_{mode}.out"], d / f"sim_{mode}.log", timeout=600)
        if rc or not re.search(r"^F ", txt, re.M):
            res[mode] = {"status": "error", "log": str(d / f"sim_{mode}.log")}
            for f in (mg, mt, d / f"a_{mode}.out"):
                Path(f).unlink(missing_ok=True)
            continue
        div, xs = None, []
        for k, n, g, t in re.findall(r"^F (\d+) (\S+) (\S+) (\S+)$", txt, re.M):
            for i, (a, b) in enumerate(zip(g, t)):
                if a in "01" and b in "01" and a != b and div is None:
                    div = {"frame": int(k), "port": n, "bit_from_msb": i, "gold": a, "gate": b}
                if a not in "01" or b not in "01":
                    xs.append((int(k), n, i))
        res[mode] = {"status": "diverged" if div else "no_divergence", "first": div, "frames": len(vecs),
                     "x_bits": len(xs)}
        # the models and the compiled simulation are large (about 120 MB per mode on b18) and can be rebuilt from
        # the netlists and witness.json; the disk filled up on 24 Nov with them kept. tb, logs and witness stay.
        for f in (mg, mt, d / f"a_{mode}.out"):
            Path(f).unlink(missing_ok=True)
    if res.get("reset", {}).get("status") == "diverged" and res.get("x_init", {}).get("status") == "no_divergence":
        f = res["reset"]["first"]
        sim = (d / "sim_x_init.log").read_text() if (d / "sim_x_init.log").exists() else ""
        m = re.search(rf"^F {f['frame']} {re.escape(f['port'])} (\S+) (\S+)$", sim, re.M)
        if m and (m.group(1)[f["bit_from_msb"]] not in "01" or m.group(2)[f["bit_from_msb"]] not in "01"):
            res["x_init"]["status"] = "x_blocked"
    return res


# ------------------------------------------------------------------ one instance, all flows
def probe(nl, h, tag):
    r = C.probe(nl, h, tag)
    for f in (R / "probe" / tag).glob("nl.json"):
        f.unlink()
    return r


_GP, _GPL = {}, __import__("threading").Lock()


def probe_golden(g, h, flow):
    """Golden probe, computed once per (host, flow); concurrent jobs shared one nl.json before (JSONDecodeError)."""
    with _GPL:
        if (h, flow) not in _GP:
            _GP[(h, flow)] = probe(g, h, f"{flow}__{h}__golden")
        return _GP[(h, flow)]


def one(inst):
    h, rows = inst["host"], []
    for flow in FLOWS:
        r = {k: inst[k] for k in ("id", "host", "cls", "sub", "outbit", "params")}
        r["flow"] = flow
        g = golden_nl(h, flow)
        t, sha = synth(inst, flow)
        r["synth_ok"] = bool(t)
        if not (g and t):
            r["tier"] = "ERROR"; rows.append(r); continue
        r["identical"] = sha == wb.sha256(g)
        if r["identical"]:
            r["tier"], r["grade"] = "REMOVED", "identical"; rows.append(r); continue
        pg, pt = probe_golden(g, h, flow), probe(t, h, f"{flow}__{inst['id']}")
        r["delta"] = {k: pt[k] - pg[k] for k in ("logic_cells", "flops", "const_cells", "passthrough_cells")}
        remnant = any(r["delta"][k] > 0 for k in ("flops", "const_cells", "passthrough_cells"))
        e = equiv_cex(h, g, t, f"{flow}__{inst['id']}")
        r["eq_rst"] = {k: v for k, v in e.items() if k != "witness"}
        if e.get("witness"):
            r["witness_frames"] = len(e["witness"])
            r["replay"] = replay(h, g, t, e["witness"], f"{flow}__{inst['id']}")
            r["control_replay"] = replay(h, g, g, e["witness"], f"{flow}__{inst['id']}__ctl")   # golden vs itself
        rp = r.get("replay", {})
        rs, xs = rp.get("reset", {}).get("status"), rp.get("x_init", {}).get("status")
        ctl_bad = any(v.get("status") == "diverged" for v in r.get("control_replay", {}).values())
        if ctl_bad:
            r["tier"] = "CONFLICT"
        elif rs == "diverged" or xs == "diverged":
            r["tier"] = "CONFLICT" if e["status"] == "proved" else "FUNCTIONAL"
            r["grade"] = "x_init" if xs == "diverged" else "reset_only"
        elif e["status"] == "proved":
            r["tier"], r["grade"] = ("INERT", None) if remnant else ("REMOVED", "no_remnant_proved")
        else:
            r["tier"] = "UNDECIDED"
            if e["status"] == "different":
                r["flag"] = "functional_candidate"
        rows.append(r)
    return rows


# ------------------------------------------------------------------ batch
import threading
from concurrent.futures import ThreadPoolExecutor
LOCK = threading.Lock()
STATUS = {"done": 0, "n": 0, "errors": [], "t0": None, "finished": False}


def run_all(hosts, workers=8):
    insts = [make_rtl(h, c, s) for h in hosts for c, subs in tg.SUBS.items() for s in subs]
    with open(R / "instances.jsonl", "w") as fh:
        for i in insts: fh.write(json.dumps(i) + "\n")
    STATUS.update(n=len(insts), t0=time.time())
    def job(inst):
        try:
            rows = one(inst)
        except Exception as ex:
            rows = [{"id": inst["id"], "host": inst["host"], "tier": "ERROR", "error": f"{type(ex).__name__}: {ex}"[:300]}]
            STATUS["errors"].append(inst["id"])
        with LOCK:
            with open(R / "rows.jsonl", "a") as fh:
                for r in rows: fh.write(json.dumps(r, default=str) + "\n")
            STATUS["done"] += 1
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, insts))
    STATUS["finished"] = True
    (R / "run.done").write_text(json.dumps({k: v for k, v in STATUS.items()}, default=str))


def rereplay(workers=8):
    """Replay again every row whose eq_rst is `different` (after the model fix) and recompute its tier."""
    rows = [json.loads(l) for l in open(R / "rows.jsonl")]
    def fix(r):
        if r.get("eq_rst", {}).get("status") != "different" or not r["eq_rst"].get("cex_file"):
            return r
        h, flow = r["host"], r["flow"]
        g = golden_nl(h, flow)
        t = LLC_twin(r["id"]) if flow == "LL" else str(R / flow / r["id"] / "nl.v")
        vecs = cex_to_vectors(r["eq_rst"]["cex_file"], Path(r["eq_rst"]["cex_file"]).parent / "map.txt", HOSTS[h]["rst"])
        r["replay"] = replay(h, g, t, vecs, f"{flow}__{r['id']}")
        r["control_replay"] = replay(h, g, g, vecs, f"{flow}__{r['id']}__ctl")
        rs, xs = r["replay"]["reset"]["status"], r["replay"]["x_init"]["status"]
        r.pop("flag", None); r.pop("grade", None)
        if any(v.get("status") == "diverged" for v in r["control_replay"].values()):
            r["tier"] = "CONFLICT"
        elif rs == "diverged" or xs == "diverged":
            r["tier"], r["grade"] = "FUNCTIONAL", ("x_init" if xs == "diverged" else "reset_only")
        else:
            r["tier"], r["flag"] = "UNDECIDED", "functional_candidate"
        return r
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(fix, rows))
    with open(R / "rows_v2.jsonl", "w") as fh:
        for r in out: fh.write(json.dumps(r, default=str) + "\n")
    return R / "rows_v2.jsonl"


def LLC_twin(iid):
    p = sorted((R / "ll" / iid).glob("*-yosys-synthesis/*.nl.v"))
    return str(p[-1]) if p else None


# ------------------------------------------------------------------ free-start check (24 Nov 2026)
# eq_rst starts every flop without a reset at 0. A Trojan register without a reset (an LFSR, say) can then sit at 0
# forever and the miter proves the netlists equivalent, although on silicon it powers up in an unknown state.
# The free-start miter keeps the reset forced in cycle 0 but gives every flop (gold and gate) a free initial value
# and compares the outputs from cycle 1 on, after the reset edge. All host flops are reset (every ITC'99 VHDL reset and
# every ISCAS-89 flop; checked below with golden vs golden), so after cycle 0 only flops without a reset can differ.
# Property: "after one reset cycle, from every power-up state, the outputs agree forever".

def _free_wrappers(nl, design, clk, rst):
    src = open(nl).read()
    m = re.search(r"\bmodule\s+\\?" + re.escape(design) + r"\s*\((.*?)\);(.*?)\bendmodule", src, re.S)
    decls = re.findall(r"^\s*(input|output)\s+(?:wire\s+)?(\[[^\]]+\]\s*)?([^;]+);", m.group(2), re.M)
    ports_ = [(d, (w or "").strip(), n.strip()) for d, w, ns in decls for n in ns.split(",")]
    names = [n for _, _, n in ports_]
    out = ""
    for side in ("gold", "gate"):
        body = "".join(f"  {d} {w} {n};\n" for d, w, n in ports_)
        body += "".join(f"  wire {w} i_{n};\n" for d, w, n in ports_ if d == "output")
        conn = ", ".join(f".{n}({n} | ~eqv_started)" if n == rst else (f".{n}(i_{n})" if d == "output" else f".{n}({n})")
                         for d, w, n in ports_)
        gate_ = "".join(f"  assign {n} = eqv_started ? i_{n} : {{$bits(i_{n}){{1'b0}}}};\n" for d, w, n in ports_ if d == "output")
        out += (f"module {side}_w({', '.join(names)});\n{body}  reg eqv_started = 1'b0;\n"
                f"  always @(posedge {clk}) eqv_started <= 1'b1;\n  {side} eqv_dut ({conn});\n{gate_}endmodule\n")
    return out


def equiv_free(h, gold, gate, tag, timeout=600):
    H = HOSTS[h]; clk, rst = H["clk"], H["rst"]
    out = R / "eq_free" / tag
    out.mkdir(parents=True, exist_ok=True)
    (out / "free_wrap.v").write_text(_free_wrappers(gold, h, clk, rst))
    ys = (f"read_liberty -ignore_miss_func {LIB}\nread_verilog {gold}\nrename {h} gold\n"
          f"read_verilog {gate}\nrename {h} gate\ndelete {tl.PHYS_SEL}\n"
          f"read_verilog -sv {out / 'free_wrap.v'}\nproc\n"
          "miter -equiv -flatten gold_w gate_w miter\nhierarchy -top miter\n"
          # no setundef -init: only eqv_started has an init value (0); every other flop starts free
          "select -assert-none t:sky130_fd_sc_hd__*\nflatten\nasync2sync\ndffunmap\ntechmap\nopt_clean\n"
          # not dfflegalize (it rejects an undefined init value in its cell list): dffunmap turns enable and
          # sync-reset flops into plain $_DFF_P_ plus logic and keeps undefined init values (checked by the select)
          "select -assert-none t:$_DLATCH_*\nselect -assert-none t:$_*FF* t:$_DFF_P_ %d\naigmap\n"
          # -zinit: every flop without an init value gets an extra free input that sets its first-cycle value
          f"write_aiger -zinit -map {out / 'map.txt'} {out / 'miter.aig'}\n")
    (out / "miter.ys").write_text(ys)
    rc, _, _ = run(["yosys", "-q", "-l", out / "miter.log", "-s", out / "miter.ys"], out / "run.log")
    if rc or not (out / "miter.aig").exists():
        return {"status": "error", "log": str(out / "miter.log")}
    nfree = len({l.split()[1] for l in (out / "map.txt").read_text().splitlines() if l.startswith("init ")})
    res = {}
    for engine in ("dprove", f"pdr -T {timeout}"):
        cex = out / f"cex_{engine.split()[0]}.aiw"
        cex.unlink(missing_ok=True)
        rc, txt, el = run(["yosys-abc", "-c", f"read_aiger {out / 'miter.aig'}; {engine}; write_cex -a {cex}"],
                          out / f"{engine.split()[0]}.log", timeout=timeout + 60)
        if re.search(r"Networks are equivalent|Property proved|UNSAT", txt) and not re.search(r"NOT EQUIVALENT|asserted", txt):
            res = {"status": "proved", "engine": engine.split()[0], "elapsed_s": el}; break
        if re.search(r"UNDECIDED|Counter-example is not available|Reached timeout", txt):
            res = {"status": "undecided", "engine": engine.split()[0], "elapsed_s": el}; continue
        if re.search(r"not equivalent|was asserted in frame", txt, re.I) and cex.exists():
            m = re.search(r"asserted in frame (\d+)", txt)
            res = {"status": "different", "engine": engine.split()[0], "elapsed_s": el,
                   "frame": int(m.group(1)) if m else None, "cex_file": str(cex)}; break
        res = {"status": "undecided", "engine": engine.split()[0], "elapsed_s": el}
    res["free_init_inputs"] = nfree
    return res


def run_subset(hosts, subs, out_name, workers=8):
    """Regenerate and rerun the twins of the given (cls, sub) pairs; rows go to out_name (rows.jsonl untouched)."""
    insts = [make_rtl(h, c, s) for h in hosts for c, s in subs]
    with open(R / f"instances_{out_name}", "w") as fh:
        for i in insts: fh.write(json.dumps(i) + "\n")
    def job(inst):
        try:
            rows = one(inst)
        except Exception as ex:
            rows = [{"id": inst["id"], "host": inst["host"], "tier": "ERROR", "error": f"{type(ex).__name__}: {ex}"[:300]}]
        with LOCK, open(R / out_name, "a") as fh:
            for r in rows: fh.write(json.dumps(r, default=str) + "\n")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, insts))
    (R / f"{out_name}.done").write_text("ok")


def campaign_nl(iid, flow):
    if flow == "LL":
        r = LLC.get(iid, {})
        return r.get("syn_nl") if r.get("syn_sha") else None
    p = HP / flow / iid / "nl.v"
    return str(p) if p.exists() else None


def free_batch(jobs, out_name, workers=8):
    """jobs: (kind, host, flow, id, gold_nl, gate_nl). One JSON line per job in out_name."""
    def job(j):
        kind, h, flow, iid, g, t = j
        try:
            r = equiv_free(h, g, t, f"{kind}/{flow}__{iid}")
        except Exception as ex:
            r = {"status": "error", "error": f"{type(ex).__name__}: {ex}"[:300]}
        rec = {"kind": kind, "host": h, "flow": flow, "id": iid, **r}
        with LOCK, open(R / out_name, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, jobs))
    (R / f"{out_name}.done").write_text("ok")
