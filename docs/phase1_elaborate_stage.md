# Yosys-elaboration RTL front-end — build record

Status: **built + green** (task #29). Implements the front-end the sv2v canary
and the elaboration mini-spike concluded was necessary
(`docs/phase1_sv2v_canary.md`). Closes the elaboration wall that blocked the
parameterized / SystemVerilog production-core backbone.

## What it is

`tools/htbench/elaborate.py`, a pre-extraction stage:

    source(.sv?) --sv2v--> Verilog-2005
                 --yosys--> read_verilog -sv
                            hierarchy -top <top> [-chparam K V ...]
                            proc; flatten; opt_clean
                            write_verilog -noattr
                 --attr-strip--> clean Verilog-2005
                 --> htbench.extract.extract_rtl

Public API:

- `elaborate(sources, top, chparams=None, *, systemverilog=None, work_dir=None,
  yosys_bin, sv2v_bin) -> ElaborationResult` — runs the pipeline, returns the
  path to flat Verilog plus a provenance record.
- `elaborate_and_extract(sources, top, chparams=None) -> (graph, ElaborationResult)`
  — convenience wrapper to the reference extractor.
- `is_synthetic_net(handle)` / `partition_synthetic(handles)` — the `_N_`-net policy.
- `plan_variants(variant_group, configs)` — the config-selection policy.
- CLI: `htbench elaborate SRC... --top T [--chparam K=V]... [--sv|--no-sv] -o OUT`.

## Why a separate stage (the wall, reproduced)

The fixture `tests/fixtures/elab_src/packed_cfg.sv` is a minimal reproducer of
the CVA6-style failure, confirmed on this toolchain (yosys 0.65, sv2v 0.0.13,
pyverilog 1.3.0):

| input to raw `extract_rtl`         | result                                            |
|------------------------------------|---------------------------------------------------|
| the `.sv` directly                 | `ParseError` (the `logic` keyword)                |
| sv2v's Verilog-2005 output         | `FormatError: Can not resolve generate-if condition` |
| `elaborate(...)` output (CFG=1)    | 9-node DFG, all user handles intact               |

So sv2v is **necessary but not sufficient**: it lowers the syntax but leaves the
parameterized generate, which Pyverilog's dataflow analyzer cannot resolve.
Yosys `hierarchy -chparam` resolves it.

## What survives, and the caveat

Validated by the test suite (`tests/test_elaborate.py`, 13 tests):

- **User handles survive.** `top.a`, `top.b`, `top.combined`, `top.result`,
  `top.rstn` are all present after the full chain. `write_verilog` runs before
  techmap/abc, so names are not gensym'd (unlike a gate-level netlist).
- **No `$`-gensyms; R9 injective.** No handle trips the forbidden-key check; all
  handles are distinct.
- **`-chparam` selects the branch.** `CFG=1` yields `expr:and(top.a,top.b)@top.combined:`
  (the `a & b` arm); `CFG=0` yields the `or` arm. Config selection is real, not
  cosmetic.
- **Synthetic `_N_` nets (caveat).** Yosys can introduce deterministic
  auto-named intermediate nets (`_0_`, scoped `top._0_`) during proc/flatten.
  The toy fixture produces none, so the predicate is unit-tested directly. v1
  policy: **report, never reject** — they are valid handles (not forbidden), are
  round-trip-stable within a pinned Yosys, and a manifest-inserted signal never
  maps to one (manifest→handle joins are unaffected; they default clean).
  Cross-Yosys-version `_N_` stability is a v1.1 concern.

The stage is **fail-loud**: any sv2v/Yosys error raises `ElaborationError`. It
never silently falls back to raw Pyverilog — that would reintroduce the wall.

## Config-selection policy

`plan_variants(variant_group, configs)` encodes the Phase-1 rule:

- one concrete config = one sample;
- multiple configs of the same parameterized design = **leakage-linked** variants
  sharing **one** `variant_group`, so split atomicity (spec §8) keeps them on the
  same side of any train/test split;
- `sample_id` is derived from the sorted chparams (`picorv32__ENABLE_MUL1`), so
  it is stable and self-describing.

This is the structure the Phase-2 sourcing driver consumes; it does not mutate
the frozen manifest (which already carries `variant_group`).

## Provenance and the frozen schema (open item for round 8)

`ElaborationResult.provenance()` records `{stage, top, chparams, sv2v_used,
yosys_script, tool_versions}` — the reproducibility record for a configured
instance ("this sample = CVA6 with `CFG=33`, yosys 0.65, sv2v 0.0.13").

`metadata.schema.json` is `additionalProperties: false` and has no field for
this, and the spec is frozen. So provenance is **not** written into
`metadata.json` yet; it is emitted by the CLI and intended as an
`elaboration.json` sidecar. **Proposed spec round 8 (deferred, needs sign-off):**
add an optional `elaboration` provenance block to `metadata.json` so the config
that produced each sample is captured in the governed contract. Recorded here so
the freeze is respected and the decision is explicit, not silent.

## CI

A dedicated `elaborate` job installs `yosys` (apt) and `sv2v` (pinned v0.0.13)
and runs `tests/test_elaborate.py` for real — the same posture as the round-trip
gate, not a skip.
