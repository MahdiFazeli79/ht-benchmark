# FUNCTIONAL tier from the v1.0 gauntlet corpus (24 November 2026)

Companion to `DRAFT-flow-labels-v1.1-2026-11-23.md`, section 11, decision 9. Not committed.

## What was run

The v1.0 gauntlet corpus has 49 accepted samples: `pilot_out` (10), `comb_out` (32) and `batch2_out` (7). All are LLM insertions (claude-sonnet-4-6) into five self-written 8-bit hosts: add8 (14), mux2x8 (10), alu8 (9), cmp8 (9), shift8 (7). All 49 hosts and Trojans are combinational, with no clock and no flop. All 49 have `activation_proof_pass: true` with `input_driven`. Taxonomy: 39 triggered, 10 always-on.

Each sample's `clean.v` and `infected.v` went through LL (LibreLane 3.1.0.dev3 Classic, synthesis only), Y_sat and Y_seq, using the same scripts and sky130_fd_sc_hd library as the host-population campaign. Per (sample, flow):

1. Golden check: each netlist against its own RTL, SAT miter in Yosys.
2. Equivalence of the clean and infected netlists, SAT miter. The SAT solver is complete for combinational logic, so `proved` and `different` are exact. On `different`, the counterexample is saved as a primary-input vector.
3. Replay of that vector on both netlists with Icarus and the sky130 functional cell models, four-state, no initial values. A control replay runs the clean netlist against itself.
4. Replay of the v1.0 prose witness (`activation_witness.json`), parsed to an input vector.
5. Remnant probe (`Campaign.probe`) on both netlists.

Tier rule: FUNCTIONAL when the counterexample replay shows a known-value output difference and the control replay does not. The grade is `x_init` because the samples have no state.

Code and outputs: `~/eda-research-workbench/outputs/gauntlet_flows_20261124/` (`gf.py`, `rows.jsonl`, one directory per netlist, miter and replay). Run time 419 s.

## Result

| Flow | FUNCTIONAL | INERT | REMOVED | UNDECIDED |
|---|---|---|---|---|
| LL | 49 | 0 | 0 | 0 |
| Y_sat | 49 | 0 | 0 | 0 |
| Y_seq | 49 | 0 | 0 | 0 |

- All 294 golden checks proved.
- All 147 counterexample replays diverged on the netlists with known values; all 147 control replays matched.
- All 147 replays of the v1.0 prose witness diverged too. The parser named every input in all 49 witnesses, so no input was filled in.
- No sample changes tier across flows. The 10 always-on samples are FUNCTIONAL as well; their payloads change an output for some input.

## What this means for the benchmark

The tier is no longer empty: 147 (sample, flow) netlists now carry a FUNCTIONAL label with a witness replayed on the netlist itself. The result is the one the survival rule predicts. A trigger reachable from the inputs, with a payload that reaches an output, survives every correct flow, so these labels needed no knowledge of the flows.

These samples cannot serve as the positive class of the detector experiment (section 7 of the draft) as they stand. The decoys and clean netlists come from ITC'99 and ISCAS'89 hosts with sequential Trojans; the positives here come from five 8-bit combinational hosts. A detector could separate the two classes by host size, by the presence of flops or by module name, without looking at any Trojan. The `pilot_out` report already warns that results on these toy hosts do not carry over to real cores.

Positives for that experiment have to come from the same hosts as the decoys. That is the second option of decision 9: add reachable-trigger classes to the host-population generator (`trojan_gen.py`), for example a trigger compared against a primary-input word, or a counter clocked by an input and cleared by reset. The tier of each such insertion then comes from `eq_rst` plus a replay from reset.

## Gaps left open

1. Counterexample saving is done for combinational miters only. `equiv_abc` (the `eq_rst` path for sequential hosts) still decides `different` from the ABC log and keeps no trace; it needs `write_cex` and a conversion of the AIGER trace to a per-cycle input sequence.
2. The replay drives one input vector. A sequential replay needs a clock, a reset pulse, a per-cycle vector file and both modes of section 3.4 (`x_init`, `reset_only`).
3. The prose-witness parser is a regex over the `trigger` field. It worked for all 49 here, but it is no general converter (draft section 10, item 6).

---

# Live twins on the campaign hosts (24 November 2026, second run)

## What was built

`trojan_gen.GEN_LIVE` (in `~/eda-research-workbench/scripts/trojan_gen.py`; `GEN`, `PLAN06` and `SUBS` unchanged) makes one live twin of each of the 19 Study 2 sub-variants. A twin keeps the decoy's structure and output bit but changes what made the decoy inert: its trigger uses only primary-input bits or a counter cleared by reset (fires within 32 cycles), and its payload reaches the output bit. Examples: `contra_bit` loses the contradicting term; `seq_sat` triggers below the saturation value; `seq_fsm` triggers on a reachable state; the T6 registers drive the output.

Hosts: the 41 campaign hosts with fewer than 5,000 cells (s27 to b14). b15 and b17 to b22 are not run yet. 779 twins, three flows, 2,337 (twin, flow) netlists. Each netlist was compared with the campaign's golden netlist of the same flow:

1. eq_rst miter as in `Campaign.equiv_abc`, followed by `write_cex -a`. The AIGER counterexample is converted to one primary-input vector per cycle, with reset high in cycle 0 as in the miter.
2. Replay of that witness on both netlists in the two modes of spec section 3.4: `reset` (flops without an init value start at 0) and `x_init` (no init values). The model is each netlist flattened with the Liberty cell functions, with the miter's own preprocessing, simulated in Icarus.
3. A control replay of the golden netlist against itself with the same witness.
4. Remnant probe against golden.

Code and outputs: `~/eda-research-workbench/outputs/live_twins_20261124/` (`lt.py`, `instances.jsonl`, `rows_v2.jsonl`). Synthesis and proofs took about 30 minutes, the corrected replays 7 minutes.

## Result

| Flow | FUNCTIONAL x_init | FUNCTIONAL reset_only | INERT | REMOVED | UNDECIDED |
|---|---|---|---|---|---|
| LL | 580 | 131 | 68 | 0 | 0 |
| Y_sat | 579 | 132 | 68 | 0 | 0 |
| Y_seq | 592 | 119 | 0 | 68 | 0 |

- ABC `dprove` decided all 2,337 netlists: 2,133 `different` and 204 `proved`. No PDR run was needed and none timed out.
- Every `different` result has a counterexample that diverged on the netlists in `reset` mode. Every control replay matched. No CONFLICT.
- All `reset_only` rows show `x_blocked` under `x_init`: the diverging output bit is X when the flops start unknown. They are the twins whose payload register has no reset (T3 chain, weak_xor, weak_mux and reg; T6 counter, johnson and ring without reset).
- The same 68 twins are INERT under LL and Y_sat and REMOVED under Y_seq. 17 twins keep the FUNCTIONAL tier but change grade between flows; in 14 of them Y_seq gives `x_init` where LL and Y_sat give `reset_only`.

## Two findings that change the plan

1. The 68 inert twins are not all live by design. 45 come from a generator fault: in T3 reg, mem and weak_mux the payload's bit 0 depends on the trigger's own input bit 0. When the trigger fixes that input bit (a comparator key bit, or an AND term), bit 0 never changes. The first fix (XOR with 1) only moved the dead case from a fixed 0 to a fixed 1. The proof labels these twins correctly as inert, but they are not the positives intended. Fix: make bit 0 toggle on every trigger independently of the data.
2. The other 23 are T6 LFSRs without reset. The eq_rst miter starts every flop without a reset at 0, and an LFSR at 0 stays at 0, so the proof says INERT. On silicon the register powers up in an unknown state, almost always non-zero, and then the LFSR runs and drives the output. INERT is therefore a label under the miter's zero-start assumption, not under every power-up state. The same assumption is behind every INERT label on a netlist with a flop that has no reset, including the campaign's decoys. The spec has to state this, or the check has to give such flops a free initial value (write_aiger without `-zinit` for those latches) and record the result.

## What the benchmark gains

- 2,133 FUNCTIONAL (twin, flow) netlists, 711 per flow, on the same 41 hosts as the decoys, each with a witness replayed on the netlist. This is the positive class the detector experiment needs.
- 382 `reset_only` netlists (18% of the positives), which measure the X-init question of spec section 7.1 directly: these positives fire from the reset state but not from an unknown power-up state.
- Flow-dependent labels with both tier changes (INERT to REMOVED) and grade changes (`reset_only` to `x_init`).

---

# Both fixes applied (24 November 2026, third pass)

## 1. Generator fault

In the T3 twins, bit 0 of the payload register now toggles on every trigger, whatever the data (`{trj_pay[p-1:1] ^ trj_data[p-1:1], ~trj_pay[0]}`), and every word written to the T3 mem twin has bit 0 set. The six T3 sub-variants that use the payload register (reg, mem, chain, weak_mux, weak_xor, weak_dupreg) were regenerated and rerun on the 41 hosts: 246 twins, 738 netlists. All 738 are FUNCTIONAL; none is INERT, UNDECIDED or CONFLICT. Merged rows: `rows_v3.jsonl`.

## 2. Free-start check

`lt.equiv_free` builds the same miter as eq_rst with two changes: no flop gets an initial value except the wrapper's `eqv_started` (Yosys `write_aiger -zinit` gives every other flop a free first-cycle value), and both sides' outputs are masked in cycle 0, so they are compared from the first clock edge after the forced reset. Property: after one reset cycle, from every power-up state, the outputs agree forever.

Checks of the check:
- Golden against golden_b, all 41 hosts and three flows: 123 of 123 proved. All host flops are therefore determined after one reset cycle, so a difference can only come from a flop without a reset.
- The no-reset LFSR twins, INERT under eq_rst: `different` from free start in LL and Y_sat, from frame 1.

Results on every netlist that eq_rst proved on the 41 hosts:

| Netlists | Proved from free start | Different from free start |
|---|---|---|
| Campaign decoys (all flows) | 2,101 | 0 |
| Twins | 23 | 46 |

- No decoy label on these 41 hosts depends on the zero-start assumption. In LL and Y_sat no decoy miter keeps a free flop at all: the decoys' flops without reset do not reach an output, and the miter drops them.
- The 46 different twins are the 23 no-reset LFSRs under LL and Y_sat. The 23 proved ones are the same LFSRs under Y_seq, where ABC `scorr` removed the LFSR during synthesis. `scorr` itself assumes a zero start, so the Y_seq netlist no longer contains the Trojan that the RTL would have on silicon. REMOVED is the correct label for that netlist.

## Final twin labels

| Flow | FUNCTIONAL x_init | FUNCTIONAL reset_only | Zero-start INERT, free-start different | REMOVED |
|---|---|---|---|---|
| LL | 613 | 143 | 23 | 0 |
| Y_sat | 612 | 144 | 23 | 0 |
| Y_seq | 606 | 150 | 0 | 23 |

## Spec decisions this raises

1. The tier of the 46 netlists that are INERT from reset but different from some power-up state. Options: FUNCTIONAL with a new grade `power_up_only` (the counterexample gives the initial state, so the evidence is constructive), or UNDECIDED with a flag. A replay cannot show it, because four-state simulation from X keeps the LFSR at X.
2. Make the free-start proof a condition of INERT and REMOVED(no_remnant_proved) in section 3.5. On these hosts it changes no decoy label and costs one extra dprove call per netlist.
3. Record in the Y_seq flow description that `scorr` assumes a zero start, so a Y_seq netlist can lose a Trojan that would fire on silicon.

Not done: hosts b15 and b17 to b22, and replaying the free-start counterexamples (needs mapping the AIGER initial values back to netlist flops).

## Decision (24 November 2026)

Mahdi decided decision 1 above: the 46 netlists are FUNCTIONAL with grade `power_up_only`. Decisions 2 and 3 are written into the v1.1 draft together with it (sections 3.2a, 3.4, 3.5, the schema sketch, R14, gaps 1, 2 and 5, open decisions 3 and 9). Relabelled rows: `rows_v4.jsonl`.

| Flow | FUNCTIONAL x_init | FUNCTIONAL reset_only | FUNCTIONAL power_up_only | REMOVED |
|---|---|---|---|---|
| LL | 613 | 143 | 23 | 0 |
| Y_sat | 612 | 144 | 23 | 0 |
| Y_seq | 606 | 150 | 0 | 23 |

---

# Large hosts and the release host list (24 November 2026, fourth pass)

## Hosts

Mahdi decided to drop b18 from the release for every flow, decoys and twins alike (spec section 6.2). The release has 46 hosts: the 41 small hosts above plus b15, b17, b20, b21 and b22. The 12 b18 twins already labelled (36 netlists, all FUNCTIONAL) stay on disk outside the release.

## Twins on the five large hosts

95 twins, 285 netlists, same pipeline as on the small hosts (`rows_big_v2.jsonl`). The free-start pass ran on every netlist that eq_rst proved, plus the decoys and controls of these hosts (`free_big.jsonl`, 302 jobs).

| Flow | FUNCTIONAL x_init | FUNCTIONAL reset_only | FUNCTIONAL power_up_only | REMOVED |
|---|---|---|---|---|
| LL | 72 | 20 | 3 | 0 |
| Y_sat | 72 | 20 | 3 | 0 |
| Y_seq | 72 | 20 | 0 | 3 |

The three twins inert from reset are the no-reset LFSRs on b17, b21 and b22. They are different from free start under LL and Y_sat and proved under Y_seq, the same pattern as on the small hosts.

## Free-start checks, all 46 hosts

| Netlists | Proved | Different | Undecided |
|---|---|---|---|
| Controls (golden against golden_b) | 138 | 0 | 0 |
| Campaign decoys | 2,377 | 0 | 2 |
| Twins proved by eq_rst | 26 | 52 | 0 |

The two undecided decoys are b17 `T3_mem` and `T3_weak_xor` under Y_seq. dprove timed out after 60 s and PDR after 600 s; their miters keep about 1,170 free flops. Under section 3.5 of the draft they are UNDECIDED with the flag `free_start_undecided`. b17 under Y_seq already carries `golden_check_undecided` from the campaign.

A parser fault first recorded these two as `different`: on a timeout ABC prints "Counter-example is not available", and the status regex matched "Counter-example". The fault is fixed in both `equiv_cex` and `equiv_free` of `lt.py`. No other row was affected: every other `different` free-start result has a counterexample file and a frame, and every eq_rst `different` result has a replay that diverged. The misparsed file is kept as `free_big.misparsed.jsonl`.

## Release twin labels (46 hosts, 874 twins per flow)

Merged rows: `rows_release.jsonl` (`rows_v4.jsonl` plus `rows_big_v2.jsonl`).

| Flow | FUNCTIONAL x_init | FUNCTIONAL reset_only | FUNCTIONAL power_up_only | REMOVED |
|---|---|---|---|---|
| LL | 685 | 163 | 26 | 0 |
| Y_sat | 684 | 164 | 26 | 0 |
| Y_seq | 678 | 170 | 0 | 26 |

Not done: the decoy labels of the release (2,379 free-start checks above) are not yet merged into one release file with the twins, and the free-start counterexamples are still not replayed.

## Release decoy labels (46 hosts, 874 decoys per flow)

Labels from the section 3.5 table: identical and remnant from the campaign (`per_instance_flow_rst.csv`; `survived` read as remnant `trojan`, `removed-perturbed` as `none`, `scorr-host-perturbation` as `host`), eq_rst from `eq_rst.jsonl`, eq_free from `free.jsonl` and `free_big.jsonl`. Rows: `decoys_release.jsonl`; twins and decoys together: `labels_release.jsonl` (5,244 netlists).

| Flow | REMOVED identical | REMOVED no_remnant_proved | INERT | HOST_PERTURBATION | UNDECIDED |
|---|---|---|---|---|---|
| LL | 187 | 549 | 138 | 0 | 0 |
| Y_sat | 15 | 767 | 92 | 0 | 0 |
| Y_seq | 35 | 782 | 46 | 9 | 2 |

No decoy is FUNCTIONAL in any flow. All non-REMOVED, non-INERT rows are on b17 under Y_seq and carry `golden_check_undecided`.

Open point for Mahdi: the spec contradicts itself on b17 `T3_mem` under Y_seq. Its campaign remnant is `host` and eq_rst is proved, but eq_free is undecided. The 3.5 table row for eq_free undecided gives UNDECIDED (used here), while the paragraph under the table says all ten b17 Y_seq netlists are HOST_PERTURBATION regardless. The other undecided one, `T3_weak_xor`, has remnant `none` and is UNDECIDED under either reading.

## Independent audit of lt.py (Antigravity, read-only)

The audit, with each finding checked against the code and the run artefacts, changed no label:

1. Status parsing: the case-insensitive `cex` alternative matched the command line that ABC echoes at the top of every log (`write_cex`), so any log that was neither proved nor undecided would have read as `different`. All 5,276 dprove logs were checked: none reached that branch without a real disproof. Fixed: `different` now needs "not equivalent" or "was asserted in frame" and a counterexample file written by this run (stale files are deleted before each run).
2. Replay: a failed or timed-out simulation read as `no_divergence`. All 497 `reset_only` rows are `x_blocked` under `x_init` and all 5,088 control replays ran, so no grade came from a failure. Fixed: such a run is now `error`, and `x_blocked` is set only over a real `no_divergence`.
3. Remnant: twins count a remnant when flops, constant cells or pass-through cells increase, not logic cells. The campaign uses the same rule for the decoys (`removed-perturbed` versus `survived`), so the two classes agree. It is coarser than the trojan/host/unattributed attribution in section 3.5; the 26 Y_seq LFSR twins labelled REMOVED(no_remnant_proved) have logic-cell deltas from -12 to +59.
4. No netlist carries `init` attributes, so the free-start miter leaves every flop free as intended.

The replay of the 52 free-start counterexamples is not done. A Codex attempt stopped on its content filter before running anything.

## Power-up replay of the free-start counterexamples

`free_replay.py` (next to `lt.py`) replays the eq_free counterexample of each of the 52 `power_up_only` netlists (26 per flow in LL and Y_sat) on the netlists. The `write_aiger -zinit` map has one `init <input> 0 <net>` line per flop without an init value; the value of that input in frame 0 of the witness is the flop's power-up value. The replay sets it on the matching `<cell>.IQ` register of the x_init model at time 0 and drives the witness inputs, with reset in cycle 0.

The miters have more init inputs than named ones (on s208_1 LL, 24 against 8). The unnamed ones start host flops whose state wires are private after flatten. All of them have a reset, which the witness asserts in cycle 0, so the replay leaves them X.

| Check | Result (52 netlists) |
|---|---|
| Named init inputs mapped to a model register | 52 (8, 16 or 32 per netlist, none left over) |
| Replay with the power-up values | 52 diverged, all at frame 1, the frame dprove reported |
| Control, golden against golden with the same values | 52 no divergence |
| Same witness, flops left X | 52 `x_blocked` |

The last row shows that the power-up state, not the inputs, makes these netlists fire, and that four-state simulation from X cannot show it. The spec now calls this the `power_up` replay (sections 3.4 and 10, item 5; the R14 rule for `power_up_only` requires it). The result is stored as `free_replay` in the 52 rows of `rows_release.jsonl` and `labels_release.jsonl`.
