# sv2v → elaborate → R9 canary on hard SystemVerilog (CVA6)

Scoped, delete-after canary (Mahdi-approved). **Nothing ingested**; the CVA6
clone was assembled in `/tmp`, measured, and deleted. This is the measurement
that gates the l-floor decision: *does the sv2v → Yosys-elaborate → Pyverilog →
R9 chain survive on real hard SystemVerilog?* If yes, the SV large designs
already on the candidate list are real (parseable), not phantom rows.

## Target

`openhwgroup/cva6` (Solderpad SHL), `core/multiplier.sv` — a real CVA6 datapath
module that exercises the hardest construct: a **packed-struct-typed parameter**
`config_pkg::cva6_cfg_t CVA6Cfg`, `import ariane_pkg::*`, and widths like
`CVA6Cfg.XLEN`/`CVA6Cfg.TRANS_ID_BITS`. Picked over `alu.sv` because `alu` also
takes a `type fu_data_t` param (a config-derived struct with no standalone
typedef), which would mean reconstructing CVA6's type generation — itself a
finding (below), not a clean parseability test.

Concrete config: `cv64a6_imafdc_sv39` (XLEN=64). A 12-line wrapper `mul_top`
instantiates `multiplier` with `CVA6Cfg = build_config_pkg::build_config(...)`
so one concrete config = one sample (the config-selection policy).

## Result — the chain SURVIVES

| stage | outcome |
|---|---|
| sv2v (7-file package closure → V2005) | **PASS** — 435 lines flat Verilog |
| Yosys elaborate (`hierarchy -top mul_top; proc; flatten; opt_clean`) | **PASS** |
| Pyverilog extract → DFG | **PASS** — 2258 nodes |
| **R9 collision rate** | **0%** (217 named handles, no aliasing) |

Real CVA6 signal names survive intact (`mul_top.\i_mul.clk_i`, `.clmul_d`,
`.clmulr_d`, …). No `$`-anchored gensyms trip the forbidden-key check. **The
parseability blocker is cleared on the hardest construct type** — CVA6-class SV
is viable for the corpus.

## What the canary surfaced (invisible on the toy fixture)

1. **High synthetic-handle ratio.** Of 217 named handles, only **56 are clean
   intrinsic** CVA6 signals; **162 are tool-generated** (159 Yosys `_N_`
   intermediates, 1 sv2v `_sv2v_0`, 2 inlined-function `$func$` artifacts). The
   mini-spike's "Yosys adds *a few* `_N_` nets" was optimistic — on real logic
   they are the majority of named nodes. The handle contract still holds:
   manifest-inserted signals map to the 56 intrinsic names, never to the tool
   nets. But the elaborated DFG is intermediate-heavy and that should be a stated
   characteristic of the dataset (a configured/elaborated instance is a real but
   *tool-processed* design).

2. **sv2v also injects synthetic names.** `_sv2v_N` temporaries and
   `...sext32to64$func$mul_flat.v:111$81.operand` inlined-function artifacts (with
   embedded `$` and source-line refs) are not source-intrinsic and are
   run/version-unstable. The old `is_synthetic_net` (yosys `_N_` only) missed
   them, and the frozen forbidden-key check only anchors `^\$`, so a mid-string
   `$` passed. **Fixed here:** `is_synthetic_net` widened to cover `_N_`,
   `_sv2v_N`, and any `$`-bearing handle, so they partition correctly and the R9
   rate is computed on real intrinsic names.
   **OPEN for Mahdi (handle-contract question, not changed unilaterally):** should
   a sample carrying `$func$` / `_sv2v_` handles be *tolerated-as-synthetic*
   (current v1 policy, same as `_N_`) or *hard-rejected* by the validator? Leaning
   tolerate (they never correspond to manifest signals), but it touches the frozen
   contract, so it is flagged not decided.

3. **Per-design closure assembly is real labor.** Getting one CVA6 module to
   elaborate required: resolving package-name ≠ filename (`cva6_config_pkg` lives
   in `cv64a6_imafdc_sv39_config_pkg.sv`), supplying `build_config_pkg` for the
   user-cfg → full-cfg transform, stubbing a generated `l15.tmp.h` include pulled
   by `ariane_pkg`, and a struct-param wrapper. None is a pipeline limitation —
   all are sourcing cost. **SV large designs are viable but each is hand-assembly,
   not clone-and-go.**

## Effect on the l-floor decision

The l-bin candidate rows already INCLUDE the SV designs (cva6, veer_eh1/eh2,
ot_otbn, ot_flash_ctrl, snitch, corundum). The open question was whether to
*remove* them if sv2v choked. The canary says **keep them — they are parseable**.
So the floor stays a genuine **15 distinct `variant_group`s** (SV-inclusive,
confirmed real), still **below the ≥25 floor**. The parseability proof removes the
downside (15 does not collapse) but does not add upside (it does not reach 25).

**Well-posed decision (Mahdi's call):** the honest l-floor is 15 genuine
independent large designs. Either source more permissive large IP toward ≥25
(each at the per-design assembly cost shown above), or invoke **Branch B** —
report permissive-large-IP scarcity as a finding and frame the large story as a
size-cliff across 15 independent designs. The number is now complete; the
scarcity is real, not an artifact of unproven parseability.
