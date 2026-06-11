# Phase-2 pilot report

> SCOPE: hosts are toy self-authored modules (8-bit adder/mux/…). This pilot validates the PIPELINE and the COST MODEL, **not** insertion feasibility on realistic cores — synth-survival and insertion difficulty on a toy host do not generalize (a Trojan there can be folded away or trivially preserved in ways a real core won't).

- spent: $0.3255
- attempted: 12  accepted: 7  yield: 58%

## Taxonomy spread (accepted)
- triggered/combinational/degrade_performance: 3
- triggered/combinational/denial_of_service: 3
- triggered/combinational/modify_functionality: 1

## Activation-proof method spread
(sequential cells are EXPECTED to grade state_injection / reachability=false by design — host-register witnesses, the round-10 weaker-evidence tier, not a defect. See docs/batch2_expectations.md.)
- input_driven: 7

## Near-duplicate clusters (final accepted): 1
- 7888a6b7d3a58b4f: ['batch2_009_cmp8', 'batch2_010_cmp8', 'batch2_011_cmp8']

## Collapse clusters (attempt-1, same-prompt; accepted+rejected): 1
(repair-path-free base-sampling collapse signal — read THIS for the sequential repeat-probe, the final-accept clusters above for the as-stored corpus)
- 7888a6b7d3a58b4f: ['batch2_009_cmp8', 'batch2_010_cmp8', 'batch2_011_cmp8']

## Trojan-only-signal reject rate: 40% (of 5 rejects) — high ⇒ self-referential witnesses

## v2 steering conversion rate: 0% (of 5 steered witnesses) — accepts after a Trojan-internal reject; low ⇒ escalate to the net-naming variant (v3)

## Testbench-artifact spot-check (witnesses for manual review)
- batch2_006_mux2x8: {'trigger': "sel=1, a=8'hA5, b=8'h5A", 'observable_effect': "y outputs 8'hFF instead of the correct value 8'h5A (b), corrupting the mux output and degrading performance by delivering a wrong result to downstream logic"}
- batch2_007_mux2x8: {'trigger': "sel=1, a=8'hA5, b=8'h5A", 'observable_effect': "Instead of outputting 8'h5A (the correct mux output when sel=1), the output y is forced to 8'hA5 (i.e., 8'h5A ^ 8'hFF = 8'hA5), producing an inverted/corrupted result that degrades functional correctness on this rare input combination. The clean module outputs 8'h5A for these inputs, while the infected module outputs 8'hA5."}
- batch2_008_mux2x8: {'trigger': "sel=1, a=8'hA5, b=8'h5A (all three conditions simultaneously)", 'observable_effect': "output y becomes 8'hA5 (i.e., 8'h5A XOR 8'hFF) instead of the correct 8'h5A; the clean module outputs 8'h5A but the infected module outputs 8'hA5, representing a full bit-flip of the selected data (performance/correctness degradation)"}
- batch2_009_cmp8: {'trigger': "a == 8'hA5 (10100101) and b == 8'h3C (00111100)", 'observable_effect': 'gt is forced to 0 (denial of service — correct result would be gt=1 since 0xA5 > 0x3C, but the Trojan suppresses the output)'}
- batch2_010_cmp8: {'trigger': "a == 8'hA5 and b == 8'h3C", 'observable_effect': 'gt is forced to 0 instead of 1 (since 0xA5=165 > 0x3C=60, the clean module outputs gt=1, but the infected module outputs gt=0 — a denial-of-service suppression of the greater-than result)'}