"""Export the v1.1 flow-labelled population into the release layout of
spec/DRAFT-flow-labels-v1.1-2026-11-23.md (sections 4 and 8.3, admission option (a)).

It copies and renames. It runs no synthesis, no proof and no replay, and it never
changes a tier: every label comes from labels_release.jsonl as it stands.

Inputs (two run directories of the workbench):
  --twins   live_twins_20261124          labels_release.jsonl, twin netlists, witnesses
  --campaign host_population_20261122_*  decoy netlists, golden netlists, campaign CSV

Output tree (--out):
  flows.json, hosts.json, labels.jsonl, MANIFEST.json
  golden/<host>/rtl.v
  golden/<host>/<flow_id>/netlist.v
  data/samples/<sample_id>/sample.json, rtl.v
  data/samples/<sample_id>/flow_labels/<flow_id>/label.json, netlist.v,
      witness.vec, power_up_state.json

Usage:
  python tools/htbench/export_release.py --twins T --campaign C --out OUT
  python tools/htbench/export_release.py --check OUT
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

SCHEMA_VERSION = "1.1-draft"
FLOW_DIR = {"LL": "ll", "Y_sat": "Y_sat", "Y_seq": "Y_seq"}
CONTAINER_ROOT = "/foss/designs/outputs/"
# Upstream terms of the host circuits, checked 25 Nov 2026. EUPL-1.2 is copyleft and CC-BY-4.0 is not one of its
# compatible licences, so netlists and RTL derived from ITC'99 hosts are not redistributed (decision 25 Nov 2026).
UPSTREAM = {
    "ITC99": {"license": "EUPL-1.2", "license_url": "https://github.com/cad-polito-it/I99T"},
    "ISCAS89": {"license": "NOASSERTION", "license_url": None,
                "note": "no licence stated by the original MCNC distribution (Brglez, Bryan, Kozminski, 1989)"},
}
EXCLUDED_HOSTS = {"b18", "b19"}          # b19: host set decision 23 Nov 2026; b18: release decision 24 Nov 2026


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def jl(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=False) + "\n")


def sid(campaign_id):
    s = campaign_id.lower()
    assert re.fullmatch(r"[a-z0-9_]+", s), campaign_id
    return s


class Src:
    def __init__(self, twins, campaign):
        self.T, self.C = Path(twins), Path(campaign)
        self.outputs = self.T.parent

    def local(self, container_path):
        """A path recorded inside the container -> the same file on this machine."""
        assert container_path.startswith(CONTAINER_ROOT), container_path
        return self.outputs / container_path[len(CONTAINER_ROOT):]

    def netlist(self, kind, cid, host, flow):
        root = self.T if kind == "twin" else self.C
        if flow == "LL":
            return root / "ll" / cid / "06-yosys-synthesis" / f"{host}.nl.v"
        return root / flow / cid / "nl.v"

    def golden(self, host, flow):
        return self.netlist("decoy", f"{host}__golden", host, flow)

    def rtl(self, kind, cid, host):
        return (self.T if kind == "twin" else self.C) / "rtl" / host / f"{cid}.v"


# ---------------------------------------------------------------- flows
def script_hashes(src, flow, hosts):
    """Hash of each host's golden script with the host name and paths masked: {hash: (hosts, text)}.
    Hosts whose script differs get their own flow_id (rule R13: any script change is a new flow)."""
    out = {}
    for h in hosts:
        ys = (src.C / flow / f"{h}__golden" / "s.ys").read_text()
        ys = re.sub(r"/foss/\S+", "<PATH>", ys)
        ys = re.sub(rf"-top {re.escape(h)}\b", "-top <HOST>", ys)
        out.setdefault(hashlib.sha256(ys.encode()).hexdigest(), ([], ys))[0].append(h)
    return out


def build_flows(src, hosts):
    """Returns (flow registry entries, {(host, campaign flow name): flow_id})."""
    h0 = sorted(hosts)[0]
    ycmt = src.golden(h0, "Y_sat").read_text().splitlines()[0]
    yosys = re.search(r"Yosys ([0-9.]+) \(git sha1 ([0-9a-f]+)", ycmt)
    yosys_v = f"{yosys.group(1)} (git {yosys.group(2)})" if yosys else None
    cfg = (src.C / "ll" / f"{h0}__golden" / "06-yosys-synthesis" / "config.json").read_text()
    m = re.search(r'"librelane_version":\s*"([^"]+)"', cfg)
    assert m, "LibreLane version not found in the run's config.json"
    llv = m.group(1)
    pdk = {"name": "sky130A", "pdk_version": None, "std_cell_lib": "sky130_fd_sc_hd", "liberty_corner": "tt_025C_1v80"}
    flows, ids = [], {}
    ll = f"ll_classic@{llv}"
    for h in hosts:
        ids[(h, "LL")] = ll
    flows.append({"flow_id": ll, "flow_family": "open_source",
                  "description": "LibreLane Classic, synthesis step only (06-yosys-synthesis netlist)",
                  "tools": {"librelane": llv, "yosys": None, "abc": None}, "script_sha256": None,
                  "pdk": pdk, "options": "LibreLane defaults; per-design config.json in the run directory",
                  "reference_flow": True, "hosts": "all",
                  "not_recorded": ["tools.yosys", "tools.abc", "script_sha256", "pdk.pdk_version"]})
    for flow, desc in (("Y_sat", "Yosys with opt -full; opt_dff -sat"),
                       ("Y_seq", "Y_sat plus abc -dff with scorr")):
        variants = script_hashes(src, flow, hosts)
        for hsh, (hs, text) in sorted(variants.items(), key=lambda kv: -len(kv[1][0])):
            f = f"{flow.lower()}@{hsh[:12]}"
            for h in hs:
                ids[(h, flow)] = f
            flows.append({"flow_id": f, "flow_family": "open_source", "description": desc,
                          "tools": {"yosys": yosys_v, "abc": "yosys-abc as bundled"}, "script_sha256": hsh,
                          "script": text, "pdk": pdk, "options": desc, "reference_flow": False,
                          "hosts": "all" if len(variants) == 1 else sorted(hs),
                          "not_recorded": ["pdk.pdk_version"]})
    return flows, ids


# ---------------------------------------------------------------- witnesses
def cex_to_vectors(aiw, mapf, rst):
    """AIGER 1.9 witness -> [{port: bits MSB first}] per frame. Same conversion as live_twins/lt.py."""
    lines = [l.strip() for l in Path(aiw).read_text().splitlines()
             if l.strip() and not l.startswith("#") and l.strip() != "."]
    while lines and re.fullmatch(r"[01]|b\d+", lines[0]):
        lines.pop(0)
    frames = lines[1:]
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


def write_vec(p, vecs, source):
    ports = sorted(vecs[0]) if vecs else []
    out = [f"# primary-input vectors, one line per clock cycle, bits MSB first; source: {source}",
           "# ports: " + " ".join(ports)]
    out += [" ".join(f"{n}={v[n]}" for n in ports) for v in vecs]
    p.write_text("\n".join(out) + "\n")


def replay_entry(mode, r):
    first = (r or {}).get("first") or {}
    return {"mode": mode, "simulator": "icarus", "cell_models": "liberty_function_flattened",
            "x_model_checked": False, "result": (r or {}).get("status", "not_run"),
            "first_divergence_cycle": first.get("frame"), "diverging_output": first.get("port")}


# ---------------------------------------------------------------- export
def export(args):
    src, out = Src(args.twins, args.campaign), Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty; refusing to overwrite")
    rows = jl(src.T / "labels_release.jsonl")
    bad = {r["host"] for r in rows} & EXCLUDED_HOSTS
    if bad:
        raise SystemExit(f"excluded hosts in the label file: {bad}")
    hosts_all = json.loads((src.C / "hosts.json").read_text())
    hosts = sorted({r["host"] for r in rows})
    flows, fid = build_flows(src, hosts)
    dump(out / "flows.json", flows)
    lo_fam = set(args.labels_only_family or [])
    unknown = {hosts_all[h]["family"] for h in hosts} - set(UPSTREAM)
    if unknown:
        raise SystemExit(f"no upstream licence recorded for families {unknown}")

    def lo(h):
        """True when no netlist or RTL of host h is written."""
        return args.labels_only or hosts_all[h]["family"] in lo_fam

    dump(out / "hosts.json", {h: {**{k: hosts_all[h][k] for k in ("family", "mod", "ports", "clk", "rst", "din", "dout")
                                     if k in hosts_all[h]},
                                  "upstream": UPSTREAM[hosts_all[h]["family"]],
                                  "distribution": "labels_only" if lo(h) else "netlists"} for h in hosts})

    camp = {(r["id"], r["flow"]): r for r in csv.DictReader(open(src.C / "per_instance_flow_rst.csv"))}
    inst_c = {r["id"]: r for r in csv.DictReader(open(src.C / "instances.csv"))}
    eq_c = {r["tag"]: r for r in jl(src.C / "eq_rst.jsonl") if r.get("kind") == "inst"}
    free = {}
    for name in ("free.jsonl", "free_big.jsonl", "free_redo2.jsonl"):
        for r in jl(src.T / name):
            free[(r["kind"], r["id"], r["flow"])] = r

    gsha = {}
    for h in hosts:
        if not lo(h):
            (out / "golden" / h).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src.rtl("decoy", f"{h}__golden", h), out / "golden" / h / "rtl.v")
        for flow in FLOW_DIR:
            g = src.golden(h, flow)
            gsha[(h, flow)] = sha256(g)
            if not lo(h):
                d = out / "golden" / h / fid[(h, flow)]
                d.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(g, d / "netlist.v")

    index, missing = [], []
    today = datetime.date.today().isoformat()
    for r in rows:
        kind, cid, host, flow = r["kind"], r["id"], r["host"], r["flow"]
        s = sid(cid)
        sdir = out / "data" / "samples" / s
        fdir = sdir / "flow_labels" / fid[(host, flow)]
        fdir.mkdir(parents=True, exist_ok=True)
        nl = src.netlist(kind, cid, host, flow)
        if not nl.exists():
            missing.append(str(nl)); continue
        tsha = sha256(nl)
        if not lo(host):
            shutil.copyfile(nl, fdir / "netlist.v")
        if not (sdir / "sample.json").exists():
            meta = r if kind == "twin" else inst_c[cid]     # twin rows carry their own parameters
            params = meta["params"] if isinstance(meta["params"], dict) else json.loads(meta["params"])
            dump(sdir / "sample.json", {
                "sample_id": s, "campaign_id": cid, "admission": "flow_labelled", "host_id": host,
                "distribution": "labels_only" if lo(host) else "netlists",
                "family": hosts_all[host].get("family"), "population": "live_twin" if kind == "twin" else "decoy",
                "trojan_class": r["cls"], "sub_variant": r["sub"], "params": params,
                "payload_output": meta.get("outbit") or None})
            if not lo(host):
                shutil.copyfile(src.rtl(kind, cid, host), sdir / "rtl.v")

        # ---- equivalence
        if kind == "twin":
            e = r["eq_rst"]; est, eng, els = e["status"], e.get("engine"), e.get("elapsed_s")
            ef = r.get("eq_free")
        else:
            est = r.get("eq_rst", "not_run")
            e = eq_c.get(f"rst/{flow}__{cid}", {})
            eng, els = (e.get("engine"), e.get("elapsed_s")) if e.get("status") == est else (None, None)
            fst = r.get("eq_free", "not_run")
            fr = free.get(("decoy", cid, flow), {})
            ef = {"status": fst}
            if fr.get("status") == fst:
                ef.update(engine=fr.get("engine"), frame=fr.get("frame"), free_init_inputs=fr.get("free_init_inputs"))
        ident = bool(r["identical"])
        eqv = {"method": "not_run" if est == "not_run" else "abc_miter_reset", "init": "reset_cycle0_zero_uninit",
               "engines": ["dprove", "pdr"], "decided_by": eng if est in ("proved", "different") else None,
               "bounded": False, "bound": None, "timeout_s": 600, "elapsed_s": els, "status": est,
               "counterexample_file": None, "abc_version": None}
        if ef:
            eqv["free_start"] = {"status": ef["status"],
                                 "decided_by": ef.get("engine") if ef["status"] in ("proved", "different") else None,
                                 "first_frame": ef.get("frame"), "free_flops": ef.get("free_init_inputs"),
                                 "counterexample_file": None}

        # ---- delta and remnant
        if kind == "twin":
            d = r["delta"]
            delta = {"cells": d["logic_cells"], "area_um2": None, "flops": d["flops"],
                     "const_drivers": d["const_cells"], "pass_through": d["passthrough_cells"]}
            attr = "trojan" if any(delta[k] > 0 for k in ("flops", "const_drivers", "pass_through")) else "none"
        else:
            c = camp[(cid, flow)]
            delta = {"cells": int(float(c["d_cells"])), "area_um2": round(float(c["d_area"]), 4),
                     "flops": int(float(c["d_flops"])), "const_drivers": int(float(c["d_const"])),
                     "pass_through": int(float(c["d_pass"]))}
            attr = r.get("remnant", "none")
        remnant = {"attribution": attr, "evidence_level": "delta_only", "trojan_named_cells": None,
                   "labels_netlist_file": None}

        # ---- witness
        wit = {"source": "none", "file": None, "sha256": None, "cycles": None, "replays": [],
               "divergence_attribution": None}
        cex = None
        if kind == "twin" and r["eq_rst"].get("cex_file"):
            cex, wsrc = src.local(r["eq_rst"]["cex_file"]), "eq_counterexample"
            wit["replays"] = [replay_entry(m, r.get("replay", {}).get(m)) for m in ("reset", "x_init")]
        elif kind == "twin" and (r.get("eq_free") or {}).get("cex_file"):
            cex, wsrc = src.local(r["eq_free"]["cex_file"]), "eq_free_counterexample"
            fr = r.get("free_replay") or {}
            wit["replays"] = [replay_entry("power_up", fr.get("replay")), replay_entry("x_init", fr.get("no_init"))]
            if fr.get("deposits_gate"):
                dump(fdir / "power_up_state.json", {
                    "description": "Frame-0 value of each flop that has no reset, on the <cell>.IQ register of the "
                                   "flattened Liberty-function model of netlist.v; all other flops start X.",
                    "deposits": [{"register": a, "value": b} for a, b in fr["deposits_gate"]]})
        if cex is not None:
            vecs = cex_to_vectors(cex, cex.parent / "map.txt", hosts_all[host]["rst"])
            write_vec(fdir / "witness.vec", vecs, wsrc)
            wit.update(source=wsrc, file="witness.vec", sha256=sha256(fdir / "witness.vec"), cycles=len(vecs))
            if any(x["result"] == "diverged" for x in wit["replays"]):
                wit["divergence_attribution"] = "trigger_only"
            if wsrc == "eq_counterexample":
                eqv["counterexample_file"] = "witness.vec"
            else:
                eqv["free_start"]["counterexample_file"] = "witness.vec"

        tier = r["tier"].lower()
        label = {
            "schema_version": SCHEMA_VERSION, "sample_id": s, "flow_id": fid[(host, flow)], "host_id": host, "tier": tier,
            "functional_grade": r["grade"] if tier == "functional" else None,
            "removed_reason": r["grade"] if tier == "removed" else None,
            "perturbation_cause": "scorr_merge" if tier == "host_perturbation" else None,
            "comparison_flow_id": fid[(host, "Y_sat")] if tier == "host_perturbation" else None,
            "flags": list(r.get("flags") or []),
            "netlists": {"trojan_sha256": tsha, "golden_sha256": gsha[(host, flow)], "identical": ident},
            "equivalence": eqv, "remnant": remnant, "delta": delta, "witness": wit,
            "provenance": {"campaign": src.T.name if kind == "twin" else src.C.name,
                           "produced_by": "live_twins/lt.py; tools/htbench/export_release.py", "date": today}}
        dump(fdir / "label.json", label)
        index.append({"sample_id": s, "flow_id": fid[(host, flow)], "host_id": host,
                      "population": "live_twin" if kind == "twin" else "decoy", "tier": tier,
                      "functional_grade": label["functional_grade"], "removed_reason": label["removed_reason"],
                      "flags": label["flags"], "path": str(fdir.relative_to(out))})

    with open(out / "labels.jsonl", "w") as f:
        for x in index:
            f.write(json.dumps(x) + "\n")
    files = sorted(p for p in out.rglob("*") if p.is_file())
    dump(out / "MANIFEST.json", {
        "release": "trove-flow-labels", "schema_version": SCHEMA_VERSION, "date": today,
        "labels_only_hosts": sorted(h for h in hosts if lo(h)), "label_records": len(index), "hosts": len(hosts),
        "files": [{"path": str(p.relative_to(out)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in files]})
    print(f"exported {len(index)} label records, {len(files)} files, to {out}")
    if missing:
        print(f"MISSING NETLISTS: {len(missing)}"); [print("  ", m) for m in missing[:10]]
        return 1
    return 0


# ---------------------------------------------------------------- checks
def recompute_tier(L):
    """Decision table of spec section 3.5, applied in order to the stored evidence."""
    e, fs = L["equivalence"], L["equivalence"].get("free_start", {}).get("status")
    att = L["remnant"]["attribution"]
    div = any(x["result"] == "diverged" and x["mode"] in ("reset", "x_init") for x in L["witness"]["replays"])
    if L["netlists"]["identical"]:
        return "removed"
    if div:
        return "conflict" if e["status"] == "proved" else "functional"
    if e["status"] == "proved":
        if fs == "different":
            return "functional"
        if fs in ("undecided", "error"):
            return "undecided"
        if fs == "proved" and att == "none":
            return "removed"
        if fs == "proved" and att == "trojan":
            return "inert"
        if att == "host":
            return "host_perturbation"
        return "undecided"
    if e["status"] in ("undecided", "error") and att == "host":
        return "host_perturbation"
    return "undecided"


def check(root):
    root = Path(root)
    man = json.loads((root / "MANIFEST.json").read_text())
    labels_only_hosts = set(man["labels_only_hosts"])
    fails = collections.defaultdict(list)
    idx = jl(root / "labels.jsonl")
    flows = {f["flow_id"] for f in json.loads((root / "flows.json").read_text())}
    tiers = collections.Counter()
    seen = set()
    for x in idx:
        d = root / x["path"]
        L = json.loads((d / "label.json").read_text())
        key = (L["sample_id"], L["flow_id"])
        if key in seen:
            fails["duplicate label"].append(key)
        seen.add(key)
        tiers[(x["population"], L["flow_id"].split("@")[0], L["tier"], L["functional_grade"] or L["removed_reason"])] += 1
        if L["flow_id"] not in flows:
            fails["R12 unknown flow_id"].append(key)
        if L["host_id"] in EXCLUDED_HOSTS:
            fails["excluded host present"].append(key)
        if L["host_id"] in labels_only_hosts:
            sd = root / "data" / "samples" / L["sample_id"]
            if (d / "netlist.v").exists() or (sd / "rtl.v").exists() or (root / "golden" / L["host_id"]).exists():
                fails["netlist or RTL shipped for a labels-only host"].append(key)
        else:
            nl = d / "netlist.v"
            if not nl.exists():
                fails["netlist missing"].append(key)
            elif sha256(nl) != L["netlists"]["trojan_sha256"]:
                fails["netlist hash mismatch"].append(key)
            g = root / "golden" / L["host_id"] / L["flow_id"] / "netlist.v"
            if not g.exists() or sha256(g) != L["netlists"]["golden_sha256"]:
                fails["golden missing or hash mismatch"].append(key)
            if not (root / "data" / "samples" / L["sample_id"] / "rtl.v").exists():
                fails["rtl missing"].append(key)
        same = L["netlists"]["trojan_sha256"] == L["netlists"]["golden_sha256"]
        if L["netlists"]["identical"] != same:
            fails["R14 identical flag disagrees with hashes"].append(key)
        t = recompute_tier(L)
        if t != L["tier"]:
            fails[f"R14 tier {L['tier']} but table gives {t}"].append(key)
        if L["tier"] == "functional":
            w = L["witness"]
            if not w["file"] or not (d / w["file"]).exists():
                fails["functional without witness file"].append(key)
            elif sha256(d / w["file"]) != w["sha256"]:
                fails["witness hash mismatch"].append(key)
            g = L["functional_grade"]
            res = {x["mode"]: x["result"] for x in w["replays"]}
            ok = {"x_init": res.get("x_init") == "diverged",
                  "reset_only": res.get("reset") == "diverged" and res.get("x_init") != "diverged",
                  "power_up_only": res.get("power_up") == "diverged" and w["source"] == "eq_free_counterexample"}.get(g)
            if not ok:
                fails[f"R14 grade {g} not supported by replays"].append(key)
        if L["tier"] in ("inert", "removed") and not L["netlists"]["identical"] and L["equivalence"]["bounded"]:
            fails["R15 bounded proof decides"].append(key)
    # Machine paths. A personal path anywhere fails. The container path /foss/... fails in label, index and witness
    # files; in Verilog it is only counted, because Yosys puts the source file name of an inlined function into
    # net names (\\:126$func$/foss/.../b13.v:169$1.$result) and renaming nets would change the netlists that were proved.
    personal, container = re.compile(rb"/Users/|/home/"), re.compile(rb"/foss/")
    verilog_with_container_path = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        data = p.read_bytes()
        if personal.search(data):
            fails["personal path in file"].append(str(p.relative_to(root)))
        if container.search(data):
            if p.suffix == ".v":
                verilog_with_container_path += 1
            else:
                fails["container path in non-Verilog file"].append(str(p.relative_to(root)))
    # manifest integrity
    listed = {f["path"]: f for f in man["files"]}
    for p in root.rglob("*"):
        if p.is_file() and p.name != "MANIFEST.json":
            rel = str(p.relative_to(root))
            if rel not in listed:
                fails["file not in manifest"].append(rel)
    for rel, f in listed.items():
        if not (root / rel).exists():
            fails["manifest entry without file"].append(rel)

    print(f"labels-only hosts: {len(labels_only_hosts)}")
    print(f"label records: {len(idx)}   samples: {len({x['sample_id'] for x in idx})}   flows: {sorted(flows)}")
    for k in sorted(tiers):
        print(f"  {k[0]:9s} {k[1]:10s} {k[2]:17s} {str(k[3]):18s} {tiers[k]}")
    print(f"note: {verilog_with_container_path} Verilog files have the container path inside Yosys net names (kept as proved)")
    if not fails:
        print("ALL CHECKS PASSED")
        return 0
    print("FAILED CHECKS:")
    for k, v in fails.items():
        print(f"  {k}: {len(v)}   e.g. {v[:3]}")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--twins"); ap.add_argument("--campaign"); ap.add_argument("--out")
    ap.add_argument("--labels-only-family", action="append", metavar="FAMILY",
                    help="like --labels-only, for the hosts of one family (e.g. ITC99); repeatable")
    ap.add_argument("--labels-only", action="store_true",
                    help="write labels, hashes and witnesses but no netlist or RTL (licence fallback, spec section 9)")
    ap.add_argument("--check", metavar="OUT", help="run the release checks on an exported tree")
    a = ap.parse_args()
    if a.check:
        return check(a.check)
    if not (a.twins and a.campaign and a.out):
        ap.error("--twins, --campaign and --out are required")
    return export(a)


if __name__ == "__main__":
    sys.exit(main())
