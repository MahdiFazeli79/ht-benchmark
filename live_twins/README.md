# Live twins and free-start labels (24 November 2026)

Code behind `spec/NOTE-functional-tier-gauntlet-2026-11-24.md` and the v1.1 draft spec. Copied from the EDA research
workbench, where it runs inside the Docker container; the paths in the code are container paths.

| File | Workbench location | What it does |
|---|---|---|
| `trojan_gen.py` | `scripts/trojan_gen.py` | Host-population Trojan generator; `GEN_LIVE` makes the live twins |
| `lt.py` | `outputs/live_twins_20261124/lt.py` | Twin synthesis, eq_rst miter with counterexample, replay, tiers, free-start check (`equiv_free`) |
| `free_replay.py` | same directory | `power_up` replay of the eq_free counterexamples |
| `free_big5.py` | same directory | Free-start pass on b15, b17, b20, b21, b22 |
| `free_redo2.py` | same directory | Rerun of the two b17 Y_seq decoy checks after the status-parser fix |

Container paths: `/foss/designs/` is the workbench root; `lt.py` imports `wblib` and `trojan_lib` from
`/foss/designs/scripts` and reads the campaign from `/foss/designs/outputs/host_population_20261122_153549`.
Run with `/opt/research-venv/bin/python` inside the container. Result files (`rows_release.jsonl`,
`labels_release.jsonl`, `free*.jsonl`, `free_replay.jsonl`) stay in the workbench output directory.
