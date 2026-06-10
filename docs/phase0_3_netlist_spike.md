# Phase-0.3 Netlist-Labeling Spike — Findings & Decision

**Date:** 2026-06-10. **Question:** which netlist-labeling method, and therefore
which `labels_netlist.handle_scheme` (`hierarchy_path` vs `structural_fingerprint`),
should v1 use — or should netlist labeling descope to v1.1?

**Test circuit:** `core_johnson_counter` (clean, 9 cells) vs
`core_johnson_counter_HT2` (infected, 33 cells), a time-bomb Trojan
(`trojantimer` 8-bit counter + `trojanactivebomb` comparator + count-freeze
mux). Synthesized identically with local Yosys 0.65, `synth -top top -flatten`.

## Method (a) — hierarchy boundary: INFEASIBLE

The synthesis flow (OpenLane/Yosys + ABC on sky130hd) flattens to a single `top`
module of flat cell instances. No `keep_hierarchy`; a Trojan cannot be confined
to a preserved module boundary without re-architecting the flow. So
`hierarchy_path` handles do not exist. Ruled out.

## Method (b) — structural diff: finds everything, but conflates inserted-with-perturbed

WL-style iterative color refinement (3 rounds; invariant to gensym renaming;
handles sequential feedback) over the cell graph, diffing infected vs clean by
signature multiset:

| metric | value |
|---|---|
| clean cells | 9 |
| infected cells | 33 |
| WL-flagged "added" | 33 (100%) |
| ground-truth Trojan-net-touching cells | 23 |
| **recall** | **1.00** |
| precision | 0.70 (10 benign cells also flagged) |

**Read this as a ground-truth-definition gap, not a method failure.** Recall is
1.00 — the diff finds every Trojan cell. The 10 "false positives" are benign
count-register cells that are *genuinely* structurally different in the infected
netlist, because the Trojan reroutes `count` through the time-bomb mux. Asking
"are those cells Trojan or benign?" has no tool-independent answer: they are
benign logic the Trojan materially altered. This is the same core-vs-neighborhood
ambiguity already solved at RTL (store `core`, derive `neighborhood` at load),
reappearing at the netlist level as **directly-inserted cells vs.
synthesis-perturbed cells**. 0.70 precision against a *strict* ground truth is
the signature of that ambiguity, not evidence the method cannot localize.

**Caveat on what this spike actually tested.** It ran the *blind* diff: generic
Yosys synthesis with NO keep anchoring on the inserted nets. It did not test the
manifest-anchored method (see v1.1 below), which is the more likely winner. The
spike ruled out the method it could test, not the method most likely to work.

## The deciding constraint — no stable, spec-compliant netlist handle

Even granting a perfect labeler, v1 needs a **re-extraction-stable, circuit-intrinsic
handle** so netlist labels pass the round-trip gate. None is available:

| candidate | verdict |
|---|---|
| `hierarchy_path` | infeasible — flow flattens |
| `structural_fingerprint` (WL), used ALONE | non-injective — distinct cells share single-cell signatures, so it cannot be identity *by itself* (violates §9 / R9). NOT ruled out as a *component*: an **anchored** fingerprint (cell identified by its manifest-known driving net + local cone) may well be injective. Door stays open for v1.1. |
| Yosys gensym | deterministic within pinned tool+input (verified: identical across two runs), but spec-forbidden tool-coordinate (`/^\$/`), and shifts on any tool-version or source change — violates inversion #1 and the cross-regeneration aspiration |

A named net DOES survive (`trojantimer`), so a **manifest-driven keep-anchored
labeling method is viable** — and it sidesteps the structural-handle problem
entirely (see v1.1). The single-cell-handle search above is the wrong frame: the
intrinsic identity is "the cell(s) the manifest says I inserted," not a structural
coordinate.

## Decision

**Descope netlist labeling to v1.1; ship v1 as `--rtl-only`.** This matches the
plan's explicit go/no-go gate ("if neither method is clean, ship RTL-only labels
in v1 and make dual-abstraction v1.1; do NOT ship approximate netlist labels")
and the current `htbench` behavior. The netlist schema, validator support, and
`to_hw2vec` netlist branch stay in place, exercised only by the graph-schema
negative fixtures, until v1.1.

## What v1.1 must solve (the real research task)

Not "a missing handle" and not "a failed diff." The proven-viable path is
**manifest-anchored keep labeling**: `trojantimer` survived synthesis as a named
net, so anchoring labels to the manifest's inserted signals — forced to survive
via `(* keep *)` attributes — gives an intrinsic, synthesis-survivable identity
("the cell(s) driven by the net the manifest says I inserted"), sidestepping the
structural-handle problem. The spike did NOT test this (it ran blind diff without
keep anchoring), so v1.1's first task is to prove manifest-anchored labeling
end-to-end.

The genuine open problem is then the **core-vs-perturbation ground-truth
definition** — the netlist analogue of the already-solved RTL core/neighborhood
split: label directly-inserted cells as netlist-`core`, synthesis-perturbed cells
as netlist-`neighborhood`, derived at load. (Recall 1.00 in this spike means the
diff already surfaces both sets; the task is to *split* them, not to find them.)

Handle candidates remaining open: (1) the manifest-known kept-net anchor itself
as the cell identity; (2) an **anchored** structural fingerprint (kept-net anchor
+ local cone) — non-injectivity was a property of the *single-cell* fingerprint
used alone, not of an anchored one; (3) a canonical-naming synthesis pass that
propagates RTL net names onto cells.
