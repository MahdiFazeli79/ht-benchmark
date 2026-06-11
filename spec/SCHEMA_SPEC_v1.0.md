# SPEC — Hardware Trojan Benchmark: Sample Schema, Taxonomy & Validator (v1.0)

**Status:** FROZEN contract for v1. Date: 2026-06-10.
**Audience:** implementers (human or Claude Code). This is the on-disk contract for one benchmark *sample*, the controlled Trojan taxonomy, the node/cell referencing scheme, and the validator + round-trip gate that enforce them. Circuit generation and LLM insertion are a later work unit and are out of scope here.

**Single overriding rule:** labels MUST reference circuit-intrinsic identity (named signals, hierarchical instance paths, or structural fingerprints), NEVER positional graph indices or tool-generated symbols. Positional indices and any derived, contestable quantity (neighborhood, vocab id) are computed at load time and never persisted in a label file.

**The four inversions this spec is built on** (store intrinsic truth, derive everything tool-specific or contestable):
1. **Identity** — labels point at intrinsic handles; integer indices are a per-release cache.
2. **Graph format** — canonical graphs are JSON; the HW2VEC `torch_geometric` view is produced by a converter at load time, never stored. Pickle is a reproducibility hazard and MUST NOT be the canonical store.
3. **Provenance** — `source` is a free string; the closed, domain-meaningful axis is `source_kind`.
4. **Derived labels** — only `core` labels are stored (objective, from the manifest); `neighborhood` is computed at load from a `k` parameter, never baked into a label file.

---

## 1. Repository layout

```
ht-bench/
  spec/
    SCHEMA_SPEC_v1.0.md           # this document
    schemas/
      trojan_manifest.schema.json
      labels_rtl.schema.json
      labels_netlist.schema.json
      metadata.schema.json
      graph.schema.json           # canonical graph JSON (RTL + netlist)
    taxonomy.json                 # closed controlled vocabulary (machine-readable)
    sources.json                  # APPENDABLE provenance registry (lint only, NOT part of the frozen contract)
  data/
    samples/<sample_id>/          # one directory per sample (clean or infected; layout §3)
  tools/
    htbench/
      __init__.py
      validate.py                 # validator CLI (§10)
      resolve.py                  # handle<->index resolution + neighborhood-at-load (§8)
      hw2vec_compat.py            # JSON graph -> torch_geometric Data converter (§9)
      roundtrip_test.py           # graph-regeneration invariance test (§11)
    pyproject.toml                # pip-installable package `htbench`
  tests/
    fixtures/                     # 5 hand-built mini samples (§12)
    test_validate.py
    test_resolve.py
    test_roundtrip.py
    test_hw2vec_compat.py
  README.md
```

Python 3.11+. Validation uses `jsonschema`. Keep `htbench` import-clean (no heavy EDA deps at import time; the converter imports torch lazily inside the function).

---

## 2. Controlled taxonomy (`spec/taxonomy.json`)

CLOSED vocabulary. No `other` value on any axis. A sample that does not fit is rejected, not bucketed. Closed enums are reserved for axes where the domain fixes the universe and a wrong value corrupts a scientific signal (payload, trigger mechanism). Provenance (`source`) is deliberately NOT here (see §5). The taxonomy describes the inserted Trojan and so applies only to `infected` samples (§4).

Emit verbatim:

```json
{
  "taxonomy_version": "1.0",
  "taxonomy_ref": "Karri et al. 2010; Trust-Hub (Shakya et al. 2017)",
  "axes": {
    "insertion_phase": { "fixed_v1": "design", "values": ["specification","design","fabrication","testing","assembly"] },
    "insertion_level": { "fixed_v1": "rtl", "values": ["system","rtl","gate","layout","physical"] },
    "activation": { "values": ["always_on","triggered"] },
    "trigger_source": { "values": ["internal","external"], "required_when": {"activation": "triggered"}, "else": null },
    "trigger_mechanism": { "values": ["combinational","sequential_counter","sequential_fsm"], "required_when": {"activation": "triggered"}, "else": null },
    "payload": { "values": ["modify_functionality","degrade_performance","leak_information","denial_of_service"] }
  },
  "feasibility_constraints": [
    {
      "id": "always_on_excludes_functional_change",
      "rule": "if activation == 'always_on' then payload in ['leak_information','degrade_performance']",
      "rationale": "An always-on Trojan has no trigger gating its effect; any payload that alters observable function fails functional-equivalence verification. Only side-channel leakage and timing/power degradation can pass a functional testbench."
    }
  ]
}
```

**Versioning discipline (enforced in review, not code):** v2 MAY add new strings and bump `taxonomy_version`. v2 MUST NOT rename or repurpose any v1 string.

---

## 3. Sample directory contract (`data/samples/<sample_id>/`)

`<sample_id>` is a stable slug: `<source>__<circuit>__<trojanslug>` for infected, `<source>__<circuit>__clean` for clean (lowercase, `[a-z0-9_]+`, no spaces). A sample is either `clean` or `infected` (the manifest `class`, §4); the benchmark's negative class is a first-class sample, not a separate corpus. Each sample directory MUST contain exactly:

```
clean.v                # synthesizable RTL, single top module, original (clean) design
infected.v             # clean + ONE inserted Trojan; identical to clean.v except inserted logic.
                       #   For a clean sample, infected.v == clean.v byte-for-byte.
trojan_manifest.json   # generation-time ground truth (§4) — the source of truth. Carries class.
labels_rtl.json        # core RTL DFG labels by intrinsic handle (§6); {} for a clean sample
labels_netlist.json    # core netlist labels by intrinsic handle (§7); {} for clean  [absent in RTL-only mode]
metadata.json          # characterization + difficulty (§8-metadata)
graphs/
  dfg_rtl.json         # canonical RTL DFG, JSON (§9)
  netlist.json         # canonical gate-level netlist graph, JSON (§9)  [absent in RTL-only mode]
  index_map.v1.0.json  # CACHE: resolved handle->positional index for THIS dataset release (§8)
```

The filename `trojan_manifest.json` is retained for both classes for directory uniformity; for a clean sample it carries provenance and verification only (no taxonomy / inserted_rtl / generator). A clean sample's `graphs/dfg_rtl.json` and (full mode) `graphs/netlist.json` are REAL extracted/synthesized graphs from the same flow as infected samples, not empty placeholders (R8): the negative class must be structurally realistic so a model cannot separate clean from infected by graph emptiness. `index_map.v1.0.json` is a regenerable cache, versioned by dataset release tag.

---

## 4. `trojan_manifest.json` — schema

Produced at insertion time; authoritative ground truth. RTL labels (§6) are DERIVED from `inserted_rtl` here, never produced by keyword scanning. A top-level `class` discriminator gives the negative (clean) class a valid manifest.

JSON Schema (`spec/schemas/trojan_manifest.schema.json`), draft 2020-12:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ht-bench/schemas/trojan_manifest.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["sample_id","class","source","source_kind","license","license_url","circuit_family","variant_group","top_module","verification"],
  "properties": {
    "sample_id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
    "class": { "type": "string", "enum": ["clean","infected"] },
    "source": { "type": "string", "minLength": 1,
      "description": "Free-form provenance, e.g. 'opencores:uart16550', 'iscas85:c3540', 'picorv32', 'core', 'ghost'. No schema change to add a corpus. Optionally lint-checked against spec/sources.json." },
    "source_kind": { "type": "string", "enum": ["llm_generated","academic_benchmark","open_source_ip","vendor_ip"],
      "description": "Closed provenance axis. CORE/GHOST -> llm_generated; ISCAS/ITC-99/Trust-Hub -> academic_benchmark; OpenCores/RISC-V/OpenTitan -> open_source_ip; commercial -> vendor_ip." },
    "license": { "type": "string", "minLength": 1,
      "description": "SPDX identifier of the source circuit's license, e.g. 'Apache-2.0', 'ISC', 'BSD-3-Clause', 'CC-BY-4.0'. The license travels with the sample. Must be redistribution-compatible with the benchmark license (R10); a circuit whose license cannot be confirmed redistributable is rejected at intake." },
    "license_url": { "type": "string", "minLength": 1,
      "description": "URL to the source circuit's license text or origin repository, so provenance is auditable." },
    "circuit_family": { "type": "string",
      "description": "DESCRIPTIVE functional type (e.g. 'aes', 'uart', 'riscv_cpu'). For §7 coverage. NOT the split key." },
    "variant_group": { "type": "string", "minLength": 1,
      "description": "SPLIT-ATOMIC structurally-independent-design identity = same source code / same generator instance. Config variants share one; unrelated implementations of the same function get distinct ones; a standalone design gets a unique one. Splits never straddle a variant_group (§8)." },
    "top_module": { "type": "string" },

    "taxonomy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["taxonomy_version","taxonomy_ref","insertion_phase","insertion_level","activation","trigger_source","trigger_mechanism","payload"],
      "properties": {
        "taxonomy_version": { "type": "string", "const": "1.0" },
        "taxonomy_ref": { "type": "string" },
        "insertion_phase": { "type": "string", "const": "design" },
        "insertion_level": { "type": "string", "const": "rtl" },
        "activation": { "type": "string", "enum": ["always_on","triggered"] },
        "trigger_source": { "type": ["string","null"], "enum": ["internal","external",null] },
        "trigger_mechanism": { "type": ["string","null"], "enum": ["combinational","sequential_counter","sequential_fsm",null] },
        "payload": { "type": "string", "enum": ["modify_functionality","degrade_performance","leak_information","denial_of_service"] }
      }
    },

    "inserted_rtl": {
      "type": "object",
      "additionalProperties": false,
      "required": ["signals","line_ranges","module_instances"],
      "properties": {
        "signals": { "type": "array", "items": { "type": "string" },
          "description": "Fully-qualified signal names introduced by the Trojan, e.g. 'top.uart_rx.trojan_cnt[3]'. From structural diff of clean.v vs infected.v, NOT name patterns." },
        "line_ranges": { "type": "array", "items": { "type": "array", "items": { "type": "integer" }, "minItems": 2, "maxItems": 2 },
          "description": "[start,end] 1-based inclusive line ranges in infected.v that are Trojan logic (from the diff)." },
        "module_instances": { "type": "array", "items": { "type": "string" },
          "description": "Hierarchical instance paths of Trojan-only module instances, e.g. 'top.trojan_inst'. Empty if inlined." }
      }
    },

    "generator": {
      "type": "object",
      "additionalProperties": false,
      "required": ["model","prompt_hash","attempt_count"],
      "properties": {
        "model": { "type": "string", "description": "e.g. 'gemini-3.1-pro'. Use 'none' for non-LLM insertion." },
        "prompt_hash": { "type": "string", "description": "sha256 of the exact prompt; '0'*64 when model == 'none'." },
        "attempt_count": { "type": "integer", "minimum": 1 }
      }
    },

    "verification": {
      "type": "object",
      "additionalProperties": false,
      "required": ["compile_pass","synth_pass","sim_tool","synth_tool"],
      "properties": {
        "compile_pass": { "type": "boolean", "description": "valid Verilog (both classes)" },
        "synth_pass": { "type": "boolean", "description": "synthesizes cleanly on the pinned flow (both classes)" },
        "functional_equiv_pass": { "type": "boolean", "description": "infected==clean under normal (non-trigger) operation (infected only)" },
        "synth_survival_pass": { "type": "boolean", "description": "Trojan cells present in synthesized infected netlist (infected only)" },
        "activation_proof_pass": { "type": "boolean", "description": "trigger constructed and payload observed to fire (infected only)" },
        "sim_tool": { "type": "string" },
        "synth_tool": { "type": "string" }
      }
    }
  },

  "allOf": [
    {
      "if": { "properties": { "class": { "const": "infected" } }, "required": ["class"] },
      "then": { "required": ["taxonomy","inserted_rtl","generator"] },
      "else": { "properties": { "taxonomy": false, "inserted_rtl": false, "generator": false } }
    }
  ]
}
```

**Cross-field rules the validator MUST enforce beyond JSON Schema (R1–R10):**

- **R1.** (infected) If `activation == "always_on"` then `trigger_source == null` AND `trigger_mechanism == null`.
- **R2.** (infected) If `activation == "triggered"` then `trigger_source != null` AND `trigger_mechanism != null`.
- **R3.** (infected) Feasibility: if `activation == "always_on"` then `payload ∈ {"leak_information","degrade_performance"}`. Reject `modify_functionality` / `denial_of_service`.
- **R4.** Verification gate. Always: `compile_pass == true` AND `synth_pass == true`. When `class == "infected"`: ALSO `functional_equiv_pass`, `synth_survival_pass`, `activation_proof_pass` present and all `true`. Any required flag false or missing means a rejected sample that MUST NOT live under `data/samples/`.
- **R5.** (infected) If `source_kind == "llm_generated"` then `generator.model != "none"`. Other `source_kind` MAY use `model == "none"`.
- **R6.** Manifest-matches-files: if `class == "infected"`, the `[start,end]` line ranges of `diff(clean.v, infected.v)` MUST equal `inserted_rtl.line_ranges`. If `class == "clean"`, `diff(clean.v, infected.v)` MUST be empty.
- **R7.** Class consistency: `class == "clean"` ⇒ `taxonomy`, `inserted_rtl`, `generator` absent AND `labels_rtl.labels == {}` AND (`labels_netlist.labels == {}` when present). `class == "infected"` ⇒ all three present and `labels_rtl.labels` non-empty.
- **R8.** Negative-class realism: a `clean` sample's `graphs/dfg_rtl.json` and (full mode) `graphs/netlist.json` MUST be real graphs from the same extraction/synthesis flow as infected samples, with non-empty `nodes` and `edges`. The validator asserts non-empty node and edge counts for clean samples, blocking the trivial "empty graph ⇒ clean" separator.
- **R9.** AST-handle injectivity: the AST-derived handles of a sample MUST remain pairwise-distinct under any downstream tool name transform used in the benchmark (notably HW2VEC's). If a transform aliases two distinct handles, the sample is REJECTED at build time. A collision is a rejected sample, never a silently merged label. The validator enforces this via the HW2VEC shim's collision detector (§9 / `hw2vec_compat`).
- **R10.** License redistributability (intake gate): `license` MUST be a SPDX identifier in the redistribution allowlist of `spec/licenses.json` (compatible with the benchmark data license recorded there). A circuit whose license is absent, unconfirmed, or copyleft-incompatible (e.g. GPL/LGPL under a CC-BY benchmark) is REJECTED at intake — same posture as the verification gauntlet. The license must travel with every sample so downstream redistribution is auditable. This protects the redistribution the citation strategy depends on.

---

## 5. Provenance: `source`, `source_kind`, `spec/sources.json`

`source` is a free string and never gates a schema version. `source_kind` is the closed axis used in analysis and the paper (it supports findings like "detection holds on academic benchmarks but degrades on real open-source IP", which a raw corpus name cannot).

`spec/sources.json` is an APPENDABLE flat registry used by the validator ONLY for optional typo-linting (`--lint-sources`). Appending is NOT a schema-version event.

```json
{ "known_sources": ["core","ghost","trusthub","hw2vec","opencores","iscas85","iscas89","itc99","picorv32","ibex","opentitan"] }
```

---

## 6. `labels_rtl.json` — core RTL node labels by intrinsic handle

Stores ONLY `core` nodes (inversion #4). `neighborhood` and `clean` are computed at load (§8) from a `k` parameter; they are never persisted. Keyed by **intrinsic RTL handle**, never by DFG integer index. Two handle forms:

- Named signal node: fully-qualified name, e.g. `"top.uart_rx.trojan_cnt[3]"`.
- Unnamed intermediate-expression node: canonical signature `"expr:<op>(<canonical,fan-in,handles>)@<dest>:<child-index-path>"`, e.g. `"expr:xor(top.a,top.s)@top.y:1/2"`. Operand order is **canonical, not blindly sorted**: commutative operators (`And/Or/Xor/Xnor/Land/Lor/Plus/Times/Eq/NotEq`) sort their operands so identity is order-independent; non-commutative operators (`Minus/Divide/comparisons/Sll/Srl/Sra`, and structural nodes `DFBranch/DFConcat/DFPartselect/DFPointer`) preserve source operand order, because there `a-b` and `b-a` are distinct nodes and must not alias. The `<dest>:<path>` is the AST-structural position (binding destination plus child-index path); for commutative operators children are canonically reordered before the path is minted, so the path is invariant to Pyverilog's operand emission order. It replaces the source line — Pyverilog dataflow nodes do not carry line numbers, and structural position is in fact more stable (it does not shift when the file is edited).

**Handle provenance (normative).** The handle is derived from the Verilog AST via Pyverilog scoped signal names, computed on `infected.v` upstream of any downstream tool's preprocessing. It is explicitly NOT the HW2VEC DFG node name: HW2VEC's `remove_underscores()` / flatten transforms are lossy (e.g. `trojan_cnt` and `trojancnt` collapse) and tool-coupled, so they can never be the source of identity. Any downstream tool (HW2VEC included) is a consumer mapped onto these handles, never their source.

Schema (`labels_rtl.schema.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["sample_id","handle_scheme","labels"],
  "properties": {
    "sample_id": { "type": "string" },
    "handle_scheme": { "type": "string", "const": "rtl_signal_or_expr_signature" },
    "labels": {
      "type": "object",
      "description": "map: intrinsic_handle -> 'core'. Empty {} for a clean sample. neighborhood/clean are derived at load, never stored.",
      "additionalProperties": { "type": "string", "const": "core" }
    }
  }
}
```

The label generator MUST compute `core` purely from `trojan_manifest.inserted_rtl`. It MUST NOT inspect node names for keywords like "trojan"/"trigger". Strict vs neighborhood-aware evaluation is an adopter choice made at load time via `k`, which pre-empts the IoU-vs-neighborhood dispute without freezing `k` into storage.

---

## 7. `labels_netlist.json` — core netlist cell labels by intrinsic handle

Stores ONLY `core` cells (same as §6). Handle scheme is a discriminated union; the Phase-0.3 spike picks which `handle_scheme` populates it, so the schema shape freezes now:

- `hierarchy_path` — Trojan cells by preserved hierarchical instance path (`top.trojan_inst.*`); used when synthesis preserved the Trojan module boundary (`keep_hierarchy`).
- `structural_fingerprint` — canonical hash of the cell's local cone: `sha1(cell_type | sorted(fanin_fingerprints) | sorted(fanout_fingerprints))`; used with the structural-diff method on flattened netlists.

Yosys gensyms (`$abc$...`) and integer net bit-IDs MUST NOT appear as keys.

Schema (`labels_netlist.schema.json`):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["sample_id","handle_scheme","labels"],
  "properties": {
    "sample_id": { "type": "string" },
    "handle_scheme": { "type": "string", "enum": ["hierarchy_path","structural_fingerprint"] },
    "labels": { "type": "object", "additionalProperties": { "type": "string", "const": "core" } }
  }
}
```

The node/cell reference scheme and the Phase-0.3 netlist-labeling method are ONE decision, made together on the same 3–5 circuits, proven by the round-trip gate (§11) before any sample is generated at scale.

---

## 8. Referencing scheme + neighborhood-at-load: `resolve.py`, `metadata.json`

`resolve.py` MUST provide:

- `resolve_rtl(dfg_graph, labels_rtl) -> dict[int, str]` — maps the CURRENT extraction run's integer DFG indices to `"core"` by matching each node to its intrinsic handle. A handle that does not resolve raises a hard error (a label pointing at a non-existent node is corruption, not a warning).
- `resolve_netlist(netlist_graph, labels_netlist) -> dict[str, str]` — same on the netlist side.
- `neighborhood(graph, core_indices, k=2) -> set[int]` — derives the neighborhood set at load by k-hop traversal from core nodes. `k` is a caller parameter, default 2, never persisted. Strict evaluation uses core only; neighborhood-aware uses `core ∪ neighborhood(k)`.
- `build_index_map(sample_dir) -> writes graphs/index_map.v1.0.json` — regenerable cache mapping handle -> current positional index, so trainers get instant integer labels without re-resolving.

The integer index and the neighborhood set are both **ephemeral**: computed at load, never the source of truth.

`metadata.json` (`metadata.schema.json`), `additionalProperties: false`, required keys: `sample_id`, `n_nodes_rtl`, `n_edges_rtl`, `n_cells_netlist` (nullable in RTL-only mode), `area_um2` (nullable), `logic_depth` (nullable), `trigger_activation_prob` (nullable float), `difficulty_bin` (enum: `xs` <100 nodes, `s` 100–1k, `m` 1k–10k, `l` >10k), `split` (enum: `train`,`val`,`test`). `difficulty_bin` is a derived, recomputable reporting convenience (from `n_nodes_rtl`), not a per-node label. Optional key `elaboration` (round 8): RTL front-end provenance — `front_end ∈ {raw_pyverilog, yosys_elaborate}`, `sv2v_used`/`sv2v_version`, `yosys_version`, `top_module`, `chparams` (the config that produced this sample), `synthetic_nets`. Absent for raw-Verilog samples; present whenever the Yosys-elaboration front end (sv2v + `hierarchy -chparam`) produced the extracted Verilog, so a configured/SystemVerilog instance is reproducible. Frozen as an OPTIONAL block before the front end populates the corpus (same freeze-the-field-before-the-data discipline as the netlist handle union).

**Two distinct identity fields — `circuit_family` (descriptive) and `variant_group` (split-atomic).** These are different properties and must not be conflated (the same discipline as `source` vs `source_kind`):

- `manifest.circuit_family` is DESCRIPTIVE — functional type (`"aes"`, `"uart"`, `"riscv_cpu"`), for §7 coverage and reader intuition. Two unrelated AES implementations share `circuit_family: "aes"` and that is correct.
- `manifest.variant_group` is the SPLIT-ATOMIC key — structurally-independent-design identity: same source code / same generator instance. PicoRV32's config variants share one `variant_group`; Tiny-AES-OpenCores and AES-OpenTitan have DIFFERENT `variant_group`s even though both are `circuit_family: "aes"`; PicoRV32 and CVA6 have different `variant_group`s even though both are `circuit_family: "riscv_cpu"`. A standalone design gets its own unique `variant_group`.

**Split atomicity (frozen before any split is published — cannot be retrofitted).** Every sample sharing a `variant_group` MUST land in the same `split` (all train, or all test/val); official splits never straddle a `variant_group`. This stops near-identical config variants from leaking across train/test (the variant-level lift of the augmentation-leakage discipline). The corpus characterization MUST report the **distinct-`variant_group` count per bin** alongside the raw sample count — "120 large designs across 27 independent designs" is the auditable claim, because the large-circuit-gap finding rests on *structurally independent* designs, not distinct function labels. For the `l` bin the target is **≥100 samples spanning ≥25 distinct `variant_group`s**. A corpus-level validator check (not per-sample) MAY assert no `variant_group` straddles a split.

---

## 9. Canonical graph JSON (`graphs/dfg_rtl.json`, `graphs/netlist.json`)

Canonical graphs are JSON (inversion #2). The node feature space differs by abstraction, so the node schema is conditional on `graph_kind`: RTL DFG nodes carry the 38-class HW2VEC vocab code; netlist nodes carry the intrinsic standard-cell type string (the cell-type id is a derived, library-version-sensitive quantity and is therefore NOT stored, same principle as the index map). `graph.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["sample_id","graph_kind","nodes","edges"],
  "properties": {
    "sample_id": { "type": "string" },
    "graph_kind": { "type": "string", "enum": ["dfg_rtl","netlist"] },
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["handle"],
        "properties": {
          "handle": { "type": "string", "minLength": 1,
            "description": "Intrinsic handle; REQUIRED and UNIQUE within a graph. Joins to labels_*.json. A duplicated or empty handle silently breaks resolution by matching the wrong node, so the validator MUST assert uniqueness." }
        }
      }
    },
    "edges": {
      "type": "array",
      "items": { "type": "array", "items": { "type": "integer", "minimum": 0 }, "minItems": 2, "maxItems": 2 },
      "description": "[src_index, dst_index] into the nodes array (positional, internal to this file)."
    }
  },
  "allOf": [
    {
      "if": { "properties": { "graph_kind": { "const": "dfg_rtl" } }, "required": ["graph_kind"] },
      "then": { "properties": { "nodes": { "items": {
        "additionalProperties": false,
        "required": ["handle","x_code"],
        "properties": {
          "handle": { "type": "string", "minLength": 1 },
          "x_code": { "type": "integer", "minimum": 0, "maximum": 37,
            "description": "HW2VEC 38-class DFG vocabulary code (external, frozen vocab)." }
        } } } } }
    },
    {
      "if": { "properties": { "graph_kind": { "const": "netlist" } }, "required": ["graph_kind"] },
      "then": { "properties": { "nodes": { "items": {
        "additionalProperties": false,
        "required": ["handle","cell_type"],
        "properties": {
          "handle": { "type": "string", "minLength": 1 },
          "cell_type": { "type": "string", "minLength": 1,
            "description": "Intrinsic standard-cell type, e.g. 'sky130_fd_sc_hd__and4_2'. Cell-type id is derived at load against a versioned vocab, not stored." }
        } } } } }
    }
  ]
}
```

Edges use positional indices internal to the file; labels never do. `hw2vec_compat.to_hw2vec(graph_json) -> torch_geometric.data.Data` produces `x` (int64; from `x_code` for dfg_rtl, from a versioned cell-type vocab for netlist), `edge_index`, and `label` (the list of handles, ordered to match the node array), matching the format HW2VEC consumes. The README MUST state, bluntly, that the JSON is canonical and that no one may re-pickle it as the store of record.

---

## 9-mode. RTL-only mode

Build flag `--rtl-only`. The validator treats `labels_netlist.json`, `graphs/netlist.json`, and netlist fields in `metadata.json` as OPTIONAL. This lets v1 ship if the netlist-labeling spike is not yet clean; dual-abstraction becomes v1.1. NEVER ship approximate netlist labels to make the netlist files present. The round-trip gate still runs on the RTL side in this mode.

---

## 10. Validator CLI (`htbench validate`)

`htbench validate <path>` where path is a sample dir or `data/samples/`:

1. JSON-Schema-validate every file against its schema (including the per-`graph_kind` node-feature conditionals).
2. Enforce cross-field rules **R1–R10** (§4).
3. Enforce taxonomy feasibility constraints from `spec/taxonomy.json` (infected samples).
4. Assert label key schemes match the declared `handle_scheme`, that stored label values are `"core"` only, and that NO key matches forbidden patterns: integer-only keys, `/^\$/` (Yosys gensyms), `/^\d+$/` (net bit-IDs). Any such key is a hard FAIL naming the offending key.
5. Assert `handle` is present and UNIQUE within each graph file (§9). A duplicate or empty handle is a hard FAIL.
6. Resolve every label handle against the corresponding graph (§8). Unresolved handle = FAIL.
7. Optional `--lint-sources`: warn (not fail) if `source` is absent from `spec/sources.json`.
8. Exit non-zero on any failure; print a per-sample PASS/FAIL report with reasons. Support `--rtl-only`. Fast and CI-runnable on the whole corpus.

(The manifest-matches-files diff check is R6 and is enforced in step 2; it is no longer an unnumbered step.)

---

## 11. Round-trip invariance test (`htbench roundtrip`) — THE GATE

The test that retires the month-5 re-run risk. MUST pass before any sample is generated at scale.

`htbench roundtrip <sample_dir>`:

1. Load `dfg_rtl.json`, resolve labels -> set of intrinsic handles labeled `core`. Call this `A`.
2. Re-extract the DFG from `infected.v` from scratch (fresh extraction run), producing new integer indices.
3. Re-resolve the SAME `labels_rtl.json` against the freshly extracted graph -> set of handles labeled `core`. Call this `B`.
4. Assert `A == B`. Any difference = FAIL.
5. Repeat for netlist if present.

`--perturb` shuffles extraction traversal order before step 2, proving labels survive a regeneration they were never written to track. A clean sample (empty `core`) trivially satisfies `A == B == {}`; the gate still validates that its labels resolve. Wire both into `tests/test_roundtrip.py`.

The gate's extractor is the reference RTL extractor shipped in this package (`htbench.extract`), which derives handles via the shared handle-derivation function (`htbench.handles`). That function is the contract the later production extractor (§14) must also satisfy. For v1, `--perturb` means shuffled AST traversal order within the same Pyverilog front-end; true cross-front-end re-extraction (a second parser) is a v1.1 aspiration and is out of scope. The gate's guarantee is therefore "handles are traversal-order-independent", not "handles are parser-independent".

---

## 12. Test fixtures

Hand-build 5 mini samples under `tests/fixtures/`, each a tiny (<40-line) Verilog pair:

- (a) infected: `triggered`/`internal`/`sequential_counter`/`modify_functionality` — valid.
- (b) infected: `triggered`/`external`/`combinational`/`denial_of_service` — valid.
- (c) infected: `always_on`/`leak_information` — valid; doubles as a feasibility positive case.
- (d) INVALID infected: `always_on` + `modify_functionality` — the validator MUST reject via R3; asserted in `test_validate.py`.
- (e) clean: `class == "clean"`, `infected.v == clean.v`, no taxonomy/inserted_rtl/generator, `labels_rtl.labels == {}` — valid; exercises the negative-class path and R7.

Each valid fixture includes a correct manifest, label files, and graph JSON with unique handles. The clean fixture (e) carries non-empty `dfg_rtl.json` (and, in full mode, `netlist.json`) to exercise R8.

**Graph-schema negative fixtures** (in `tests/test_validate.py`, not full samples), proving the per-`graph_kind` `additionalProperties: false` branches are actually strict:
- (f) a `dfg_rtl` graph whose node carries BOTH `x_code` and `cell_type` MUST FAIL schema validation.
- (g) a `netlist` graph whose node carries `x_code` (wrong vocabulary) MUST FAIL schema validation.
If either passes, the conditional branches are tightened until they fail.

---

## 13. Definition of done

- All schemas emitted and self-consistent; `spec/taxonomy.json` and `spec/sources.json` present.
- `htbench validate`, `htbench roundtrip`, `resolve.neighborhood`, `hw2vec_compat.to_hw2vec` implemented, pip-installable, CI-wired.
- All five fixtures behave as specified (4 valid pass: a, b, c, e; 1 rejected for the right reason: d).
- Graph-schema negative fixtures (f, g) FAIL validation, proving the per-`graph_kind` node-feature branches are strict; clean fixture (e) asserts non-empty graphs (R8).
- Round-trip test passes including under `--perturb`, on both an infected and the clean fixture.
- `test_hw2vec_compat.py` asserts `to_hw2vec` round-trips: node count matches the JSON, `edge_index` shape matches the edge list, and `label` ordering aligns element-wise with the node array.
- `README.md` documents: sample contract incl. the clean/infected `class`, the "intrinsic handle, never positional index" rule, the "JSON canonical, pickle forbidden as store" rule, the "store core, derive neighborhood at load" rule, the taxonomy with citation, the `source` vs `source_kind` split, and how to run validate/roundtrip.

---

## 14. Out of scope for this work unit / for v1

- Circuit generation and LLM insertion (later work unit).
- Mixed-signal / analog Trojans (out of scope for v1 entirely).
- More than one Trojan per sample (v1 is single-Trojan).
- Gate-level INSERTION (v1 inserts at RTL only; `insertion_level` FIXED `rtl`).
- Any `other` / catch-all taxonomy value (forbidden by design).

---

## 15. Engineering resolutions folded in before freeze

**Review round 8 (2026-06-11) — elaboration provenance (folded in before the front end populates the corpus):** the Yosys-elaboration RTL front end (sv2v + `hierarchy -chparam`, §8/`elaborate.py`) turns a configured/SystemVerilog source into the Verilog-2005 the extractor sees. That transform must be reproducible per sample, but the frozen `metadata.json` (`additionalProperties:false`) had no home for it. Added an OPTIONAL `elaboration` block recording `front_end`, sv2v/yosys versions, `chparams`, `top_module`, `synthetic_nets`. Optional ⇒ raw-Verilog samples and existing fixtures stay valid; sv2v provenance and yosys-elaboration provenance land in ONE amendment because sv2v is becoming a standard normalization step (its parseability canary gates the l-floor). Same discipline as the netlist handle union: freeze the field before the data populates it.

**Review round 1 (2026-06-10):** (1) JSON canonical, HW2VEC view via converter, pickle forbidden as store. (2) Graph nodes carry a required, unique `handle`; validator asserts uniqueness. (3) `source` free string + closed `source_kind`; appendable `sources.json` lint registry. (4) RTL-only mode confirmed compatible with the round-trip gate.

**Review round 2 (2026-06-10):**
- **A. Negative class.** Added a top-level `class ∈ {clean, infected}` discriminator. `taxonomy`/`inserted_rtl`/`generator` are required only for infected (JSON-Schema if/then). `verification` splits into always-required `compile_pass`/`synth_pass` plus infected-only `functional_equiv_pass`/`synth_survival_pass`/`activation_proof_pass`. Clean samples carry empty `core` labels. A GNN detection benchmark now has a schema for its negative class.
- **B. Rule numbering.** The manifest-matches-files diff check is now R6; class consistency is R7. Validator enforces R1–R7; no unnumbered checks remain.
- **C. `to_hw2vec` acceptance test.** Added `test_hw2vec_compat.py` (node count, edge_index shape, label-ordering alignment) so inversion #2's safety claim is tested, not asserted.
- **D. Netlist feature vocabulary.** `graph.schema.json` node features are now conditional on `graph_kind`: `x_code ∈ [0,37]` for `dfg_rtl`; intrinsic `cell_type` string for `netlist`. One schema no longer carries a wrong-vocabulary feature.
- **E. Neighborhood not persisted.** Label files store `core` only; `neighborhood` is computed at load from a `k` parameter (`resolve.neighborhood`, default 2). The one research-sensitive parameter stays out of frozen storage, consistent with inversion #1.

**Review round 3 (2026-06-10):**
- **Conditional-schema strictness (proven, not trusted).** Added graph-schema negative fixtures (f, g): a `dfg_rtl` node with both `x_code` and `cell_type`, and a `netlist` node with `x_code`, MUST fail validation. Because `graph_kind` is enum-bound to two values, exactly one `if/then` branch always fires and its `additionalProperties: false` rejects the stray key; the base `nodes.items` is deliberately permissive (adding `additionalProperties: false` there would forbid `x_code`/`cell_type` and break the conditional). The fixtures prove the prose.
- **Negative-class realism (decided + R8).** Clean samples carry real synthesized netlists and real DFGs from the identical flow, non-empty, so the negative class is not trivially separable by graph emptiness. New rule R8; validator asserts non-empty clean-sample graphs.
- **Verification schema/sample-validity divergence (accepted).** The three infected-only verification flags are optional in JSON Schema and required-and-true only via R4, exactly as R1–R3 push taxonomy semantics past the schema. A file can be schema-valid yet sample-invalid; the validator is the sample-validity authority by design. Inherited consciously, no change.

**Review round 7 (2026-06-10) — split the conflated identity field:**
- **`circuit_family` (descriptive) vs `variant_group` (split-atomic).** Round 6 reused `circuit_family` as the split key, but that field carries two meanings that provably diverge: two unrelated AES cores share `circuit_family: "aes"` yet are independent (should split); two RISC-V generators share `"riscv_cpu"` yet are different sources. The leakage-atomic property is source/generator identity, not function. Conflating them silently breaks one guarantee (inflated/deflated family count, or a variant-group leaking across a split) with no error — the quiet-corruption signature this project refuses. Fix (same discipline as `source`/`source_kind`): keep `circuit_family` descriptive, add required `variant_group` = structurally-independent-design identity. Splits bind on `variant_group`; the ≥25 floor counts distinct `variant_group`s. Last load-bearing schema decision before sourcing.

**Review round 6 (2026-06-10) — split atomicity, surfaced while ruling on the l-bin config-variant policy:**
- **Split atomicity introduced (§8).** Copyleft exclusions (round 5) make the l-bin floor reachable only with config variants of parameterized cores, near-identical structural twins that would leak across train/test (the exact failure Nina's thesis identified with resynthesis augmentation) and make the "large-circuit generalization gap" headline a leakage artifact. Frozen now because splits cannot be retrofitted: variants in one split-atomic group, splits never straddle it, distinct-group count per bin reported, `l` bin ≥100 samples across ≥25 groups. (Round 6 keyed this on `circuit_family`; round 7 corrected the key to a dedicated `variant_group`.)

**Review round 5 (2026-06-10) — surfaced while scoping Phase-1 corpus sourcing:**
- **License intake gate (R10).** Before ingesting real IP from five source families with five license regimes (OpenCores mixed GPL/LGPL/BSD, ISCAS/ITC-99 academic, RISC-V ISC/Apache, crypto often encumbered), the contract gains `license` + `license_url` provenance fields (required, both classes) and a redistributability allowlist in `spec/licenses.json`. License-compatibility is a hard intake gate: a circuit whose license cannot be confirmed redistribution-compatible with the benchmark data license is rejected, same posture as the verification gauntlet. Frozen BEFORE ingestion because it is a schema touch; deferring it risks a month-4 relicense/rip-out-and-rebalance, and is the one thing that could threaten the redistribution the citation strategy depends on.

**Review round 4 (2026-06-10) — surfaced while planning the `htbench` implementation:**
- **Handle provenance is AST-derived (§6, normative).** Planning exposed that the only on-hand extractor (HW2VEC) flattens and strips underscores, so its DFG node names are flat, lossy, and tool-coupled (`trojan_cnt`/`trojancnt` collapse). Using them as handles would silently violate the §9 uniqueness guarantee. Fixed: the handle is derived from the Verilog AST (Pyverilog scoped names), upstream of any tool preprocessing; HW2VEC is a downstream consumer mapped onto handles, never their source.
- **R9 injectivity.** New rule: AST handles must remain pairwise-distinct under any downstream tool name transform, or the sample is rejected at build time (a collision is a rejected sample, never a merged label). Enforced by the `hw2vec_compat` collision detector. Header and §10 step 2 now read R1–R9.
- **§11/§14 circularity resolved.** The round-trip gate uses a *reference* extractor (`htbench.extract`) shipped in the enforcement work unit, not the deferred production extractor; both are clients of the shared handle-derivation function (`htbench.handles`), which is the real contract. `--perturb` is scoped to intra-front-end traversal shuffling for v1; cross-front-end re-extraction is v1.1.
