# Phase-1 Candidate List — Review (PRE-DOWNLOAD)

Reviewable artifact for task #28. **Nothing ingested.** Machine-readable list:
`phase1_candidates.yaml`. Read the four headline numbers first — they are where
this could be quietly wrong, and two of them are currently **failing**.

## The four numbers (read these first)

| # | Metric | Value | Verdict |
|---|---|---|---|
| 1 | **l-bin distinct `variant_group` (as-is)** | **11** | **FAIL vs ≥25 floor** |
| 2 | **Homogeneity** (RISC-V CPU + OpenTitan share) | **57% + 30% = 87%** | **RISK — "a RISC-V benchmark"** |
| 3 | Rejected-on-intake | 5 (ITC-99, ISCAS-85/89, OpenCores-LGPL, NEORV32) | as expected |
| 4 | **SystemVerilog → needs `sv2v`** | **57% of candidates** | **NEW Phase-1 dependency** |

The l+m promotable pool is only **19** distinct groups, so even promoting every
medium design and adding config variants, the **≥25 distinct-`variant_group`
floor is not reachable from this first-pass list**. Config variants raise the
sample count but NOT the distinct-group count, which is the floor — so they do
not fix #1.

## Three decisions this forces (before sourcing locks in)

**A. The ≥25-distinct-`variant_group` l-floor is the binding problem.** Permissive,
parseable, genuinely-large (>10k-node), independent designs are scarcer than the
plan assumed once copyleft (ITC-99, OpenCores) and VHDL (NEORV32) are excluded.
Options, in order of my preference:
  1. **Source harder before lowering the bar.** OpenTitan has ~30 IP blocks (many
     m–l) — I listed 7; the rest add distinct groups. Add permissive non-CPU
     large IP: DSP (FFT/FIR/CORDIC at large configs), comms MACs (Ethernet/USB),
     NoC routers, DDR/memory controllers — these also fix #2.
  2. **Promote large-m + count config variants for the sample count** (floor stays
     on distinct groups). Gets to ≥100 samples; does not by itself reach ≥25
     groups.
  3. **Lower the l-floor to ~15–20 distinct groups** if 1+2 fall short — but state
     it as a measured limit of permissive large IP, not a silent climb-down.

**B. `sv2v` is now a hard Phase-1 prerequisite (57% of the backbone).** Ibex, CVA6,
CV32E40P, all OpenTitan, VeeR are SystemVerilog; Pyverilog cannot parse them
directly. Add `sv2v` (MIT) to the normalization pass. **Risk:** sv2v may not
cleanly convert every OpenTitan block (packages, interfaces, complex generates);
some will still fail and shrink the usable set further. **Mitigation:** run an
sv2v→Pyverilog smoke test on CVA6 + 2 OpenTitan blocks NOW, before committing to
the SV-heavy backbone — if sv2v chokes, #1 and the whole l-bin plan change.

**C. Homogeneity (87% RISC-V/OpenTitan) makes the bounded OpenCores pass too
bounded.** A backbone that is almost all RISC-V cores + OpenTitan security IP
risks a model learning "RISC-V/OpenTitan-shaped = the distribution." The
diversity pass (ruling #3) should widen beyond OpenCores to DSP/comms/NoC/control
IP — the same designs that fix the l-floor (#1) also fix homogeneity. These are
the same action.

## R9 canaries (task #27 — measure here first)

Marked `r9_canary: true`: **cva6, openc910, veer_eh1, ot_otbn, rocket, cv32e40p,
ibex**. These are the deep-hierarchy large designs where HW2VEC's
flatten/underscore-mangle is most likely to alias names. Run the R9 collision
rate on these (post-sv2v) before sourcing the full l bin — chosen for depth +
SystemVerilog/packages + Chisel-gen naming (rocket), the three structures most
likely to trip R9.

## What is NOT in question

Licenses on the survivors are confirmed permissive (Apache-2.0 / Solderpad-2.1 /
ISC / MIT / BSD), except `e203` (unconfirmed → reject until its LICENSE is
checked). The rejected rows are shown in `phase1_candidates.yaml` as the audit
trail for the §2/§9 license-rigor paragraph.

## Recommendation

Don't approve a download yet — approve a **direction**. My read: do the sv2v
smoke test (B) and the OpenTitan-blocks + non-CPU-IP expansion (A.1 / C) as the
next pre-download step, re-tally the four numbers, and only then freeze the l-bin
target. If the expanded list still can't clear ~20 distinct l-groups, that is
itself a finding (permissive large IP is genuinely scarce) and the floor moves
with a stated rationale. The list is doing its job: it surfaced that the l-floor
and the SV dependency are the real risks, on paper, before a single git clone.
