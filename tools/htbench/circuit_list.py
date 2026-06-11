"""Phase-1 circuit-list gate (task #28): the reviewable pre-download manifest.

A *circuit-list manifest* names the candidate IP to source for the corpus, one
row per (`variant_group`, `source`). It is the artifact reviewed BEFORE the
download boundary is crossed: nothing is cloned until this list passes the gate
and Mahdi approves it. The exclusions (`rejected`) are shown deliberately — they
are the audit trail for the §2/§9 license-rigor paragraph.

This module IS the gate. It:
  - validates every row (required fields, `parse_path`/`bin` enums, unique
    `variant_group`);
  - runs the R10 license allowlist (`spec/licenses.json` — the SAME source of
    truth `htbench.validate` uses on samples), marking rows whose license is not
    redistributable as download-BLOCKED (default-closed: `unconfirmed` blocks);
  - computes the review metrics ("the four headline numbers": l-bin distinct
    `variant_group` floor, homogeneity, reject count, sv2v share) so the review
    rests on COMPUTED values, not hand-maintained ones that silently drift.

Pure: `check_circuit_list` operates on a parsed dict and an allowlist set, so it
is testable without PyYAML or the filesystem. YAML loading is an optional front
door (CLI `htbench check-list`).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PARSE_PATHS = {"verilog_direct", "sv2v", "chisel_gen", "EXCLUDE"}
BINS = {"xs", "s", "m", "l"}
REQUIRED = ("variant_group", "circuit_family", "source",
            "license", "language", "parse_path", "bin")

# The ≥25 l-bin floor is RETIRED (Branch B, spec round 9). The sv2v→R9 canary
# confirmed the SystemVerilog large designs are parseable, so 15 is the genuine,
# complete count — and permissive, large, independent, parseable RTL is simply
# scarce in the open ecosystem. We report all distinct large families the gated
# ecosystem yields, honestly, with the count; we do NOT pad toward a target. The
# old floor is kept only as a reference line in the report.
L_FLOOR_GROUPS_RETIRED = 25
L_FLOOR_SAMPLES = 100


def load_allowlist(spec_dir: str | Path = "spec") -> set[str]:
    data = json.loads((Path(spec_dir) / "licenses.json").read_text())
    return set(data["redistributable_allowlist"])


@dataclass
class CircuitListReport:
    errors: list = field(default_factory=list)          # structural (blocking)
    blocked: list = field(default_factory=list)         # (variant_group, license) R10-blocked
    n_candidates: int = 0
    n_eligible: int = 0                                 # candidates passing R10
    n_rejected: int = 0                                 # rows in the `rejected` section
    bin_distinct: dict = field(default_factory=dict)    # bin -> distinct variant_group count
    l_distinct: int = 0
    top_family: tuple = ("", 0.0)
    riscv_share: float = 0.0
    opentitan_share: float = 0.0
    sv2v_share: float = 0.0
    chisel_share: float = 0.0

    @property
    def structurally_valid(self) -> bool:
        """True if the manifest is well-formed. R10-blocked rows do NOT make it
        invalid — they are simply not download-eligible until their license is
        confirmed."""
        return not self.errors

    def render(self) -> str:
        L = []
        L.append("# Phase-1 circuit-list gate report (PRE-DOWNLOAD)\n")
        L.append("**Nothing ingested.** This is the reviewable artifact.\n")
        status = "well-formed" if self.structurally_valid else "STRUCTURAL ERRORS"
        L.append(f"- manifest: **{status}**")
        L.append(f"- candidates: {self.n_candidates}  "
                 f"(download-eligible after R10: **{self.n_eligible}**, "
                 f"blocked: {len(self.blocked)})")
        L.append(f"- rejected-on-intake: {self.n_rejected}\n")

        L.append("## The four headline numbers\n")
        L.append("| # | Metric | Value | Verdict |")
        L.append("|---|---|---|---|")
        v1 = (f"ecosystem yield (≥{L_FLOOR_GROUPS_RETIRED} floor RETIRED — "
              f"Branch B, scarcity documented)")
        L.append(f"| 1 | l-bin distinct independent families | {self.l_distinct} | {v1} |")
        homog = self.riscv_share + self.opentitan_share
        v2 = "OK" if homog < 0.70 else "RISK — homogeneous"
        L.append(f"| 2 | Homogeneity (RISC-V {self.riscv_share:.0%} + "
                 f"OpenTitan {self.opentitan_share:.0%}) | {homog:.0%} | {v2} |")
        L.append(f"| 3 | Rejected-on-intake | {self.n_rejected} | audit trail |")
        L.append(f"| 4 | SystemVerilog → needs sv2v | {self.sv2v_share:.0%} | "
                 f"pipeline dependency |\n")

        L.append("## Distinct `variant_group` per bin\n")
        for b in ("xs", "s", "m", "l"):
            L.append(f"- {b}: {self.bin_distinct.get(b, 0)}")
        L.append("")

        if self.blocked:
            L.append("## R10-blocked (cannot be cloned until license confirmed)\n")
            for vg, lic in self.blocked:
                L.append(f"- `{vg}` — license `{lic}` not on the redistributable allowlist")
            L.append("")

        if self.errors:
            L.append("## Structural errors (fix before review)\n")
            for e in self.errors:
                L.append(f"- {e}")
            L.append("")
        return "\n".join(L)


def check_circuit_list(data: dict, allowlist: set[str]) -> CircuitListReport:
    """Validate a parsed circuit-list manifest and compute review metrics.

    `data` is ``{"candidates": [...], "rejected": [...], "meta": {...}}``.
    `allowlist` is the R10 redistributable license set (see `load_allowlist`).
    """
    rep = CircuitListReport()
    candidates = list(data.get("candidates") or [])
    rejected = list(data.get("rejected") or [])
    rep.n_candidates = len(candidates)
    rep.n_rejected = len(rejected)

    seen_groups: set[str] = set()
    eligible = 0
    for i, row in enumerate(candidates):
        tag = row.get("variant_group", f"<row {i}>")
        for f in REQUIRED:
            if not str(row.get(f, "")).strip():
                rep.errors.append(f"{tag}: missing required field '{f}'")
        pp = row.get("parse_path")
        if pp not in PARSE_PATHS:
            rep.errors.append(f"{tag}: parse_path '{pp}' not in {sorted(PARSE_PATHS)}")
        elif pp == "EXCLUDE":
            rep.errors.append(f"{tag}: parse_path EXCLUDE belongs in 'rejected', not 'candidates'")
        if row.get("bin") not in BINS:
            rep.errors.append(f"{tag}: bin '{row.get('bin')}' not in {sorted(BINS)}")
        vg = row.get("variant_group")
        if vg:
            if vg in seen_groups:
                rep.errors.append(f"{tag}: duplicate variant_group (must be unique in candidates)")
            seen_groups.add(vg)
        # R10 — default-closed: anything not explicitly on the allowlist blocks.
        lic = row.get("license", "")
        if lic in allowlist:
            eligible += 1
        else:
            rep.blocked.append((vg or tag, lic))
    rep.n_eligible = eligible

    # Metrics over ALL candidate rows (the list as proposed), matching the
    # review's headline tally. Each row is one variant_group, so per-bin distinct
    # == per-bin row count once uniqueness is enforced above.
    n = max(rep.n_candidates, 1)
    bin_counts = Counter(r.get("bin") for r in candidates)
    rep.bin_distinct = {b: bin_counts.get(b, 0) for b in BINS}
    rep.l_distinct = bin_counts.get("l", 0)

    fam_counts = Counter(r.get("circuit_family") for r in candidates)
    if fam_counts:
        fam, cnt = fam_counts.most_common(1)[0]
        rep.top_family = (fam, cnt / n)
    rep.riscv_share = sum(1 for r in candidates
                          if r.get("circuit_family") == "riscv_cpu") / n
    rep.opentitan_share = sum(1 for r in candidates
                              if "opentitan" in str(r.get("source", "")).lower()) / n
    rep.sv2v_share = sum(1 for r in candidates
                         if r.get("parse_path") == "sv2v") / n
    rep.chisel_share = sum(1 for r in candidates
                           if r.get("parse_path") == "chisel_gen") / n
    return rep


def load(path: str | Path) -> dict:
    """Load a YAML circuit-list manifest (optional dependency: PyYAML)."""
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise ImportError("check-list needs PyYAML: pip install 'tools/[manifest]'") from e
    return yaml.safe_load(Path(path).read_text())
