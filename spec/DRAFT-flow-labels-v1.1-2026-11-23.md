# DRAFT: TROVE schema v1.1 amendment, flow-specific post-synthesis labels

Status: DRAFT, 23 November 2026. Not frozen, not reviewed, not committed.
Extends: `SCHEMA_SPEC_v1.0.md` (frozen 10 June 2026, amended in rounds 8 to 12). Nothing in v1.0 is edited. Every addition below is optional for existing samples, the same freeze-the-field-before-the-data rule as rounds 8, 10, 11 and 12.
PROVISIONAL: everything that compares this scheme with SeqCube-HT (Xu et al., Cybersecurity 2026) or Qin et al. (ICCNEA 2026) rests on their abstracts only. Those parts carry the tag PROVISIONAL and must be checked against the full texts before any of it reaches a paper.

Inputs this draft was written from:
- `experiments/trojan_paper_2026-11-21/benchmark-differentiation-2026-11-23.md` (novelty check, 8 neighbours, 3 risks).
- `experiments/trojan_paper_2026-11-21/RESULTS_host_population.md` and `per_instance_flow_rst.csv`, `eq_rst.jsonl`, `e1_results.csv`, `e1b_results.csv` in `~/eda-research-workbench/outputs/host_population_20261122_153549/`.
- `~/eda-research-workbench/scripts/trojan_lib.py` (`equiv_abc`, `probe`) for what the checks actually do.
- `ht-bench/tools/htbench/gauntlet.py` (`activation_proof`) for the v1.0 witness.
- `ht-bench/docs/LESSON-2026-07-05-bounded-negative-is-not-soundness.md`.

---

## 0. The rule this amendment adds

A post-synthesis label belongs to one netlist, and a netlist belongs to one sample and one flow. The label is a property of the pair (sample, flow_id), where flow_id fixes the tool versions, the script and the cell library. The same sample may be FUNCTIONAL under one flow and REMOVED under another; the host-population campaign shows exactly this (the seq_fsm trigger survives LL and Y_sat on all 47 hosts and is removed by Y_seq on all 47).

Two consequences, stated as rules in section 5:
- No label is ever claimed across flows. There is no "post-synthesis label" without a flow_id, and no field aggregates over flows.
- Changing any tool version, the flow script or the cell library makes a new flow_id. Old labels are not carried over.

This is a fifth inversion in the sense of v1.0's opening list: v1.0 stores the RTL insertion as the truth and derives graph views; v1.1 stores per-flow evidence as the truth and derives every binary detector label at load (section 8.3).

---

## 1. Terms

- Golden netlist (of host H under flow F): the clean RTL of H through F.
- Trojan netlist: the infected RTL of a sample through F.
- Reference flow: the flow every other flow's golden is checked against. Currently LL.
- Remnant: cells in the Trojan netlist that the golden netlist of the same flow does not have and that are attributed to the Trojan (section 3.3).
- Evidence kinds. Every check in section 3 has one of five kinds, and the kind limits what the check can decide:

| Kind | What a positive result means | What a negative result means |
|---|---|---|
| exact | the stated fact holds (e.g. byte identity) | the fact does not hold |
| proof (unbounded) | holds for every input sequence from the stated initial state | a counterexample exists from that state |
| constructive | one concrete trace shows the behaviour; holds as a fact about the circuit | nothing; absence of a trace is not evidence |
| bounded | nothing beyond the bound | solver or simulator reach only, never circuit behaviour |
| heuristic | a structural indication, not a behavioural fact | a structural indication, not a behavioural fact |

The bounded row is Mahdi's rule from the 5 July 2026 lesson: a bounded negative ("no divergence in N cycles", "BMC found nothing within B frames", "proof timed out") is a statement about the tool's reach. It never sets INERT or REMOVED.

---

## 2. Tiers

One tier per (sample, flow_id). Five values, closed vocabulary, no `other`.

| Tier | Meaning | Minimum evidence |
|---|---|---|
| FUNCTIONAL | The Trojan in this netlist can fire: an input sequence makes the Trojan netlist's outputs differ from the golden netlist's. | A replayed witness that shows a known-value output divergence on the netlist itself (constructive), or, for grade `power_up_only`, a free-start counterexample (section 3.2a). Sub-grade `x_init`, `reset_only` or `power_up_only`, section 3.4. |
| INERT | Trojan cells remain in the netlist, but the netlist is proved equivalent to the golden netlist from reset. A decoy: it looks like a Trojan and cannot act like one from reset. | Equivalence proved (proof) and remnant attributed to the Trojan (heuristic, section 3.3). |
| REMOVED | The flow deleted the Trojan. | Either the netlist is byte-identical to the golden netlist (exact), or there is no remnant (heuristic) and equivalence is proved (proof). Sub-reason `identical` or `no_remnant_proved`. |
| UNDECIDED | The evidence does not separate the tiers above. | The equivalence check timed out or failed and no witness diverged. Timeout, engine and bound recorded. |
| HOST_PERTURBATION | The netlist differs from golden, but the difference is attributed to the flow treating host logic differently, not to Trojan logic. Excluded from survival counts and from every detector view. | Remnant attributed to host cells, plus a comparison flow in which the same sample is REMOVED with no remnant. Cause recorded (currently only `scorr_merge`). |

Two notes that the tier names hide:

1. INERT and REMOVED(no_remnant_proved) have the same behaviour from reset. Both are proved equivalent to golden. They differ only in the remnant test, which is a structural heuristic. A detector view that treats INERT as positive (section 8.3, view `present`) therefore depends on that heuristic, and any result reported under it must say so.
2. INERT means inert from reset, under the miter's initial state (section 3.2: reset forced in cycle 0, every flop without reset starting at 0). A Trojan that only fires from a power-up state the reset does not reach would be labelled INERT by this rule. Section 3.2 records the initial-state policy with each proof so that a stronger, free-initial-state proof can be added later without relabelling.

A host that fails the eligibility rule of section 6 gets no tier for that flow at all; its rows stay in the raw campaign data and are absent from the benchmark.

---

## 3. How each tier is decided

### 3.1 Byte identity (exact)

Compare the Trojan netlist with the golden netlist of the same flow, after the flow's own output step and before any post-processing. Identical bytes give REMOVED(identical) and stop the procedure. The campaign records this as `identical` in `per_instance_flow_rst.csv`.

### 3.2 Equivalence from reset, `eq_rst` (proof when it decides)

As implemented in `trojan_lib.equiv_abc` with `clk` and `rst` given:
- Both netlists are wrapped so that the reset input is forced active in the first clock cycle (`rst | ~eqv_started`).
- Yosys: `flatten; setundef -init -zero; async2sync; techmap; opt -fast`, miter, `aigmap`, `write_aiger -zinit`. Every flop starts at 0; flops with a reset then take their reset value in cycle 0.
- ABC runs `dprove`; if that does not decide, `pdr -T <timeout>`. Status is `proved`, `different` or `undecided` (timeout or no verdict), or `error` when the miter could not be built.
- Timeout in the campaign: 600 s per engine.

What the outcomes mean:
- `proved` is an unbounded proof of equivalence for every input sequence from the stated initial state. Kind: proof.
- `different` means ABC reported a counterexample. Kind: proof of non-equivalence. The counterexample is saved (`write_cex -a`) and converted to one primary-input vector per cycle; `different` alone does not set FUNCTIONAL, the witness must be replayed (section 3.4). The campaign code (`trojan_lib.equiv_abc`) still keeps no trace; the prototype that does is `lt.equiv_cex` (section 10, item 1).
- `undecided` and `error` are bounded results. They set UNDECIDED unless a replayed witness diverges.

Initial-state policy is part of the record (`equivalence.init`, section 4). The campaign value is `reset_cycle0_zero_uninit`.

### 3.2a Free-start equivalence, `eq_free` (proof when it decides)

eq_rst starts every flop without a reset at 0. A Trojan register without a reset can then stay in a state that never fires (a no-reset LFSR at 0 stays at 0), and eq_rst proves the netlists equivalent although on silicon the register powers up in an unknown state.

`eq_free` builds the same miter with two changes: no flop has an initial value except the wrapper's `eqv_started` (Yosys `write_aiger -zinit` gives each of the others a free first-cycle value), and both sides' outputs are masked in cycle 0, so they are compared from the first clock edge after the forced reset. `proved` means: after one reset cycle, from every power-up state, the outputs agree forever. `different` comes with a counterexample that fixes the initial values of the free flops and the inputs per cycle.

Calibration (24 November 2026, 41 hosts): golden against golden_b proved for all 123 (host, flow) pairs, so every host flop is fixed after one reset cycle and a difference can only come from a flop without a reset. Prototype: `lt.equiv_free`.

Calibration already done (RESULTS file): negative controls on b01, b06, s27 and s298 (a flop reset to 1, XORed into an output bit) are reported `different`; the earlier miter faults could only produce false `different`, never false `proved`.

### 3.3 Remnant classification (heuristic)

As implemented in `trojan_lib.probe`, the campaign counts, for the Trojan netlist against the golden netlist of the same flow: logic cells, area, flops, confirmed constant drivers and confirmed pass-through cells (constants and pass-throughs found by random simulation with 4,096 patterns and confirmed exactly for small cones). The current outcome rule is: a remnant exists when the netlist has extra flops, constant drivers or pass-through cells.

v1.1 keeps that rule as the evidence level `delta_only` and adds two stronger levels, so the record says which one was used:

| Evidence level | Test | Available today |
|---|---|---|
| `delta_only` | extra flops, constant drivers or pass-through cells against golden | yes, all three flows |
| `named` | cells or nets carrying the Trojan's RTL names survive in the netlist | LL and Y_sat partly; Y_seq renames all nets, so never |
| `fingerprint` | v1.0 §7 `structural_fingerprint` diff maps the extra cells to the Trojan's cone | no; needs the §7 netlist labeller run per flow |

Attribution values: `none`, `trojan`, `host`, `unattributed`. The cell delta is recorded but does not by itself create a remnant: under LL the removed-perturbed netlists range from 337 cells fewer to 327 cells more than golden with no remnant.

### 3.4 Witness replay (constructive when it diverges, bounded when it does not)

A witness is a sequence of primary-input vectors, one per clock cycle, stored as a file. It must not refer to internal signals: after synthesis, RTL names may be gone, so a v1.0 gauntlet witness (a drive-to-state reach predicate on a host register) is converted to the input sequence the gauntlet actually drove.

Witness sources:
- the counterexample of an `eq_rst` result `different` (needs `write_cex`, section 10 item 1); this witness starts from the miter's initial state;
- the v1.0 gauntlet's recorded input sequence for samples with `activation_proof_pass: true` (RTL simulation, from reset).

Two replay modes, both on the gate-level Trojan netlist and the golden netlist of the same flow, in a four-state simulator with the cell library's functional models:

| Mode | Initial state | Pass condition |
|---|---|---|
| `reset` | the `eq_rst` initial state: every flop at 0, reset forced in cycle 0 | some output bit is known (0 or 1) in both netlists and differs |
| `x_init` | every flop X; no `initial` values, no init attributes; the witness's own reset pulses applied as given | same: known in both and differs |

Result values per mode: `diverged`, `no_divergence`, `x_blocked` (the output that diverges under `reset` is X under `x_init`), `not_run`.

What a pass means. A `reset` pass shows the Trojan can fire from the reset state. An `x_init` pass, with X-pessimistic cell models, shows it fires from every power-up state, because four-state simulation over-approximates every concrete start. The X-pessimism of the sky130 functional models has not been checked; until it is, an `x_init` pass is recorded with `x_model_checked: false` (section 10 item 3).

What a fail means. `no_divergence` and `x_blocked` are bounded (cycle count) and say nothing about the circuit. They never set INERT or REMOVED.

FUNCTIONAL sub-grade: `x_init` when the `x_init` replay passes; `reset_only` when only the `reset` replay passes; `power_up_only` when eq_rst is `proved` and eq_free is `different` (decided by Mahdi, 24 November 2026). A `power_up_only` netlist cannot fire from the reset state, but fires from at least one power-up state, with no attacker action. Its evidence is the eq_free counterexample, which fixes the initial state. The `reset` and `x_init` replays cannot show it, because a four-state simulation from X keeps such a register at X. A third replay, `power_up`, starts each flop named in the counterexample from its power-up value and leaves the other flops X (all of them have a reset, which the witness asserts in cycle 0); a pass is a known-value divergence at frame 1 or later, with a golden-against-golden control that does not diverge. This is the field the SeqCube comparison needs (section 7.1).

### 3.5 Decision table

Apply after host eligibility (section 6) holds for (host, flow).

| identical | eq_rst | remnant | replay (any mode) | Tier |
|---|---|---|---|---|
| yes | not run | n/a | n/a | REMOVED(identical) |
| no | any | any | diverged | FUNCTIONAL (sub-grade per 3.4), unless eq_rst = proved: then CONFLICT |
| no | proved, eq_free different | any | not diverged | FUNCTIONAL(power_up_only) |
| no | proved, eq_free undecided or error | any | not diverged | UNDECIDED, flagged `free_start_undecided` |
| no | proved, eq_free proved | none | not diverged | REMOVED(no_remnant_proved) |
| no | proved, eq_free proved | trojan | not diverged | INERT |
| no | proved | host | not diverged | HOST_PERTURBATION if the comparison-flow condition holds, else UNDECIDED |
| no | proved | unattributed | not diverged | UNDECIDED |
| no | different | any | not run or not diverged | UNDECIDED, flagged `functional_candidate` |
| no | undecided or error | trojan or none | not diverged | UNDECIDED |
| no | undecided or error | host | not diverged | HOST_PERTURBATION if the comparison-flow condition holds, else UNDECIDED |

CONFLICT: a diverging `reset` replay together with a `proved` equivalence from the same initial state is impossible unless a tool or the test setup is wrong. The validator fails the sample and it stays out of every release until the cause is found. A diverging `x_init` replay with a `proved` result is possible only if the witness never asserts reset; the same rule applies, because the case needs a human look.

HOST_PERTURBATION comparison-flow condition: there is a flow F' registered in the same release in which the same sample is REMOVED with remnant `none`, and the remnant under F lies in cells attributed to the host. The campaign's ten b17 Y_seq netlists meet this with F' = Y_sat; four are proved under eq_rst and six undecided. Nine of them are HOST_PERTURBATION. The tenth, `T3_mem`, is proved under eq_rst but its eq_free proof is undecided (PDR, 600 s), so the eq_free row applies first: it is UNDECIDED with `free_start_undecided` (decided by Mahdi, 24 November 2026). Rows of the table are applied in order and the first matching row decides.

---

## 4. Label record schema

One file per (sample, flow): `data/samples/<sample_id>/flow_labels/<flow_id>/label.json`. The same directory holds that flow's `netlist.v` (if redistribution is allowed, section 9), `labels_netlist.json` (v1.0 §7 schema, core cells of this flow's netlist) and the witness files.

Schema `spec/schemas/flow_label.schema.json`, draft 2020-12 (sketch; the `$defs` for enums are written out here and would move to `taxonomy.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ht-bench/schemas/flow_label.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version","sample_id","flow_id","host_id","tier","netlists","equivalence","remnant","delta","witness","provenance"],
  "properties": {
    "schema_version": { "const": "1.1-draft" },
    "sample_id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
    "flow_id": { "type": "string", "description": "Key into spec/flows.json. Exactly one flow." },
    "host_id": { "type": "string", "description": "Key into the host eligibility record (section 6)." },

    "tier": { "enum": ["functional","inert","removed","undecided","host_perturbation"] },
    "functional_grade": { "enum": ["x_init","reset_only","power_up_only",null] },
    "removed_reason": { "enum": ["identical","no_remnant_proved",null] },
    "perturbation_cause": { "enum": ["scorr_merge",null] },
    "comparison_flow_id": { "type": ["string","null"], "description": "HOST_PERTURBATION only: the flow in which the sample is REMOVED with no remnant." },
    "flags": { "type": "array", "items": { "enum": ["functional_candidate","free_start_undecided","golden_check_undecided","host_partial_collapse","x_model_unchecked"] } },

    "netlists": {
      "type": "object", "additionalProperties": false,
      "required": ["trojan_sha256","golden_sha256","identical"],
      "properties": {
        "trojan_sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" },
        "golden_sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" },
        "identical": { "type": "boolean" }
      }
    },

    "equivalence": {
      "type": "object", "additionalProperties": false,
      "required": ["method","status"],
      "properties": {
        "method": { "enum": ["abc_miter_reset","not_run"] },
        "init": { "enum": ["reset_cycle0_zero_uninit","reset_cycle0_free_uninit"], "description": "Initial-state policy. Campaign value: reset_cycle0_zero_uninit." },
        "engines": { "type": "array", "items": { "type": "string" }, "description": "Engines in the order tried, e.g. [\"dprove\",\"pdr\"]." },
        "decided_by": { "type": ["string","null"] },
        "bounded": { "type": "boolean", "description": "true if the deciding engine is a bounded one (e.g. BMC). dprove and pdr decisions are unbounded: false." },
        "bound": { "type": ["integer","null"], "description": "Frame bound when bounded is true." },
        "timeout_s": { "type": ["number","null"] },
        "elapsed_s": { "type": ["number","null"] },
        "status": { "enum": ["proved","different","undecided","error","not_run"] },
        "counterexample_file": { "type": ["string","null"] },
        "abc_version": { "type": ["string","null"] },
        "free_start": {
          "type": "object", "additionalProperties": false,
          "required": ["status"],
          "description": "eq_free, section 3.2a. Required when status is proved.",
          "properties": {
            "status": { "enum": ["proved","different","undecided","error","not_run"] },
            "decided_by": { "type": ["string","null"] },
            "first_frame": { "type": ["integer","null"] },
            "free_flops": { "type": ["integer","null"], "description": "Flops given a free initial value in the miter." },
            "counterexample_file": { "type": ["string","null"] }
          }
        }
      }
    },

    "remnant": {
      "type": "object", "additionalProperties": false,
      "required": ["attribution","evidence_level"],
      "properties": {
        "attribution": { "enum": ["none","trojan","host","unattributed"] },
        "evidence_level": { "enum": ["delta_only","named","fingerprint"] },
        "trojan_named_cells": { "type": ["integer","null"], "description": "null when the flow renames all nets (Y_seq)." },
        "labels_netlist_file": { "type": ["string","null"], "description": "Core remnant cells, v1.0 §7 schema. Must be null or empty for tier removed." }
      }
    },

    "delta": {
      "type": "object", "additionalProperties": false,
      "required": ["cells","flops","const_drivers","pass_through"],
      "properties": {
        "cells": { "type": "integer" },
        "area_um2": { "type": ["number","null"] },
        "flops": { "type": "integer" },
        "const_drivers": { "type": "integer" },
        "pass_through": { "type": "integer" }
      }
    },

    "witness": {
      "type": "object", "additionalProperties": false,
      "required": ["source","replays"],
      "properties": {
        "source": { "enum": ["eq_counterexample","eq_free_counterexample","gauntlet_v1","none"] },
        "file": { "type": ["string","null"], "description": "Primary-input vectors, one line per cycle." },
        "sha256": { "type": ["string","null"] },
        "cycles": { "type": ["integer","null"] },
        "replays": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["mode","result"],
            "properties": {
              "mode": { "enum": ["reset","x_init"] },
              "simulator": { "type": "string" },
              "cell_models": { "type": "string" },
              "x_model_checked": { "type": "boolean" },
              "result": { "enum": ["diverged","no_divergence","x_blocked","not_run"] },
              "first_divergence_cycle": { "type": ["integer","null"] },
              "diverging_output": { "type": ["string","null"] }
            }
          }
        },
        "divergence_attribution": { "enum": ["trigger_only","payload_confirmed",null], "description": "Same meaning as v1.0 round 10." }
      }
    },

    "provenance": {
      "type": "object", "additionalProperties": false,
      "required": ["campaign","produced_by","date"],
      "properties": {
        "campaign": { "type": "string", "description": "e.g. host_population_20261122_153549" },
        "produced_by": { "type": "string", "description": "notebook and cell, or script and commit" },
        "date": { "type": "string", "format": "date" }
      }
    }
  }
}
```

Flow registry `spec/flows.json` (appendable, like `sources.json`, but each entry is immutable once a label cites it):

```json
{
  "flow_id": "ll_classic@3.1.0.dev3",
  "flow_family": "open_source",
  "description": "LibreLane Classic, synthesis only",
  "tools": { "librelane": "3.1.0.dev3", "yosys": "<as run>", "abc": "<yosys-abc as run>" },
  "script_sha256": "<sha256 of the exact script or config>",
  "pdk": { "name": "sky130A", "pdk_version": "<commit or tag>", "std_cell_lib": "sky130_fd_sc_hd", "liberty_corner": "<as run>" },
  "options": "<free text: e.g. opt -full; opt_dff -sat>",
  "reference_flow": true
}
```

The `<as run>` fields are left open on purpose: this draft does not invent version strings. They are filled from the run directory's `cfg/` and tool logs when the registry is built.

---

## 5. Cross-field rules (R12 to R19)

Numbered after v1.0's R1 to R11.

- R12. Flow scope. Every `label.json` names exactly one `flow_id` that exists in `spec/flows.json`. No file, field or derived table may state a post-synthesis label without a flow_id or merge labels from two flows.
- R13. New flow on any change. A change to any `tools` version, `script_sha256`, `pdk` field or `options` is a new `flow_id`. Labels are recomputed, never copied.
- R14. Tier evidence. The tier must follow the decision table of section 3.5 from the stored evidence. The validator recomputes the tier from the record and fails on a mismatch.
  - `removed` + `identical` ⇒ `netlists.identical == true` and `trojan_sha256 == golden_sha256`.
  - `removed` + `no_remnant_proved` ⇒ `equivalence.status == proved`, `equivalence.free_start.status == proved` and `remnant.attribution == none`.
  - `inert` ⇒ `equivalence.status == proved`, `equivalence.free_start.status == proved` and `remnant.attribution == trojan`.
  - `functional` with grade `x_init` or `reset_only` ⇒ at least one replay with `result == diverged`, and `functional_grade` set to match.
  - `functional` with grade `power_up_only` ⇒ `equivalence.status == proved`, `equivalence.free_start.status == different`, `witness.source == eq_free_counterexample`, no `reset` or `x_init` replay diverged, and the `power_up` replay diverged.
  - `undecided` ⇒ no replay diverged.
- R15. Bounded results never decide. A tier of `inert` or `removed` must rest on `identical == true` or on an unbounded `proved` (`equivalence.bounded == false`). A replay result of `no_divergence` or `x_blocked`, a timeout, or a bounded engine's "no counterexample" can only give `undecided`.
- R16. Conflict. A `diverged` replay together with `equivalence.status == proved` fails validation (section 3.5).
- R17. Removed means empty. For `removed`, the per-flow `labels_netlist.json` is absent or has empty `labels`. For `inert` and `functional`, it is present and non-empty whenever `remnant.evidence_level` is `named` or `fingerprint`.
- R18. Host eligibility. A `label.json` exists only for (host, flow) pairs that are eligible under section 6. A pair whose golden check is `undecided` carries the flag `golden_check_undecided` (or is excluded; open decision 4).
- R19. Views are derived. No binary "is Trojan" value is stored in any v1.1 file. Detector labels are computed at load from `tier` (section 8.3), the same way v1.0 derives `neighborhood`.

---

## 6. Golden check per flow and host eligibility

### 6.1 Golden check

For every host H and every non-reference flow F, prove the golden netlist of H under F equivalent to the golden netlist of H under the reference flow, with the same `eq_rst` method and initial-state policy as section 3.2. Stored once per (host, flow) in `data/hosts/<host_id>/golden_checks.json`:

```json
{ "host_id": "b18", "flow_id": "y_sat@<hash>", "reference_flow_id": "ll_classic@3.1.0.dev3",
  "status": "undecided", "engines": ["dprove","pdr"], "timeout_s": 600, "init": "reset_cycle0_zero_uninit" }
```

Why it is needed: if F changes the host's own behaviour, every tier under F compares against a golden that is wrong, and "proved equivalent to golden" means nothing about the Trojan.

Campaign status (47 hosts, two non-reference flows, 94 checks): 90 proved, 4 undecided at 600 s (Y_sat on b18; Y_seq on b17, b18 and s13207). None different.

The reference flow itself is not checked against the RTL. Doing so (Yosys `equiv_*` or a second synthesis tool) would close the chain; it is listed as open decision 5.

### 6.2 Eligibility rule

A host H is eligible for flow F when all of these hold:

1. The golden check for (H, F) is `proved`, or F is the reference flow. `different` excludes the pair. `undecided` is open decision 4.
2. H is not degenerate. H is degenerate when some registered flow reduces its golden netlist to constant drivers only (no flops) and that netlist is proved equivalent to the reference golden. That is a proof that every output is constant from reset, and a host whose outputs never change cannot show a Trojan's payload.
3. H is not on the exclusion list in `spec/host_exclusions.json`, where each entry names the host, the reason, the evidence and the date.

b19 meets condition 2: under Y_seq its golden is 30 tie cells, proved equal to the 84,797-cell LL golden, so all 30 output bits are constant 0 from reset. It is excluded for every flow. The entry stays open until the cause is known: the constant outputs may come from the host itself or from our wrapper (reset polarity, port mapping), and the second case would be a wrapper bug that also needs checking on other large hosts.

Partial collapse is a flag, not an exclusion: b18 drops from 3,122 to 113 flops under Y_seq. Labels for such pairs carry `host_partial_collapse`. The threshold for setting the flag is open decision 6.

b18 is excluded from the benchmark release for every flow (decided by Mahdi, 24 November 2026). Reasons: the partial collapse above, the undecided golden checks under Y_sat and Y_seq, and run time (about 20 minutes per (twin, flow) for synthesis, proofs and replays). The exclusion covers its decoys and its live twins alike: a host that keeps only one class would let a detector score by recognising the host. The ETS 2027 campaign figures, which include b18 with its flag, are not affected. Twelve b18 live twins (36 netlists, all FUNCTIONAL) were labelled before the decision and stay on disk, outside the release.

Rule for the release: the host list is one list, applied to decoys and positives together. Release hosts: the 47 campaign hosts minus b18, that is 46 hosts.

---

## 7. Hooks for the three novelty risks

### 7.1 X-init against reset replay (SeqCube-HT; PROVISIONAL)

Claim to make measurable: a witness that fires from a defined reset state may not fire from an unknown power-up state, so "witness-validated" depends on the initial-state assumption. Our abstract-level reading is that SeqCube-HT validates witnesses from reset traces; this is PROVISIONAL until the full text confirms their initial-state semantics.

Hook in the schema: every FUNCTIONAL label carries both replays (`reset` and `x_init`) and the sub-grade. The release report gives, per flow: number FUNCTIONAL, number with `x_init` pass, number `reset_only`, number `power_up_only`, number `x_blocked`. Measured on the live twins (46 release hosts, LL): 685 `x_init`, 163 `reset_only`, 26 `power_up_only`.

Experiment: take reset-witnessed instances built the way SeqCube-HT builds them (or the v1.0 gauntlet's input-driven, reset-based witnesses, which are the same kind), replay them in both modes on each flow's netlist, and report the `reset_only` share. If it is zero, the X-init point is not a difference and the paper drops it. If it is not zero, it is a measured result.

### 7.2 Survival is not function (Qin et al.; PROVISIONAL)

Claim to make measurable: a Trojan whose cells survive synthesis is not thereby a functional Trojan. The scheme reports two rates per flow and never one alone:
- structural survival = (FUNCTIONAL + INERT) / labelled;
- functional survival = FUNCTIONAL / labelled.

On the current population the two rates differ completely: 282 survivors over three flows, all 282 proved equivalent from reset, so structural survival is 141, 94 and 47 of 893 and functional survival is 0 in every flow.

What Qin et al.'s "100 % survival" counts, and what their SAT check proves, is unknown from the abstract. A full sequential equivalence proof from reset that passes rules out FUNCTIONAL from reset, so if their check is of that kind, their survivors are INERT by our definition; if it is combinational or bounded, it separates neither tier. Nothing about their method goes into a paper until the full text is read. PROVISIONAL.

### 7.3 Detector experiment: inert decoys as Trojans or as clean

Three label views, computed at load from the tiers (R19). Clean samples are 0 in every view.

| Tier | view `rtl` (v1.0 practice) | view `present` | view `functional` |
|---|---|---|---|
| FUNCTIONAL | 1 | 1 | 1 |
| INERT | 1 | 1 | 0 |
| REMOVED | 1 | 0 | 0 |
| UNDECIDED | excluded | excluded | excluded |
| HOST_PERTURBATION | excluded | excluded | excluded |

The question "does counting inert decoys as Trojans change a detector's reported result" is the comparison of `present` against `functional`; the question the ETS paper already raises is `rtl` against the other two. Protocol: one detector, one flow at a time, the same `variant_group`-atomic splits as v1.0 §8, train and score under each view, report recall, precision and AUC per view with confidence intervals. The detector itself (a GNN from the literature, or the structural score D2 of the ETS paper as a training-free baseline) is open decision 7.

Blocking fact: the population has no FUNCTIONAL netlists (section 9), so the `functional` view has no positives today. The experiment needs a FUNCTIONAL population first; the natural source is the v1.0 gauntlet corpus (samples with `activation_proof_pass: true`) run through the three flows.

---

## 8. Mapping onto v1.0 fields

### 8.1 Field by field

| v1.0 field | v1.0 meaning | Relation to v1.1 |
|---|---|---|
| `class: infected` | a Trojan was inserted at RTL | Unchanged. It is the RTL fact and the source of view `rtl`. It is not a netlist label. |
| `verification.synth_tool` | the single pinned flow | Must resolve to one `flow_id` in `spec/flows.json`. The v1.0 netlist files are that flow's netlist and labels. |
| `verification.synth_survival_pass` | Trojan cells present after the pinned flow | Equals "remnant attribution is `trojan`" under the pinned flow. True ⇒ tier is FUNCTIONAL, INERT or UNDECIDED there, never REMOVED. |
| `verification.functional_equiv_pass` | infected equals clean on non-trigger inputs, bounded by the vector budget | Bounded. It never sets a tier. |
| `verification.activation_proof_pass` | trigger reached and divergence seen at RTL | RTL evidence only. Its witness is a candidate for netlist replay (section 3.4); the netlist tier comes from the replay. |
| `activation_proof_method: input_driven` | trigger reached by driving inputs | The witness can be converted to a primary-input sequence and replayed per flow. |
| `activation_proof_method: state_injection` | trigger reached by forcing state | No input witness exists, so it cannot support FUNCTIONAL. Tier comes from `eq_rst` (INERT if proved, otherwise UNDECIDED). |
| `reachability_established: true` | input_driven and reached from reset (name-heuristic reset detection) | Corresponds to the `reset` replay mode at RTL. The v1.1 netlist equivalent is a `reset` replay pass, which gives `functional_grade: reset_only` unless `x_init` also passes. The round-10 reset-name heuristic is replaced in v1.1 by the reset port recorded in the host record. |
| `reachability_established: false` | not shown reachable from reset | No FUNCTIONAL without a netlist replay pass. |
| `divergence_attribution` | `trigger_only` or `payload_confirmed` | Copied per flow into `witness.divergence_attribution`; a netlist replay shows an output divergence, which is `trigger_only` unless the payload effect is checked. |
| `labels_netlist.json` (§7) | core cells of the pinned flow's netlist | Kept for the pinned flow. Other flows get their own under `flow_labels/<flow_id>/`. Empty for REMOVED (R17). |

### 8.2 The admission conflict with R4

v1.0 R4 rejects an infected sample whose `synth_survival_pass` or `activation_proof_pass` is false. The host-population Trojans (classes T3, T4 and T6) were built to be removable and have no activation proof, so none of them passes R4, and the same holds for any INERT or REMOVED instance a release wants to keep as a negative control. Two ways out:

- (a) Add an optional manifest field `admission ∈ {gauntlet_v1, flow_labelled}`. Absent means `gauntlet_v1` and R4 applies unchanged. `flow_labelled` makes the three infected-only verification flags optional and requires at least one `flow_labels/<flow_id>/label.json`. Same discipline as the optional fields of rounds 10 to 12.
- (b) Keep the flow-labelled population outside `data/samples/` in a parallel tree with its own manifest, and leave v1.0 untouched.

This draft uses (a) in the schema sketch. Open decision 1.

### 8.3 Directory contract addition

v1.0 §3 says a sample directory contains exactly the listed files. v1.1 adds one optional entry:

```
flow_labels/
  <flow_id>/
    label.json            # section 4
    labels_netlist.json   # v1.0 §7 schema, this flow; absent or empty for REMOVED
    netlist.v             # optional, subject to section 9 licensing
    witness.vec           # optional, primary-input vectors
```

---

## 9. Flow coverage

Registered now (open-source, reference flow first):

| flow_id | Flow | Hosts | Notes |
|---|---|---|---|
| `ll_classic@3.1.0.dev3` | LibreLane Classic, synthesis only | all | reference flow |
| `y_sat@7d1c5eb9258a` | Yosys with `opt -full; opt_dff -sat` | 42 of the 46 release hosts | |
| `y_sat@0d365ed5721e` | the same script with one `techmap` before cell mapping | b14, b17, b20, b21 | see below |
| `y_seq@9d87444f9c80` | Y_sat plus `abc -dff` with `scorr` | all | renames all nets; remnant evidence `delta_only` |
| `y_seq_k<k>@<hash>` | Y_seq with `scorr -F k` | E1b hosts | E1b only; one flow_id per k; not in the release |

The hash in a Yosys flow_id is the first 12 hex digits of the SHA-256 of the host's golden synthesis script, with the host name and file paths masked. `tools/htbench/export_release.py` computes it and writes the full script into `flows.json`.

Y_sat is two flows (found when the release was exported, 25 November 2026). During the campaign run of 22 November 2026, one `techmap` step was added to the Y_sat script before cell mapping, because on b14, b20 and b21 the final `opt -full` rebuilt coarse `$mux` cells that `abc -liberty` does not map, and the probe rejected those netlists (notebook 11, cell 3). The four hosts synthesized after that change, b14, b17, b20 and b21, used the new script; the other 42 release hosts used the old one. b18, which is outside the release, is not covered by this table. Under R13 a script change is a new flow_id, so their Y_sat labels carry `y_sat@0d365ed5721e`. The notebook argues that the two scripts give the same netlist on the 42 earlier hosts, because techmap changes nothing when only fine-grained gate cells remain. That was checked on 25 November 2026 and holds only in part (next paragraph). The Y_seq script already had the `techmap` step for every host, so Y_seq is one flow. For the b17 HOST_PERTURBATION labels, the comparison flow is `y_sat@0d365ed5721e`.

Re-run check of the two Y_sat scripts (25 November 2026, Yosys 0.70, results in `ysat_techmap_recheck_20261125/`). Every release Y_sat netlist of the 42 earlier hosts that had been made with the old script, 1,625 netlists (42 golden, 798 twins, 785 decoys), was synthesized again with the new script and compared byte for byte with the original.

| Result | Netlists |
|---|---|
| byte-identical | 1,555 |
| different bytes | 70 |

The 70 lie on 11 small hosts: s444 (21), s400 (11), s510 (10), s713 (8), s420_1 (5), b03, s344, s349 and s641 (3 each), s382 (2) and b08 (1). One of them is a golden netlist (s444). Each of the 70 has the same count of every cell type as its original, and each is proved equivalent to its original by `dprove` with the eq_rst miter of section 3.2. A control run of the old script on these 70 and on 70 unchanged netlists reproduced the original bytes in all 140 cases, so the difference comes from the `techmap` step and not from run-to-run variation. The two scripts are therefore equivalent on every netlist checked but not netlist-identical, and they stay two flow_ids. Labels are not copied from one to the other (R13).

Host b15 straddled the script change. Its golden netlist, 6 decoys and all 19 twins were made with the old script, and 13 decoys with the new one. The b15 golden and the 25 old-script Trojan netlists are byte-identical under both scripts. The 13 new-script decoys are compared with a golden netlist that was made with the old script; because that golden netlist has the same bytes under the new script, the comparison is the same one a new-script golden would give.

Current campaign mapped onto the tiers (47 hosts, b19 excluded, 893 Trojan netlists per flow):

| Flow | REMOVED identical | REMOVED no_remnant_proved | INERT | FUNCTIONAL | UNDECIDED | HOST_PERTURBATION |
|---|---|---|---|---|---|---|
| LL | 187 | 565 | 141 | 0 | 0 | 0 |
| Y_sat | 15 | 784 | 94 | 0 | 0 | 0 |
| Y_seq | 35 | 798 | 47 | 0 | 3 (b18) | 10 (b17) |

The Y_sat row adds up the two Y_sat flow_ids; it is a campaign summary and not a label (R12). All INERT rows use `remnant.evidence_level: delta_only` today. FUNCTIONAL candidates exist only outside the population: the E1 control with T = S (10 hosts, all three flows, `different`) and the four negative controls. None has a saved counterexample, so none is FUNCTIONAL yet under R14.

Slot for commercial flows (future work): `flow_family: commercial`, with Cadence Genus or Synopsys Design Compiler as the tool. Same record, same rules, same reference-flow golden check. Two things differ and are open decision 8: vendor licences may forbid redistributing the netlists (then the release ships `label.json`, hashes and witnesses but no `netlist.v`), and some licences restrict publishing benchmark results at all. No commercial flow is claimed until it is run, and no open-source label is ever used as a stand-in for one (R12).

---

## 10. Implementation gaps (nothing below exists yet)

1. Save counterexamples. `equiv_abc` decides `different` from the ABC log text and keeps no trace. Prototype done 24 November 2026 (`lt.equiv_cex`: `write_cex -a`, AIGER trace to per-cycle input vectors); not yet in `trojan_lib`.
2. Replay tool. A gate-level, four-state replay of a witness on the Trojan and golden netlists of one flow, in both modes of section 3.4. Prototype done 24 November 2026 (`lt.replay`, Icarus on the Liberty-function model with the miter's preprocessing, plus a golden-against-golden control replay); it does not use the sky130 Verilog cell models.
3. X-model check. Confirm that the sky130 functional cell models are X-pessimistic (no `if`/`case` constructs that turn X into a known value), or list the cells that are not, before any `x_init` pass is reported as a statement about all power-up states.
4. Per-flow netlist labeller. v1.0 §7 `structural_fingerprint` labels for each flow's netlist, which would lift remnant evidence above `delta_only` and give Y_seq a remnant test that does not rely on names.
5. Free-initial-state equivalence. Prototype done 24 November 2026 (`lt.equiv_free`, section 3.2a), and the `power_up` replay of its counterexamples (`free_replay.py`): each `init` line of the `write_aiger -zinit` map names a flop's power-up input, whose frame-0 value is set on the `<cell>.IQ` register of the model. All 52 `power_up_only` netlists diverge at frame 1, as dprove reported; all 52 controls match; without the power-up values all 52 are `x_blocked`. Not yet in `trojan_lib`.
6. Gauntlet witness export. Record the input vectors the v1.0 gauntlet drove, so its witnesses can be replayed on netlists.
7. Validator. R12 to R19 in `htbench validate`, including recomputing the tier from the evidence.
8. Registry. Fill `spec/flows.json` from the run directory's `cfg/` and tool logs; compute script hashes.

---

## 11. Open decisions for Mahdi

1. Admission: optional `admission` field in the manifest (8.2 a) or a separate tree outside `data/samples/` (8.2 b)?
2. INERT evidence: is `delta_only` attribution enough to publish INERT labels, or must INERT wait for the fingerprint labeller (gap 4)? Under `delta_only`, INERT and REMOVED(no_remnant_proved) are separated by a heuristic only.
3. Initial-state policy for INERT. Decided 24 November 2026: INERT and REMOVED(no_remnant_proved) require the free-start proof too; proved from reset but different from free start is FUNCTIONAL(power_up_only).
4. Golden check undecided: label the four pairs with a flag, or exclude them until a longer timeout or another engine decides?
5. Reference flow against RTL: check LL against the RTL, or accept LL as the reference by declaration?
6. Partial-collapse flag: what flop-loss ratio sets `host_partial_collapse` (b18 loses 96 % of its flops under Y_seq)?
7. Detector for section 7.3: a published GNN detector, the ETS paper's structural score as a baseline, or both?
8. Commercial flows: is Genus or DC available under a licence that allows publishing labels, and netlists?
9. FUNCTIONAL population. Decided 24 November 2026: both were run. The gauntlet corpus (toy combinational hosts) is FUNCTIONAL in every flow but cannot be the positive class; the live twins on the campaign hosts are (see NOTE-functional-tier-gauntlet-2026-11-24.md).
10. Naming: "INERT" or "inert decoy" in the schema and paper? The schema uses the one-word form.
