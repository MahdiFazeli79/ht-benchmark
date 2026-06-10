# Phase-1 Sourcing Plan — circuit-list + license map (PRE-DOWNLOAD, for review)

**Status:** reviewable draft for Mahdi's approval **before any ingestion**
(task #28). Nothing downloaded yet. The R10 license gate runs on this list, not
post-hoc. Per-bin targets: xs 60 / s 140 / m 180 / l 120 (total 500 soft; **l
hard floor 100**). **Source the l bin first.**

## Headline finding: the license gate reshapes the source list

License checks (with citations below) turn the plan's original five-family
source list on its head. The classic academic benchmarks are **out**, and the
clean corpus is dominated by modern permissively-licensed IP.

| Source family | License reality | R10 verdict |
|---|---|---|
| **ITC-99** (Politecnico I99T) | CC-BY-SA-4.0 *or* EUPL-1.2 — both **copyleft / share-alike** | **REJECT** (share-alike incompatible with a permissive CC-BY benchmark) |
| **ISCAS-85/89** | no formal license (academic convention, NCSU mirrors); netlist `.bench` format, not synthesizable RTL | **REJECT** (unconfirmed license + format mismatch) |
| **OpenCores crypto** (AES128, SHA cores, AES-128 pipelined) | mostly **LGPL** (copyleft) | **REJECT** except specific cores |
| OpenCores — Tiny AES | Apache-2.0 | accept |
| OpenCores — Mini AES | BSD | accept |
| **RISC-V ecosystem** | permissive throughout (see below) | **accept — the clean backbone** |
| **OpenTitan** | Apache-2.0 across all IP | **accept — the clean backbone** |

**Consequence:** v1 sources almost entirely from the RISC-V + OpenTitan
permissive ecosystem plus hand-picked permissive crypto/peripheral IP. OpenCores
becomes a per-core landmine check, not a bulk source. This *narrows* the well of
large designs, which makes the l-bin floor harder and raises the importance of
config-variant + parameterized scaling (below).

## A decision only you can make: ITC-99

ITC-99 is widely cited and would aid cross-paper comparability, but it is
copyleft. Including it means either (a) excluding it (conservative R10 default,
my recommendation for v1), or (b) a deliberate licensing decision to carry
CC-BY-SA circuits inside the aggregate with per-circuit share-alike handling —
an aggregate-vs-derivative question that needs an IP-law check, not an autonomous
call. **Recommendation: exclude for v1; revisit only if reviewers demand ITC-99
comparability, and then with legal review.** The R10 gate already rejects it, so
the safe default is the default.

## The clean backbone (R10-confirmed permissive)

| Source | License | Bin (proxy) | Notes |
|---|---|---|---|
| PicoRV32 | ISC | s–m | small 32-bit core; config variants |
| SERV | ISC | xs–s | bit-serial, tiny |
| Ibex | Apache-2.0 | m | 2-stage 32-bit core |
| CV32E40P / CV32E40X (OpenHW) | Solderpad-2.1 | m | 32-bit cores |
| VexRiscv | MIT | s–l | highly configurable (small→large) |
| **CVA6 / Ariane** (OpenHW) | Solderpad-2.1 | **l** | 64-bit application core — large |
| **OpenTitan IP** (aes, hmac, kmac, **otbn**, flash_ctrl, usbdev, spi_host, rv_core_ibex) | Apache-2.0 | m–**l** | many sizable blocks; OTBN + flash_ctrl + usbdev are l-bin candidates |
| Tiny AES / Mini AES | Apache-2.0 / BSD | s | small crypto |
| PULP platform IP | Solderpad-2.1 | m–l | accelerators, interconnect |

## l-bin first (>10k nodes; floor 100) — the hard, source-first work

Because the copyleft exclusions removed ITC-99 and most OpenCores, 100 distinct
>10k-node clean designs cannot come from "famous large benchmarks." The realistic
path is three legs, sourced before any Trojan insertion:

1. **Large cores as-is:** CVA6/Ariane, larger CV/PULP cores, OTBN, big OpenTitan
   blocks. Distinct designs: ~15–30 realistically.
2. **Config variants of parameterized cores:** VexRiscv / Rocket-class generators
   and parameterized OpenTitan/PULP blocks instantiated at large configs. A
   config variant is a *real synthesizable design*, not a fake — legitimate, and
   the honest way to populate l without manufacturing circuits. Distinct configs:
   many, but flag in metadata that they share a generator (avoid train/test
   leakage across variants of one generator — same discipline as §4.2 dedup).
3. **Parameterized non-core IP scaled up:** wide AES/crypto datapaths, large FFT,
   systolic multipliers, big FIFO/regfile-heavy blocks at large WIDTH/DEPTH.

**Steering caveat (supervisor):** bins are defined by post-extraction DFG node
count, but sourcing is pre-extraction. Steer acquisition by an **RTL-LOC proxy**,
assign the true bin after extraction, and **track both** so a systematic proxy
bias surfaces early. Rough proxy: >10k nodes ≈ 1.5–4k+ LOC depending on style;
treat the proxy as a filter, not a guarantee.

## Intake gate (runs on this list before download)

For every candidate: confirm SPDX `license` ∈ `spec/licenses.json` allowlist
(R10), record `license_url`, record the RTL-LOC proxy and intended bin. A
candidate whose license can't be confirmed is dropped here, on the reviewable
list, never silently ingested. Leakage discipline: variants sharing a generator
are marked so the official split never straddles them.

## Rulings (settled 2026-06-10)

1. **l-floor = ≥100 l-bin samples spanning ≥25 distinct `circuit_family`.** Config
   variants count, but the *family* floor (≥25) is the real constraint, so the
   bin can't be "6 cores × 20 configs." Every variant shares its generator's
   `circuit_family`; splits are atomic over `circuit_family` (frozen, spec §8);
   the distinct-family count per bin is a reported statistic ("120 large across
   27 families"). **Source the l bin and assign `circuit_family` in the SAME
   pass** — family identity is the steering variable, not a post-hoc tag.
2. **ITC-99 excluded from the redistributed corpus**, and the exclusion becomes a
   one-paragraph **license-rigor note** in §2/§9 ("a redistributability gate
   excluded ITC-99 (copyleft) and most OpenCores crypto (LGPL) at intake"). v1.1
   nicety: an adapter script that points at the user's *own* ITC-99 copy
   (distribute the adapter, not the circuits) — sidesteps redistribution.
3. **Bounded OpenCores per-core pass**, targeting style diversity the
   RISC-V/OpenTitan backbone lacks (peripherals, small crypto, bus logic).
   Confirm license per-core, take the clean ones (Tiny AES Apache, Mini AES BSD,
   and whatever clears), **stop when marginal diversity flattens**. The value is
   not count (~a dozen) but the defense against "this is just a RISC-V benchmark"
   — the backbone is structurally homogeneous, and a model could learn
   "RISC-V-shaped = the distribution" instead of learning Trojans.

## R9 measurement: run it on the FIRST LARGE designs (not the easy ones)

Task #27's R9 collision-rate check runs on the first large RISC-V cores
specifically: deep hierarchy + generate blocks are where HW2VEC's
flatten/underscore-mangle is most likely to alias names. If R9 bites, it bites
hardest in the very bin you're working hardest to fill, so measure there first —
a bad rate then changes the handle/normalization before 100 l-bin circuits are
sourced, not after.

## Sources

- ITC-99 license: [cad-polito-it/I99T](https://github.com/cad-polito-it/I99T) (CC-BY-SA-4.0 / EUPL-1.2)
- OpenCores crypto licenses: [OpenCores Crypto projects](https://opencores.org/projects?expanded=Crypto+core), [Tiny AES (Apache-2.0)](https://opencores.org/projects/tiny_aes), [Mini AES (BSD)](https://opencores.org/projects/mini_aes)
- ISCAS benchmarks (no formal license): [ISCAS89 mirror](https://filebox.ece.vt.edu/~mhsiao/iscas89.html)
