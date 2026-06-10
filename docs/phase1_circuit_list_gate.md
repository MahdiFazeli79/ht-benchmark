# Phase-1 circuit-list gate report (PRE-DOWNLOAD)

**Nothing ingested.** This is the reviewable artifact.

- manifest: **well-formed**
- candidates: 40  (download-eligible after R10: **38**, blocked: 2)
- rejected-on-intake: 5

## The four headline numbers

| # | Metric | Value | Verdict |
|---|---|---|---|
| 1 | l-bin distinct `variant_group` | 15 | FAIL vs ≥25 floor |
| 2 | Homogeneity (RISC-V 35% + OpenTitan 28%) | 62% | OK |
| 3 | Rejected-on-intake | 5 | audit trail |
| 4 | SystemVerilog → needs sv2v | 52% | pipeline dependency |

## Distinct `variant_group` per bin

- xs: 1
- s: 5
- m: 19
- l: 15

## R10-blocked (cannot be cloned until license confirmed)

- `e203` — license `unconfirmed` not on the redistributable allowlist
- `openpiton` — license `unconfirmed` not on the redistributable allowlist
