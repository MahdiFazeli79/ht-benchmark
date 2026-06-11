# Batch 2 — expectations to state up front

Batch 2 is the second small paid pilot, gated exactly like the first (Tier-3:
key provenance, caps, spec set, model id, confirmed in the run session). Its job
is to answer three load-bearing questions under one batch, and to report two
numbers that decide the next versioned change. Writing this down now so the
batch-2 report reads as design, not surprise.

## The three questions the spec must cover

1. **Sequential-fix validation.** Sequential cells under prompt_v2 (the
   host-observable witness steering). Does the steering actually recover
   sequential yield? This is also the first real exercise of the
   `state_injection` grading branch on real model output.
2. **Collapse breadth.** Repeat-probes on 2-3 different cells (not just the one
   `add8` combo from pilot 1), to measure whether mode collapse is uniform across
   the taxonomy or concentrated in simple cells. This is what licenses the
   diversification-architecture decision (general prompt-seed variation vs.
   over-generate-and-dedup vs. multi-model insertion).
3. **Cost estimate.** One realistically-sized host, to turn the toy-host cost
   floor ($0.019/sample) into an estimate for real cores.

## Expected grade distribution — SUPERSEDED by drive-to-state

This section predicted that successful sequential samples would grade
`state_injection` / `reachability_established=false`, because the then-current
`parse_witness` forced host registers. That prediction was written before the
seqrecheck (c) run, which showed the forced-state proof MASKS host-register payloads
and rejects every sequential cell. The fix — drive-to-state (`docs/drive_to_state_
design.md`) — inverts the expectation: sequential triggers are now REACHED via inputs,
not forced, so successful sequential samples grade `input_driven` /
`reachability_established=true` (the stronger tier). `state_injection` is now the
exception, not the sequential norm. Kept here for provenance of the reasoning trail;
the live expectation lives in the drive-to-state doc.

## Two numbers the report already emits

- **v2 steering conversion rate** (`PilotReport.steering_conversion_rate`): of the
  witnesses the steering fired on, the fraction that converted to accepts. High =>
  general steering suffices forever; low => the net-naming steering variant is the
  justified v3. Decision input, measured not guessed.
- **Collapse clusters (attempt-1)** across the repeat-probe cells: the
  collapse-breadth signal. Read the ATTEMPT-1 clusters
  (`PilotReport.attempt1_collapse_clusters`), not the final-accept clusters, for
  the sequential cells 1-3: their triplicate is same-prompt only on attempt 1: once
  a sample rejects and the v2 steering fires, its accepted attempt-2 output carries
  its own repair history, so identical specs no longer share a prompt and final-
  accept clustering would read repair-path noise as base-sampling diversity.
  Attempt-1 outputs are same-prompt by construction (one retained intermediate per
  sample, pooled across accepted and rejected), so final-accept clusters measure the
  v2 fix and attempt-1 clusters measure collapse, without contaminating each other.
  Uniform clustering across cells => collapse is taxonomy-wide; clustering only on
  simple cells => cell-dependent, and the cheaper diversification answers may cover
  most of the corpus. The combinational repeat-probes (6-8, 9-11) accept on attempt
  1, so their final and attempt-1 clusters coincide.

## Proposed spec set (12 samples, for review)

`pilot.batch2_specs()` / `_BATCH2_CELLS`. All R1-R3 feasible at construction;
the two new hosts (`accum8`, `alu8`) verified to compile (iverilog -g2012) and
synthesize (yosys) before review.

| # | host | mechanism | payload | purpose |
|---|------|-----------|---------|---------|
| 1-3 | counter8 | sequential_counter | denial_of_service | seq-fix validation + collapse probe (the exact pilot-1 reject cell, 3× identical) |
| 4 | counter8 | sequential_fsm | modify_functionality | the other pilot-1 sequential reject |
| 5 | accum8 | sequential_counter | degrade_performance | second sequential host (not only counter8) |
| 6-8 | mux2x8 | combinational | degrade_performance | collapse-breadth probe cell #2 (3× identical) |
| 9-11 | cmp8 | combinational | denial_of_service | collapse-breadth probe cell #3 (3× identical) |
| 12 | alu8 | combinational | modify_functionality | cost-slope point (larger self-authored host) |

Proposed caps for the run (set in the run session, not here): same as pilot 1,
$10 total / $1 per-run / 0.20 yield floor over 10 armed at 8. alu8 costs more
per sample (bigger prompt); still well within the per-run cap.

## Status

Spec DRAFTED and mock-tested (no spend), awaiting review. The RUN is the Tier-3
gate, authorized only in the run session (key provenance, caps, spec set, model
id). Real-core cost point deferred to a separately-gated download.
