# ht-bench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24525130.svg)](https://doi.org/10.5281/zenodo.24525130)

A canonical, synthesis-verified, **dual-abstraction** hardware-Trojan benchmark
with **generation-time ground truth**. This repository holds the sample-schema
contract, the `htbench` enforcement package, and the first data release: the
flow-labelled Trojan population (TROVE, v1.1 draft) under `release/`. The LLM
insertion engine and the production extractor are later work units.

The one rule the whole project protects: **ground truth is recorded at the
moment of insertion, never reconstructed afterward by keyword heuristics.**

## Get the benchmark

The data is in `release/v1.1-draft/`. Start with `release/README.md`, which
describes the layout, the tiers and the known limits, and with
`release/v1.1-draft/labels.jsonl`, which has one line per (sample, flow).

- 1,748 samples (874 live twins and 874 decoys) on 46 ISCAS-89 and ITC'99
  hosts, synthesized with three flows: 5,244 label records.
- Each record states whether the Trojan is functional, inert or removed after
  synthesis, with the equivalence proof and the witness behind the label.
- The 27 ISCAS-89 hosts come with netlists and RTL. The 19 ITC'99 hosts come
  with labels, netlist hashes and witnesses only, because ITC'99 is licensed
  under EUPL-1.2.

Check a copy of the release with:

```bash
python tools/htbench/export_release.py --check release/v1.1-draft
```

The label definitions are in `spec/DRAFT-flow-labels-v1.1-2026-11-23.md`. That
spec is a draft, so tiers and layout can still change.

## What is in here

- `release/`: the flow-labelled data release and its README.
- `spec/SCHEMA_SPEC_v1.0.md`: the frozen contract for one benchmark *sample*.
- `spec/DRAFT-flow-labels-v1.1-2026-11-23.md`: the draft of the per-flow labels.
- `spec/schemas/*.json`: JSON Schemas for the manifest, labels, metadata, graphs.
- `spec/taxonomy.json`: closed Karri/Trust-Hub trigger and payload vocabulary.
- `tools/htbench/`: the enforcement package (validator, resolver, reference
  extractor, HW2VEC converter, round-trip gate) and the release exporter.
- `live_twins/`: the scripts that produced the v1.1 labels.
- `tests/`: fixtures and the pytest suite.

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

# gate a Phase-1 circuit-list manifest BEFORE any download (license + metrics)
htbench check-list docs/phase1_candidates.yaml

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

The flow-labelled release under `release/` is separate from this v1 pipeline:
it follows the v1.1 draft spec and is checked by `export_release.py --check`,
not by `htbench validate`.

## Licence and citation

The code is under the MIT licence (`LICENSE`). The benchmark data is under
CC BY 4.0 (`LICENSE-DATA`); host circuits keep their upstream terms, which that
file lists. To cite the benchmark, use `CITATION.cff` or the DOI
[10.5281/zenodo.24525130](https://doi.org/10.5281/zenodo.24525130), which always
points to the latest version on Zenodo.
