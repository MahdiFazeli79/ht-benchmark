# Phase-2 pilot report

> SCOPE: hosts are toy self-authored modules (8-bit adder/mux/…). This pilot validates the PIPELINE and the COST MODEL, **not** insertion feasibility on realistic cores — synth-survival and insertion difficulty on a toy host do not generalize (a Trojan there can be folded away or trivially preserved in ways a real core won't).

- spent: $0.2661
- attempted: 5  accepted: 0  yield: 0%

## Taxonomy spread (accepted)

## Activation-proof method spread
(sequential cells are EXPECTED to grade state_injection / reachability=false by design — host-register witnesses, the round-10 weaker-evidence tier, not a defect. See docs/batch2_expectations.md.)

## Near-duplicate clusters (final accepted): 0

## Collapse clusters (attempt-1, same-prompt; accepted+rejected): 1
(repair-path-free base-sampling collapse signal — read THIS for the sequential repeat-probe, the final-accept clusters above for the as-stored corpus)
- 631213decb65746a: ['seqrecheck_002_counter8', 'seqrecheck_003_counter8']

## Trojan-only-signal reject rate: 60% (of 5 rejects) — high ⇒ self-referential witnesses

## v2 steering conversion rate: 0% (of 5 steered witnesses) — accepts after a Trojan-internal reject; low ⇒ escalate to the net-naming variant (v3)

## Per-sample cost (USD)
- seqrecheck_001_counter8: $0.0513 (rejected)
- seqrecheck_002_counter8: $0.0459 (rejected)
- seqrecheck_003_counter8: $0.0519 (rejected)
- seqrecheck_004_counter8: $0.0636 (rejected)
- seqrecheck_005_accum8: $0.0533 (rejected)

## Testbench-artifact spot-check (witnesses for manual review)