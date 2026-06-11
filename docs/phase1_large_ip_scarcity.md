# Permissive large-IP scarcity — the l-bin finding (Branch B)

The ≥25-distinct-`variant_group` l-bin floor is **retired** (spec round 9). The
complete, parseability-confirmed count of permissive, large (>10k-node),
independent, parseable RTL designs the open ecosystem yields is **15**. That
scarcity is not a sourcing failure — it is a true, citable fact about the
open-hardware ecosystem, and it is the large-circuit story: a size-cliff
demonstrated across 15 independent large designs, with the scarcity documented.

This file is the methodology behind "only 15," so the claim reads as "we looked
rigorously and this is what exists," not "we found 15 and stopped."

## How we searched

Permissive (R10-allowlisted) RTL, steered toward the large bin first (sourcing by
RTL-size proxy, true bin assigned post-extraction). Pools:
- **RISC-V ecosystem** — PicoRV32, SERV, Ibex, CV32E40P, CVA6, VexRiscv, OpenC910,
  VeeR-EH1/EH2, Snitch, Rocket, BOOM, BlackParrot.
- **OpenTitan** — the lowRISC IP blocks (otbn, kmac, flash_ctrl, usbdev, aes,
  hmac, otp_ctrl, …), all Apache-2.0.
- **Permissive non-CPU IP (Branch A expansion)** — comms (corundum NIC,
  alexforencich ethernet/axi/pcie), crypto (secworks AES/SHA/ChaCha), ML/DSP
  (gemmini, PULP hwpe), NoC (openpiton).

## What we excluded, and why (the gate did this mechanically)

- **Copyleft → R10 reject**: ITC-99 (CC-BY-SA / EUPL), most OpenCores crypto
  (LGPL), any GPL/LGPL/MPL. Not redistributable under one CC-BY benchmark license.
- **No formal license → R10 reject (default-closed)**: ISCAS-85/89 (academic
  convention only); also `.bench` netlists, not synthesizable RTL.
- **Wrong language**: NEORV32 (VHDL — outside the Verilog/SV pipeline).
- **Unconfirmed license → blocked pending verification**: e203, openpiton.
- **Parseability**: confirmed NOT a blocker — the sv2v→Yosys-elaborate→Pyverilog
  →R9 canary cleared CVA6-class SystemVerilog (`docs/phase1_sv2v_r9_canary.md`),
  so the SV large designs are real, not phantom rows.

## The 15 l-bin distinct families (8 circuit families)

| variant_group | family | license | source |
|---|---|---|---|
| cva6 | riscv_cpu | Solderpad-2.1 | openhwgroup/cva6 |
| openc910 | riscv_cpu | Apache-2.0 | XUANTIE-RV/openc910 |
| veer_eh1 | riscv_cpu | Apache-2.0 | chipsalliance/Cores-VeeR-EH1 |
| veer_eh2 | riscv_cpu | Apache-2.0 | chipsalliance/Cores-VeeR-EH2 |
| rocket | riscv_cpu | BSD-3 | chipsalliance/rocket-chip |
| boom | riscv_cpu | BSD-3 | riscv-boom/riscv-boom |
| snitch | riscv_cpu | Solderpad-2.1 | pulp-platform/snitch_cluster |
| black_parrot | riscv_cpu | BSD-3 | black-parrot/black-parrot |
| ot_otbn | bignum_accel | Apache-2.0 | lowRISC/opentitan |
| ot_kmac | keccak | Apache-2.0 | lowRISC/opentitan |
| ot_flash_ctrl | flash_controller | Apache-2.0 | lowRISC/opentitan |
| ot_usbdev | usb_device | Apache-2.0 | lowRISC/opentitan |
| corundum | ethernet_nic | BSD-2 | ucsdsysnet/corundum |
| gemmini | ml_accelerator | BSD-3 | ucb-bar/gemmini |
| openpiton | noc_tile | unconfirmed (blocked) | PrincetonUniversity/openpiton |

License-eligible now: **14** (openpiton pending license verification).

## Independence — the honest caveats (Branch B condition)

The 15 are distinct `variant_group`s: none is a config-variant of another (the
split-atomicity violation that would make the count a leakage artifact, e.g.
"one core × 20 configs"). But "independent" has two disclosed correlations a
reader should weigh:

1. **Four OpenTitan blocks share one repo and the `prim_*` primitive library.**
   ot_otbn / ot_kmac / ot_flash_ctrl / ot_usbdev are functionally distinct
   designs (different tops, different RTL trees, different circuit families), so
   they count as four `variant_group`s — they are NOT generator-config siblings.
   But they share lowRISC's common primitive submodules (prim_fifo, prim_lfsr,
   prim_packer, …), so their low-level substructure is correlated. Disclosed, not
   collapsed.
2. **veer_eh1 / veer_eh2 are sibling microarchitectures** from one vendor lineage
   (chipsalliance VeeR). Separate repos, separate RTL (EH2 adds multi-threading),
   so distinct `variant_group`s — but related lineage.

8 distinct circuit families across the 15 is real functional diversity given the
scarcity; the RISC-V CPUs dominate the count (8/15) because large permissive
*non*-CPU RTL is the scarcest sub-pool — itself part of the finding.

## Per-design cost (why grinding past 15 is a bad trade)

The canary measured the cost of one large SV design end to end: package-name ≠
filename, user→full config transform (`build_config`), a stubbed generated
include (`l15.tmp.h`), and a struct-param wrapper — per-design build-system
archaeology, worse for OpenTitan (prim/fusesoc closure). Each step toward a
retired ≥25 floor pays that cost again to buy a marginal large family in an
ecosystem that demonstrably does not have them — and each such design is itself
~75% tool-generated nodes after elaboration (canary). The honest move is to
report the 15 and the scarcity, not to grind.
