"""Resume the large-host run after the disk-full stop (24 Nov 2026): redo the failed b18 twins, then the free-start
pass for the six large hosts. Run inside the container: /opt/research-venv/bin/python resume_big.py"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lt", "/foss/designs/outputs/live_twins_20261124/lt.py")
lt = importlib.util.module_from_spec(spec); spec.loader.exec_module(lt)
R = lt.R
redo = []
pairs = [(i.split("__L")[1].split("_", 1)[0], i.split("__L")[1].split("_", 1)[1]) for i in redo]
# b18 dropped from the benchmark (decided 24 Nov 2026): no redo
HB = {"b20", "b21", "b22", "b15", "b17"}
rows = [json.loads(l) for l in open(R / "rows_big.jsonl")]
jobs = []
for r in rows:
    if r["host"] in HB and r.get("eq_rst", {}).get("status") == "proved":
        t = lt.LLC_twin(r["id"]) if r["flow"] == "LL" else str(R / r["flow"] / r["id"] / "nl.v")
        jobs.append(("twin", r["host"], r["flow"], r["id"], lt.golden_nl(r["host"], r["flow"]), t))
last = {}
for l in open(lt.HP / "eq_rst.jsonl"):
    x = json.loads(l); last[x["tag"]] = x
for x in last.values():
    if x["kind"] != "inst" or x["status"] != "proved" or x["host"] not in HB:
        continue
    fl, iid = x["tag"].split("/", 1)[1].split("__", 1)
    g, t = lt.campaign_nl(f"{x['host']}__golden", fl), lt.campaign_nl(iid, fl)
    if g and t:
        jobs.append(("decoy", x["host"], fl, iid, g, t))
for h in sorted(HB):
    for fl in lt.FLOWS:
        g, b = lt.campaign_nl(f"{h}__golden", fl), lt.campaign_nl(f"{h}__golden_b", fl)
        if g and b:
            jobs.append(("control", h, fl, f"{h}__golden_b", g, b))
print("free-start jobs:", len(jobs), flush=True)
(R / "free_big.jsonl").unlink(missing_ok=True)
lt.free_batch(jobs, "free_big.jsonl", 3)
print("done", flush=True)
