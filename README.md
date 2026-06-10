# ht-bench

A canonical, synthesis-verified, **dual-abstraction** hardware-Trojan benchmark
with **generation-time ground truth**. This repository currently holds the
frozen sample-schema contract and the `htbench` enforcement package; the corpus,
the LLM insertion engine, and the production extractor are later work units.

The one rule the whole project protects: **ground truth is recorded at the
moment of insertion, never reconstructed afterward by keyword heuristics.**

## What is in here

- `spec/SCHEMA_SPEC_v1.0.md` — the frozen contract for one benchmark *sample*.
- `spec/schemas/*.json` — JSON Schemas for the manifest, labels, metadata, graphs.
- `spec/taxonomy.json` — closed Karri/Trust-Hub trigger and payload vocabulary.
- `tools/htbench/` — the enforcement package (validator, resolver, reference
  extractor, HW2VEC converter, round-trip gate).
- `tests/` — fixtures and the pytest suite.

## The four inversions (store intrinsic truth, derive the rest)

1. **Identity.** Labels reference circuit-intrinsic **handles**, never positional
   graph indices. Indices are recomputed at load and cached per release.
2. **Graph format.** Canonical graphs are **JSON**. The HW2VEC `torch_geometric`
   view is produced by a converter (`hw2vec_compat.to_hw2vec`) at load time.
   **Pickle is never the store of record** — it does not survive across torch /
   torch_geometric versions.
3. **Provenance.** `source` is a free string; the closed, analysis-meaningful
   axis is `source_kind ∈ {llm_generated, academic_benchmark, open_source_ip,
   vendor_ip}`.
4. **Derived labels.** Only `core` labels are stored. `neighborhood` is computed
   at load from a `k` parameter (`resolve.neighborhood`), never baked into a file.

## Handles are AST-derived

A handle comes from the Verilog **AST** (Pyverilog scoped signal names),
upstream of any tool preprocessing — e.g. `top.uart_rx.cnt`, or
`expr:and(top.a,top.b)@top.s:` for an unnamed expression node. It is **not** the
HW2VEC DFG node name: HW2VEC flattens and strips underscores, which is lossy
(`trojan_cnt` and `trojancnt` collapse) and tool-coupled. HW2VEC is a downstream
consumer mapped onto handles, with a collision detector (rule **R9**) that
rejects any sample whose handles would alias under that transform.

## Install

```bash
pip install -e tools/                 # core: jsonschema
pip install -e 'tools/[extract]'      # + Pyverilog, for the reference extractor / round-trip gate
pip install -e 'tools/[hw2vec]'       # + torch, torch_geometric, for to_hw2vec
```

The reference extractor also needs the Graphviz system library
(`brew install graphviz` / `apt-get install graphviz graphviz-dev`) for
`pygraphviz`.

## Use

```bash
# elaborate a parameterized / SystemVerilog core into flat Verilog-2005
# (sv2v -> yosys -chparam), preserving intrinsic signal names
htbench elaborate core.sv pkg.sv --top my_core --chparam CFG=33 -o elaborated.v

# validate a sample directory (or a directory of samples)
htbench validate data/samples --rtl-only

# graph-regeneration invariance gate (the test that retires the re-run risk)
htbench roundtrip data/samples --perturb
```

`elaborate` is the RTL front-end for production cores. Raw Pyverilog parses
Verilog-2005 but cannot *elaborate* packed-parameter generate-if gating (the
CVA6-style `CFG[...]` wall); `sv2v -> yosys hierarchy -chparam -> write_verilog`
resolves it while keeping user signal names intact (`write_verilog` runs before
techmap, so no gensyms). One concrete config = one sample; multiple configs of
one design become leakage-linked variants under a single `variant_group`. See
`docs/phase1_elaborate_stage.md`.

`validate` enforces the JSON Schemas plus cross-field rules **R1–R9** (taxonomy
feasibility, verification gates, manifest-matches-files diff, class consistency,
negative-class realism, AST-handle injectivity), handle uniqueness, and
forbidden-key patterns. `roundtrip` re-extracts the DFG, re-resolves the same
labels, and asserts the labeled `core` set is unchanged; `--perturb` shuffles
extraction order to prove handles are traversal-order-independent.

## Develop

```bash
python -m pytest tests/ -v            # full suite
python tests/build_fixtures.py        # regenerate fixtures from source
```

### Secret guard (enable before any work that touches API keys)

A fail-closed scanner rejects known key prefixes and high-entropy secret
assignments. It runs in CI and ships as a pre-commit hook:

```bash
git config core.hooksPath hooks      # enable the pre-commit secret scan
htbench-scan-secrets .               # scan the tree manually
```

Mark legitimate fixtures with a trailing `# pragma: allowlist secret`.

## Status

v1 operates in `--rtl-only` mode. Netlist extraction and netlist round-trip are
deferred to the Phase-0.3 labeling-method spike (`hierarchy_path` vs
`structural_fingerprint`); the netlist schema, validator support, and converter
are already in place.
