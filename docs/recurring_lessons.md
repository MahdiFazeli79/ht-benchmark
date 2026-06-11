# Recurring lessons

Cross-session engineering lessons for TROVE. These are the traps that don't
announce themselves and tend to recur in a different costume each time. The
handoff's "Standing discipline" is the per-session checklist; this file is the
durable record the checklist is drawn from. Append a dated line when a session
surfaces a new one; keep each entry to the failure and the guard.

## Verification

- **Green in the wrong env is a skip masquerading as a pass — verify the
  interpreter before trusting the count.** (2026-06-11) A pilot-era run reported
  `103 passed, 5 skipped` because `conda activate gnn-hwsec` silently failed and
  the base interpreter ran the suite; the toolchain tests (yosys / iverilog /
  pyverilog) skipped instead of running. The real count in `gnn-hwsec` was `125
  passed, 0 skipped`. A skip count above zero on a suite that has toolchain tests
  is the tell. Check `which python` (or run with the env's explicit interpreter
  path) and confirm `0 skipped` before trusting a local-green. CI catches it
  after the fact; this catches it before the push. Sibling of the standing rule
  "CI-green is authoritative; never call a gate green on local alone."

## Provenance

- **Do not backfill metadata that was never logged.** (2026-06-11) When the
  temperature field was added (round-11 schema amendment), the ten already
  committed pilot manifests were left without it rather than backfilled with
  `temperature: 1.0`. The default in effect at run time was indeed 1.0, so the
  value would have been technically true, but writing it would claim a logged
  value that was never logged: provenance-false. The honest corpus state is "that
  run did not record it"; the new field is optional so old samples stay valid.
  The store-objective discipline applied to the project's own metadata, not just
  its labels.
