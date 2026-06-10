# sv2v Canary — Findings (scoped test, clones deleted)

**Scope (Mahdi-approved):** clone CVA6 + an OpenTitan block into scratch, run the
FULL chain sv2v → Pyverilog → htbench extractor → R9, measure what survives,
**delete the clones**. These were never corpus; nothing entered `data/samples/`,
nothing was committed but this findings note. A successful parse here does NOT
authorize ingest — that still requires the candidate-list review.

## The chain, leg by leg (CVA6 `alu`, with its real package/typedef/import deps)

| Leg | Result |
|---|---|
| **sv2v** (SV → Verilog) | **PASS** — `alu.sv` + riscv_pkg/config_pkg/ariane_pkg/concrete-config converted clean, exit 0, 321 lines of Verilog |
| **Pyverilog parse** | **FAIL → fixable** — sv2v emits `(* full_case, parallel_case *)` synthesis attributes Pyverilog rejects; a 1-line attribute-strip shim fixes parsing |
| **Pyverilog dataflow elaboration** | **FAIL — hard wall** — `Can not resolve generate-if condition` on CVA6's packed-config parameter (`CVA6Cfg[16626]` gating generate blocks) |
| **R9 / extractor / DFG** | not reached |

## The load-bearing finding

**sv2v is necessary but NOT sufficient.** Two blockers beyond it, one trivial and
one structural:

1. **Attribute shim (trivial).** sv2v passes `(* ... *)` attributes through;
   Pyverilog can't parse them. A regex strip (preserving `@(*)`) fixes it. One
   line. Not the problem.

2. **Parameter/generate elaboration (structural).** Pyverilog's dataflow analyzer
   cannot resolve `generate-if` gated on parameter values. CVA6 expresses its
   whole configuration as a packed-struct parameter and gates logic on bit-slices
   of it, so elaboration stalls. **This is not SV-specific — it is a
   parameter-elaboration gap, and essentially all real IP is heavily
   parameterized.** Raw Pyverilog extracts toy/CORE-style designs (constant or
   no params) but not configured production cores.

3. **Dependency-closure assembly (per-design effort).** OpenTitan `hmac` could not
   even be fed to sv2v without first assembling its full package + `prim_*` +
   `prim_sha2` closure across IP boundaries. Each OpenTitan block is a
   dependency-resolution task, not a single file. (sv2v errored: `hmac_pkg.sv
   does not exist` — the closure was incomplete.)

## What this means for v1 (scope-reshaping)

The htbench RTL-DFG front-end is raw Pyverilog. That choice quietly assumed
Verilog-2005, constant-parameter designs — which the toy fixtures and the CORE
corpus are, but the permissive large-IP backbone is not. To ingest real
parameterized SV cores, the extraction front-end needs **elaboration**, not just
SV→Verilog translation. The realistic path:

> source → (sv2v if SV) → **Yosys elaborate with a concrete parameter set
> (`hierarchy -top -chparam`, resolve/flatten generate) → `write_verilog`** →
> attribute-strip → Pyverilog DFG → handles → R9

We already run Yosys on the netlist side, so adding a Yosys *elaboration* pass on
the RTL side is consistent — but it is a real new pipeline stage, it picks a
concrete config per design (which is fine and honest — a configured instance is a
real design), and it must be checked for whether intrinsic AST handle names
survive Yosys elaboration (its own mini-spike).

**This is the finding the canary was for:** it surfaced, at two repos, that the
SV backbone needs an elaboration front-end before sourcing fifty — exactly the
kind of toolchain assumption that would otherwise have detonated mid-Phase-1.

## Open decisions for Mahdi

1. **Adopt a Yosys-elaboration RTL front-end** (the realistic fix), accepting it
   as a new pipeline stage + a handle-survival mini-spike — vs. restrict v1 to
   designs raw Pyverilog can elaborate (which excludes most of the permissive
   large backbone and likely kills the l bin).
2. If Yosys-elaboration: confirm the "configured instance is a real design"
   framing is acceptable (it is standard, but worth stating in §4).

## Smaller fix noted in passing

CVA6's license is **SHL-0.51** (Solderpad 0.51), not the `Solderpad-2.1` on the
R10 allowlist. Add `SHL-0.51` / `SHL-2.0` / `SHL-2.1` SPDX ids to
`spec/licenses.json` (all Apache-based permissive) before ingesting OpenHW/PULP IP.
