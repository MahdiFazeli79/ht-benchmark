# Drive-to-state activation-proof — design for review

The seqrecheck (c) artifacts proved the sequential wall is a parser-expressivity
ceiling, not the prompt and not the TB sample window: the model emits correct,
reachable, input-driven witnesses ("drive en=1 until count reaches 8'hA5"), but
`parse_witness` only does single-shot `sig=val` — apply for input ports, FORCE for
everything else. Forcing the host register the payload manipulates masks the payload;
forcing a Trojan-internal net fails against clean. The fix locus is the activation-
proof: drive the design to the trigger state via inputs over time, instead of forcing.

**This doc is for review. The CODE is gated on the admissibility decision below — not
on this doc landing.** Build starts only after that position is settled.

## 0. The decision that gates everything (settle this first)

Drive-to-state quietly redefines admissibility. If the only way to witness a trigger
is to reach it by driving inputs within a cycle budget, then **a Trojan must be input-
reachable within that budget to be admissible**. A 32-bit-counter trigger is
"reachable" only in principle (billions of cycles); under a budget it is a reject.

This is a benchmark-design position with corpus-size and taxonomy consequences, not a
bugfix. It must be decided explicitly:

> **Is input-reachability-within-budget the corpus admissibility rule, with "reachable
> but not within budget" a first-class reject class — distinct from masking and from
> structural?**

Lean (yours, and it holds up): yes — a Trojan you cannot activate from the ports is
weak as a detection benchmark anyway, so the tightening is a feature. Consequences to
accept if so:

- **Corpus size:** deep-trigger Trojans (wide-counter / long-FSM triggers) drop out.
  Likely small, but real, and it shows in per-mechanism yield.
- **Taxonomy:** `not-reachable-in-budget` becomes a reported reject class, the same
  honest-scarcity pattern as the large-IP story — "these trigger depths are excluded
  at budget B," disclosed, not silently dropped.
- **Grading tier:** sequential accepts now grade `input_driven` + `reachability_
  established=true` (the stronger tier the witnesses already describe), not
  `state_injection`. The round-10 weaker-evidence branch becomes the exception, not
  the norm.
- **Budget B** is a published constant (proposal: B = 1024 cycles for the pilot hosts;
  revisit per host class). It is the number the admissibility claim is relative to.

Everything below (schema fields, grading, the third reject class) falls out of this
answer. If the answer is "no, keep forced-state too," the schema still needs the drive
path but masking stays a live failure mode and the admissibility story is muddier.
**Recommendation: adopt input-reachability-within-budget; build the drive path; keep
forced-state only as an explicitly-graded weaker fallback, not the default.**

## 1. Witness schema v2 — a SUPERSET of v1 (must not regress the 7)

v1 (`sig=val`, free text) becomes the degenerate zero-length-drive case. The schema
expresses a *drive*, with the static single-vector witness as `budget=0`:

- `held_inputs`: input-port assignments held constant during the drive (e.g. `en=1`).
  For a combinational Trojan this is the whole trigger vector (`a=8'hDE, b=8'hAD`).
- `reach_predicate`: a predicate over **host-observable** signals to drive to (e.g.
  `count == 8'hA5`). `None` for combinational (the held vector IS the trigger).
- `settle_cycles`: extra cycles to hold the inputs after the predicate is met, for an
  internal FSM to arm (the model already states this — "keep en=1 for 3 edges"). This
  reaches the armed state WITHOUT naming the internal net.
- `budget`: max drive cycles before declaring `not-reachable-in-budget` (default B).
- `observe_cycles`: divergence window after settle (reuses the round-12 diagnostic).

Degeneracy is the regression guarantee: a combinational witness parses to
`reach_predicate=None, budget=0`, drives zero cycles, applies the vector, observes once
— byte-for-byte the v1 decision path. Parsing stays lenient/fail-loud.

## 2. Activation-proof drive-to-state

1. Parse the witness to (`held_inputs`, `reach_predicate`, `settle_cycles`, `budget`,
   `observe_cycles`). If a referenced signal is neither an input nor a host-observable
   net of clean → **structural** reject (the trigger can only be named on the infected
   design; it is not input-expressible).
2. Generate ONE testbench, run on clean and infected identically: reset, hold
   `held_inputs`, clock up to `budget` cycles checking `reach_predicate` each cycle.
   - predicate never true within budget → **not-reachable-in-budget** reject.
   - predicate true at cycle T → hold `settle_cycles` more, then observe `observe_
     cycles`, comparing clean vs infected (the SHARED `_mismatches`).
     - diverge → ACCEPT, grade `input_driven` + `reachability_established=true`.
     - no divergence in the window → **masking / unobservable** reject (trigger reached
       but the effect never surfaces at an output — degenerate witness or unobservable
       payload).

No `force` on the decision path → masking-by-force is gone by construction. Forced-
state survives only as an explicitly-graded weaker fallback iff §0 keeps it.

## 3. Three distinct reject reasons (so the next quarantine round classifies itself)

- `structural: witness names a signal absent from clean and not an input` — the schema
  can't express this via the ports (Trojan-internal trigger).
- `not-reachable-in-budget: predicate <P> not met within <B> cycles` — the trigger is
  genuinely deep; a benchmark-admissibility reject, not a harness limit.
- `masking/unobservable: trigger reached at cycle <T>, no divergence in <W>` — the
  payload can't be witnessed at the outputs.

Each is a different action next round; conflating them is what cost us the first read.

## 4. Regression gate — don't trust the new path until the old corpus survives it

Before the new harness is trusted, run **every currently-accepted sample** (pilot 1 +
batch 2, the combinational accepts) through it as a gate:

- All combinational accepts MUST still accept via the zero-length-drive degenerate path.
- Any sample that accepted in v1 only via a `force` the new harness now forbids MUST
  break **loudly** (re-classify as a reject), never silently re-accept on a different
  basis — a silent re-accept would hide a changed admissibility basis in the corpus.

This is a test, committed with the code: load the accepted manifests, re-run activation-
proof v2, assert the combinational set is unchanged and flag any divergence for review.

## 5. Build order (after §0 is answered)

1. Schema v2 + lenient parser, with the v1 degenerate-case regression test (no toolchain).
2. Drive-to-state activation-proof + the three reason strings (toolchain tests:
   reach-and-diverge accept, not-reachable-in-budget, masking, structural).
3. The corpus regression gate (§4).
4. A re-run of seqrecheck (c) under v2 — Tier-3, gated — to confirm the 001/003 freeze
   Trojans now accept as `input_driven`/reachable, and to see how many of the 5 are
   genuinely `not-reachable-in-budget` vs recovered.

## 6. Cross-link — what this corrects from last round

The sequential "collapse" filed under cell-dependent generator behavior in
`diversification_decision.md` was substantially this parser-expressivity ceiling, not
generator diversity — the model was emitting correct reachable witnesses the harness
discarded at parse time. So: the per-cell collapse-rate finding carries an asterisk for
sequential cells, and **no diversification effort (including multi-model) will move a
single sequential cell until drive-to-state lands.** Diversification stays a
combinational-cell concern until the witness model is fixed.
