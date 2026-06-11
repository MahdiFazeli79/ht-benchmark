# Phase-2 pilot report

> SCOPE: hosts are toy self-authored modules (8-bit adder/mux/…). This pilot validates the PIPELINE and the COST MODEL, **not** insertion feasibility on realistic cores — synth-survival and insertion difficulty on a toy host do not generalize (a Trojan there can be folded away or trivially preserved in ways a real core won't).

- spent: $0.1884
- attempted: 12  accepted: 10  yield: 83%

## Taxonomy spread (accepted)
- always_on/None/degrade_performance: 1
- always_on/None/leak_information: 1
- triggered/combinational/degrade_performance: 4
- triggered/combinational/denial_of_service: 1
- triggered/combinational/leak_information: 1
- triggered/combinational/modify_functionality: 2

## Activation-proof method spread
- input_driven: 10

## Near-duplicate clusters: 1
- c490af0deb150aff: ['pilot_001_add8', 'pilot_002_add8']

## Trojan-only-signal reject rate: 100% (of 2 rejects) — high ⇒ self-referential witnesses

## Testbench-artifact spot-check (witnesses for manual review)
- pilot_001_add8: {'trigger': "a == 8'hA5 and b == 8'h5A (the rare exact input combination where a=0xA5, b=0x5A)", 'observable_effect': "sum outputs 9'h100 (i.e., 256) instead of the correct value 9'hFF (255), meaning the result is inflated by 1, degrading computation correctness"}
- pilot_002_add8: {'trigger': "a == 8'hA5 and b == 8'h5A (the rare exact 16-bit input match a=0xA5, b=0x5A)", 'observable_effect': "sum outputs 9'h100 (i.e., 256) instead of the correct 9'hFF (255), meaning the result is incremented by 1, degrading arithmetic correctness for this specific input combination"}
- pilot_003_add8: {'trigger': "a == 8'hAA and b == 8'h55 (simultaneously)", 'observable_effect': "clean sum would be 8'hAA + 8'h55 = 9'hFF (255), but the Trojan outputs 9'hFD (253) because bit 1 of the sum is flipped via XOR with 9'h002, corrupting the result and degrading computational correctness; additionally, the inserted mux logic on the critical path degrades timing performance"}
- pilot_004_mux2x8: {'trigger': "sel=1, a=8'hA5, b=8'h5A", 'observable_effect': "y outputs 8'h00 instead of the correct value 8'h5A (output driven to zero, degrading performance/correctness)"}
- pilot_005_add8: {'trigger': "a == 8'hA5 and b == 8'h5A", 'observable_effect': "sum outputs 9'h000 instead of the correct value 9'hFF (0xA5 + 0x5A = 0xFF)"}