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

## Expected grade distribution (state this up front in the report)

Steered sequential witnesses express triggers via clean-module registers, which
`parse_witness` classifies as **forced state**. So successful sequential samples
should come back graded `activation_proof_method = state_injection` with
`reachability_established = false`. **This is not a regression.** It is the
weaker-evidence tier doing exactly what round 10 designed it to do: a forced-state
proof is honestly labeled as weaker than an input-driven one. The report should
say "sequential -> mostly state_injection, reachability=false, by design" before
showing the method spread, so the honest-but-weaker labels are read as design,
not defect.

## Two numbers the report already emits

- **v2 steering conversion rate** (`PilotReport.steering_conversion_rate`): of the
  witnesses the steering fired on, the fraction that converted to accepts. High =>
  general steering suffices forever; low => the net-naming steering variant is the
  justified v3. Decision input, measured not guessed.
- **Near-duplicate clusters** across the repeat-probe cells: the collapse-breadth
  signal. Uniform clustering across cells => collapse is taxonomy-wide; clustering
  only on simple cells => cell-dependent, and the cheaper diversification answers
  may cover most of the corpus.

## Status

Spec not yet drafted. The spec set is the next no-spend artifact (for review);
the RUN is the Tier-3 gate, authorized only in the run session.
