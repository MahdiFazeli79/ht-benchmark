# Phase-2 pilot report

> SCOPE: hosts are toy self-authored modules (8-bit adder/mux/…). This pilot validates the PIPELINE and the COST MODEL, **not** insertion feasibility on realistic cores — synth-survival and insertion difficulty on a toy host do not generalize (a Trojan there can be folded away or trivially preserved in ways a real core won't).

- spent: $0.6109
- attempted: 32  accepted: 32  yield: 100%

## Taxonomy spread (accepted)
- always_on/None/degrade_performance: 4
- always_on/None/leak_information: 4
- triggered/combinational/degrade_performance: 8
- triggered/combinational/denial_of_service: 5
- triggered/combinational/leak_information: 4
- triggered/combinational/modify_functionality: 7

## Activation-proof method spread
(under drive-to-state, sequential accepts grade input_driven + reachability_established=true — the trigger is REACHED via inputs, not forced — so state_injection is now the exception. See docs/drive_to_state_design.md.)
- input_driven: 32

## Near-duplicate clusters (final accepted): 1
- 131d717b0c4b6a1b: ['comb_005_alu8_d4', 'comb_006_alu8_d2']

## Collapse clusters (attempt-1, same-prompt; accepted+rejected): 0
(repair-path-free base-sampling collapse signal — read THIS for the sequential repeat-probe, the final-accept clusters above for the as-stored corpus)

## Trojan-only-signal reject rate: 0% (of 0 rejects) — high ⇒ self-referential witnesses

## v2 steering conversion rate: n/a (steering never fired) (of 0 steered witnesses) — accepts after a Trojan-internal reject; low ⇒ escalate to the net-naming variant (v3)

## Per-cell dedup (over-generate→keep K distinct; discard rate is the multi-model escalation input): overall 63%
- comb_001_add8: 4/4 distinct, 11 generated, 11 accepted, 7 discarded (rate 64%)
- comb_002_add8: 1/4 distinct, 12 generated, 12 accepted, 11 discarded (rate 92%)  ⚠ SHORTFALL
- comb_003_cmp8: 1/4 distinct, 12 generated, 12 accepted, 11 discarded (rate 92%)  ⚠ SHORTFALL
- comb_004_cmp8: 4/4 distinct, 4 generated, 4 accepted, 0 discarded (rate 0%)
- comb_005_alu8: 4/4 distinct, 5 generated, 5 accepted, 1 discarded (rate 20%)
- comb_006_alu8: 4/4 distinct, 5 generated, 5 accepted, 1 discarded (rate 20%)
- comb_007_mux2x8: 4/4 distinct, 5 generated, 5 accepted, 1 discarded (rate 20%)
- comb_008_mux2x8: 1/4 distinct, 12 generated, 12 accepted, 11 discarded (rate 92%)  ⚠ SHORTFALL
- comb_009_shift8: 1/4 distinct, 12 generated, 12 accepted, 11 discarded (rate 92%)  ⚠ SHORTFALL
- comb_010_add8: 4/4 distinct, 4 generated, 4 accepted, 0 discarded (rate 0%)
- comb_011_shift8: 4/4 distinct, 4 generated, 4 accepted, 0 discarded (rate 0%)

## Per-sample cost (USD)
- comb_001_add8_d1: $0.0049
- comb_001_add8_d2: $0.0059
- comb_001_add8_d3: $0.0056
- comb_001_add8_d4: $0.0055
- comb_002_add8_d1: $0.0045
- comb_003_cmp8_d1: $0.0047
- comb_004_cmp8_d1: $0.0098
- comb_004_cmp8_d2: $0.0057
- comb_004_cmp8_d3: $0.0056
- comb_004_cmp8_d4: $0.0059
- comb_005_alu8_d1: $0.0079
- comb_005_alu8_d2: $0.0281
- comb_005_alu8_d3: $0.0091
- comb_005_alu8_d4: $0.0231
- comb_006_alu8_d1: $0.0109
- comb_006_alu8_d2: $0.0111
- comb_006_alu8_d3: $0.0097
- comb_006_alu8_d4: $0.0082
- comb_007_mux2x8_d1: $0.0053
- comb_007_mux2x8_d2: $0.0057
- comb_007_mux2x8_d3: $0.0051
- comb_007_mux2x8_d4: $0.0087
- comb_008_mux2x8_d1: $0.0046
- comb_009_shift8_d1: $0.0044
- comb_010_add8_d1: $0.0134
- comb_010_add8_d2: $0.0107
- comb_010_add8_d3: $0.0309
- comb_010_add8_d4: $0.0417
- comb_011_shift8_d1: $0.0105
- comb_011_shift8_d2: $0.0116
- comb_011_shift8_d3: $0.0151
- comb_011_shift8_d4: $0.0114

## Testbench-artifact spot-check (witnesses for manual review)
- comb_001_add8_d1: {'trigger': "a == 8'hA5 and b == 8'h5A (the rare exact 16-bit input pattern where a=0xA5, b=0x5A)", 'observable_effect': "sum outputs 9'h100 (256) instead of the correct 9'hFF (255), i.e. the result is off by 1 (incremented by 1), degrading arithmetic correctness for this specific input combination"}
- comb_001_add8_d2: {'trigger': "a == 8'hA5 and b == 8'h5A", 'observable_effect': "The clean module produces sum = 8'hA5 + 8'h5A = 9'h0FF (255), but the infected module produces sum = 9'h0FE (254), because the Trojan clears bit 0 of the result, degrading the output value by 1."}
- comb_001_add8_d3: {'trigger': "a == 8'hA5 and b == 8'h5A (the rare exact two-byte match)", 'observable_effect': "instead of outputting the correct sum 8'hA5 + 8'h5A = 9'h0FF, the infected module outputs 9'h0FE (sum reduced by 1), degrading the addition result by one."}
- comb_001_add8_d4: {'trigger': "a == 8'hA5 and b == 8'h5A (the rare exact 16-bit input match a=0xA5, b=0x5A)", 'observable_effect': "Instead of the correct sum 0xFF (8'hA5 + 8'h5A = 9'h0FF), the output is (0xFF + 1) XOR 0x055 = 0x100 XOR 0x055 = 9'h155, which is an incorrect degraded result differing from the clean module's 9'h0FF."}
- comb_002_add8_d1: {'trigger': "a == 8'hA5 and b == 8'h5A (the unique complementary pair where a=0xA5, b=0x5A)", 'observable_effect': "sum outputs 9'h000 (zero) instead of the correct value 9'hFF (255); clean module produces 9'hFF"}