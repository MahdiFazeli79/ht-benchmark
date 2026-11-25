# TROVE flow-labelled release, v1.1 draft

This folder holds the flow-labelled Trojan population defined in
`spec/DRAFT-flow-labels-v1.1-2026-11-23.md`. The spec is a draft, so the tier
definitions and the file layout can still change.

## Contents of `v1.1-draft/`

| Path | What it is |
|---|---|
| `labels.jsonl` | One line per (sample, flow): tier, grade, flags and the folder of the record. Start here. |
| `data/samples/<sample_id>/sample.json` | Host, Trojan class, sub-variant and parameters of the sample. |
| `data/samples/<sample_id>/rtl.v` | RTL of the host with the Trojan inserted. |
| `data/samples/<sample_id>/flow_labels/<flow_id>/label.json` | The label record (spec section 4). |
| `.../flow_labels/<flow_id>/netlist.v` | The synthesized netlist of the sample under that flow. |
| `.../flow_labels/<flow_id>/witness.vec` | Primary-input vectors, one line per clock cycle, for FUNCTIONAL records. |
| `.../flow_labels/<flow_id>/power_up_state.json` | Power-up values of the flops without reset, for grade `power_up_only`. |
| `golden/<host>/<flow_id>/netlist.v` | Trojan-free netlist of the host under the same flow. |
| `flows.json` | The synthesis flows, with tool versions and script hashes. |
| `hosts.json` | Ports, clock, reset, upstream licence and distribution mode of each host. |
| `MANIFEST.json` | SHA-256 and size of every file. |

Size: 1,748 samples (874 live twins and 874 decoys) on 46 hosts, three flows
each, 5,244 label records.

## Tiers

`functional`, `inert`, `removed`, `undecided` and `host_perturbation`, as
defined in spec section 2. Live twins are the positive class and decoys the
negative class. No binary "is Trojan" value is stored; a detector label is
derived from the tier (spec section 8.3).

## Hosts without netlists

The 19 ITC'99 hosts (b01 to b22) are distributed as labels only: label
records, netlist hashes, witnesses and Trojan parameters, with no `netlist.v`,
`rtl.v` or golden netlist. ITC'99 is licensed under EUPL-1.2
(https://github.com/cad-polito-it/I99T), which does not allow derived netlists
to be redistributed under the CC-BY-4.0 licence of this data. `hosts.json`
marks these hosts with `"distribution": "labels_only"`. The netlist hashes in
each `label.json` let a rebuilt netlist be verified.

The 27 ISCAS-89 hosts ship with netlists. The original ISCAS-89 distribution
states no licence; `hosts.json` records this as `NOASSERTION`.

## Known limits

- Remnant evidence is `delta_only` for every record (spec section 3.3), so
  `inert` and `removed (no_remnant_proved)` are separated by a structural
  heuristic.
- Hosts b14, b17, b20 and b21 ran the Y_sat flow with one extra `techmap`
  step and therefore have their own flow id.
- The PDK version, the ABC version and the Yosys version inside LibreLane were
  not recorded by the runs. They are `null` in `flows.json`.
- Every `x_init` replay has `x_model_checked: false` (spec section 10, item 3).

## Checking the release

```
python tools/htbench/export_release.py --check release/v1.1-draft
```

The check recomputes each tier from the stored evidence with the decision
table of spec section 3.5 and verifies the hashes and witnesses.
