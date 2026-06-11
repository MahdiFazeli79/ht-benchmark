# Diversification mechanism — decision

Decision set 2026-06-11, after two paid pilots. This one does not wait on more
data: the collapse-breadth question has a consistent answer across both runs.

## Evidence

Mode collapse (the model emitting the same Trojan shape on identical prompts) is
**cell-dependent, not taxonomy-wide**:

- add8 (pilot 1): collapsed.
- cmp8 (batch 2): collapsed (3/3 identical attempt-1 signature).
- mux2x8 (batch 2): did NOT collapse (three distinct Trojans).
- counter8 (batch 2): did NOT collapse.

Two batches agree: some cells collapse, others produce diverse output under the
same prompt at temperature 1.0.

### Asterisk (2026-06-11, after seqrecheck) — sequential "collapse" was largely a parser ceiling

The sequential repeat-probe's apparent behavior was substantially a parser-
expressivity ceiling, NOT generator diversity. The seqrecheck (c) artifacts showed the
model emitting correct, reachable, input-driven witnesses that `parse_witness`
discarded at parse time (it forces non-input signals, masking host-register payloads).
So the per-cell collapse-rate finding above is sound for the **combinational** cells
(add8, cmp8, mux2x8) but carries an asterisk for sequential cells: their accept/reject
behavior was dominated by the harness, not the generator. Consequence for this
decision: **no diversification effort, including the multi-model escalation, will move
a single sequential cell until drive-to-state lands** (`docs/drive_to_state_design.md`)
— the generator was already producing distinct, valid witnesses. Diversification is a
combinational-cell concern until the witness model is fixed.

## Decision

**Over-generate-and-dedup is the v1 diversification mechanism.** It is the
proportionate answer to a cell-dependent problem: it removes duplicates on the
collapsing cells and costs nothing on the diverse ones (nothing to discard). It
does not pay the heavyweight cost of multi-model insertion to solve a problem only
some cells have.

**Multi-model insertion is the documented escalation**, taken only if dedup-discard
rates come back high at scale (i.e. over-generation has to throw away too much to
hit target counts, making a second generator cheaper than the waste).

## Consequence — the dedup quality check moves onto the critical path

The corpus-level dedup check was parked as a post-gauntlet quality gate ("after the
gauntlet, before scaling"). It is no longer just a hygiene gate: it IS the
diversification mechanism. Its structural-signature key (the rename-robust signature
already used for near-dup clustering, the same one that read the collapse signal) is
the seed. Promoting it from report instrument to a generation-loop validator (over-
generate N, keep the structurally-distinct ones, discard the rest) is the build.

## Reporting

Per-cell collapse rates become a reported finding in the paper, not an internal
note — the same honest-scarcity pattern as the large-IP story: a measured property
of the generator, disclosed, with the mechanism that handles it. The dedup-discard
rate at scale is the number that would justify the multi-model escalation.

## Status

Direction set; build not started. Independent of the sequential-mechanism work
(the gauntlet-TB-timing vs v3 question), which is gated behind the targeted
sequential re-run with the failing artifacts in hand.
