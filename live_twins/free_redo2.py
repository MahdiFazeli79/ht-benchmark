"""Rerun the two b17 Y_seq decoy free-start jobs that dprove left undecided (misread as different, 24 Nov 2026)."""
import importlib.util
spec = importlib.util.spec_from_file_location("lt", "/foss/designs/outputs/live_twins_20261124/lt.py")
lt = importlib.util.module_from_spec(spec); spec.loader.exec_module(lt)
R = lt.R
jobs = []
for iid in ("b17__T3_mem", "b17__T3_weak_xor"):
    g, t = lt.campaign_nl("b17__golden", "Y_seq"), lt.campaign_nl(iid, "Y_seq")
    jobs.append(("decoy", "b17", "Y_seq", iid, g, t))
(R / "free_redo2.jsonl").unlink(missing_ok=True)
lt.free_batch(jobs, "free_redo2.jsonl", 2)
print("done", flush=True)
