# Combinational scale batch — spec for review

The first corpus-building run. Combinational cells ride the degenerate apply-and-observe
path (one-cycle vectors, no drive, no parser heuristic), so they are durable under any
future prompt_v3 and need none of it. This batch also stands up the diversification
mechanism from `docs/diversification_decision.md`: over-generate-and-dedup, on the
critical path, because collapse is cell-dependent (add8, cmp8 collapse; mux2x8 does not).

**This is for review. The dedup-loop CODE and the paid RUN are both gated** — the run
is Tier-3, authorized in the run session as always.

## 0. The decision that gates the size (settle first)

The knob is **K = distinct accepted samples per cell** (distinct by the rename-robust
structural signature). K sets corpus size, cost, and how hard dedup has to work.

> **What is K, and what is the per-cell over-generation cap N (how many generations we
> pay for chasing K distinct before we stop and report a shortfall)?**

Proposal: **K = 4 distinct per cell, N_cap = 12 generations per cell.** Rationale: K=4
gives intra-cell variety without over-paying on the cells that collapse (where the 5th
distinct may not exist at temperature 1.0); N_cap = 3·K bounds the spend on a collapsing
cell and converts "couldn't hit K" into a reported per-cell shortfall (honest-scarcity
pattern), not an unbounded loop. Both are yours to set; everything below scales off them.

## 1. Combinational cell set (the taxonomy spread)

Five self-authored combinational hosts (add8, mux2x8, cmp8, shift8, alu8), spanning the
combinational-feasible taxonomy (R1–R3 checked at construction):

| trigger source | mechanism | payloads | hosts |
|---|---|---|---|
| internal | combinational | degrade_performance, modify_functionality, denial_of_service | add8, cmp8, alu8 |
| external | combinational | leak_information, modify_functionality | mux2x8, shift8 |
| (always_on) | — | leak_information, degrade_performance | add8, shift8 |

~10 distinct cells × K=4 ≈ **40 distinct samples** target. The exact cell list is a
`combinational_scale_specs()` enumeration (same shape as `batch2_specs`), drafted as
code once K/N are set.

## 2. Over-generate-and-dedup mechanism (on the critical path)

Per cell, the diversification loop:

1. Call `generate_sample` (the existing gauntlet-gated path) repeatedly.
2. Each accept's inserted-Trojan structural signature (`_structural_signature`, the same
   rename-robust key that read collapse) is the dedup key. Keep the FIRST accept of each
   signature; **discard structural duplicates** (they inflate the corpus and poison
   variant_group splits — the reason dedup is non-optional now).
3. Stop at K distinct accepts or N_cap generations, whichever first.
4. Emit per cell: `distinct` (≤K), `generated`, `accepted`, `discarded_dupes`, and the
   **discard rate** = discarded_dupes / accepted.

The discard rate is the load-bearing number (next section). The kept K samples are the
corpus; the discards are logged (count + signatures), not written to the corpus dir.

## 3. The escalation trigger (measured, not guessed)

The dedup-discard rate per cell is the exact input the diversification decision parked
for: **if a cell's discard rate is high (over-generation throws away most of what it
makes to hit K), a second generator is cheaper than the waste → multi-model insertion
moves from documented escalation to a build, for that cell.** Low discard rate ⇒
over-generate-and-dedup suffices forever. Per-cell discard rates become a reported
finding in the paper (the honest-scarcity pattern again).

## 4. Cost + caps

At the observed ~$0.013/sample, ~40 distinct with bounded over-generation on the
collapsing cells lands roughly **$1–2** (depends on the real discard rates, which is
partly what we are measuring). Proposed caps for the run (you set them in the session):
total $5, per_run $1, no yield-floor abort surprise on a 40+-sample run (raise
`min_attempts_before_floor` accordingly). Hosts stay toy/self-authored — the toy-host
scope disclosure (round-12) still applies; this batch validates the pipeline + the
diversification mechanism, not realistic-core insertion.

## 5. Code plan (after §0 is answered, gated for review)

1. `combinational_scale_specs()` — the cell enumeration (no-spend, CI-safe test).
2. A dedup-batch run mode — `run_dedup_batch(specs, out_dir, K, N_cap, ...)` wrapping
   `run_pilot`/`generate_sample`, with the per-cell distinct/discard accounting and the
   discard-rate metric in the report (mock-tested, no spend).
3. The regression posture is automatic: dedup only ADDS a keep/discard filter over the
   existing accept path; an accepted sample is still a gauntlet-passed sample.
4. Then the paid run — Tier-3, in the run session: key provenance, caps, the spec set,
   K/N, model id.

## Status

Spec drafted for review. K and N_cap (§0) gate the cell-list code and the dedup-loop
build; the run is the Tier-3 gate after that. Sequential lane stays parked (parser 5/5,
prompt_v3 deferred); combinational accepts here are durable under any later prompt_v3.
