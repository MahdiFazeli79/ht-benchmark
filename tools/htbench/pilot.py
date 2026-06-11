"""Phase-2 pilot driver (HELD at the key-and-caps gate — the run is Tier-3).

Wires the engine end to end: real AnthropicClient → generate_sample with the
gauntlet as `verify` → write each accepted sample (clean.v, infected.v, a
schema-valid trojan_manifest.json carrying the round-10 grade, the activation
witness) → emit the pilot REPORT (taxonomy spread, near-duplicate clustering,
testbench-artifact spot-check data, and the Trojan-only-signal reject rate — a
high rate there flags self-referential witnesses from the prompt).

NOTHING here makes a paid call on import. `run_pilot()` is the ONLY metered code
and is invoked only AFTER the operator sets ANTHROPIC_API_KEY themselves and
re-confirms the caps in the live session — never by reference to a past one. The
verify adapter, manifest writer, and report are mock-tested at zero cost.

Scope note: a pilot sample is the lightweight measurement artifact (sources +
manifest + witness). Full schema-complete sample assembly (graphs/dfg_rtl.json,
labels_rtl.json, metadata.json via the extractor) is the production step after
the pilot validates the engine's yield.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import cost_guard as CG
from . import gauntlet as G
from . import insertion as I


def gauntlet_verify(clean, infected, spec, gt, activation):
    """Adapt the gauntlet to the engine's `verify` signature, carrying the
    round-10 grade in `Verdict.detail` so it reaches the manifest on accept."""
    v = G.run_full(clean, infected, spec.top_module, activation)
    return I.Verdict(v.ok, v.reason, detail=v.detail or {})


def _signature(text: str) -> str:
    """Whitespace-normalized hash of the inserted Trojan text — exact/near-dup key
    for clustering (fuzzy similarity is a documented follow-up)."""
    return hashlib.sha256(re.sub(r"\s+", " ", text.strip()).encode()).hexdigest()[:16]


def build_manifest(sample_id, spec, result, *, model, prompt_hash, license, license_url,
                   circuit_family, variant_group, sim_tool="iverilog", synth_tool="yosys"):
    """Construct a schema-valid infected trojan_manifest.json. `inserted_rtl.line_ranges`
    comes from the SAME structural diff the validator's R6 uses, so it passes by
    construction; the round-10 grade rides in `verification`."""
    grade = result.verification or {}
    verification = {"compile_pass": True, "synth_pass": True,
                    "functional_equiv_pass": True, "synth_survival_pass": True,
                    "activation_proof_pass": True, "sim_tool": sim_tool, "synth_tool": synth_tool}
    for k in ("activation_proof_method", "reachability_established", "divergence_attribution"):
        if k in grade:
            verification[k] = grade[k]
    return {
        "sample_id": sample_id, "class": "infected",
        "source": f"llm:{model}", "source_kind": "llm_generated",
        "license": license, "license_url": license_url,
        "circuit_family": circuit_family, "variant_group": variant_group,
        "top_module": spec.top_module,
        "taxonomy": {"taxonomy_version": "1.0", "taxonomy_ref": "Karri/Trust-Hub",
                     "insertion_phase": "design", "insertion_level": "rtl",
                     "activation": spec.activation, "trigger_source": spec.trigger_source,
                     "trigger_mechanism": spec.trigger_mechanism, "payload": spec.payload},
        "inserted_rtl": {"signals": [], "line_ranges": result.ground_truth["line_ranges"],
                         "module_instances": []},
        "generator": {"model": model, "prompt_hash": prompt_hash, "attempt_count": result.attempts},
        "verification": verification,
    }


def write_sample(out_dir, sample_id, clean_rtl, spec, result, **manifest_kw) -> Path:
    d = Path(out_dir) / sample_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "clean.v").write_text(clean_rtl)
    (d / "infected.v").write_text(result.infected_rtl)
    (d / "trojan_manifest.json").write_text(
        json.dumps(build_manifest(sample_id, spec, result, **manifest_kw), indent=2))
    (d / "activation_witness.json").write_text(json.dumps(result.activation, indent=2))
    return d


@dataclass
class PilotReport:
    accepted: list = field(default_factory=list)   # {sample_id, cell, sig, method, witness}
    rejected: list = field(default_factory=list)   # {cell, reason}
    spent_usd: float = 0.0
    aborted: str = ""                              # "" or the abort reason

    @property
    def attempted(self):
        return len(self.accepted) + len(self.rejected)

    @property
    def yield_rate(self):
        return len(self.accepted) / self.attempted if self.attempted else 0.0

    def taxonomy_spread(self):
        return dict(Counter(a["cell"] for a in self.accepted))

    def near_duplicate_clusters(self):
        clusters = defaultdict(list)
        for a in self.accepted:
            clusters[a["sig"]].append(a["sample_id"])
        return {sig: ids for sig, ids in clusters.items() if len(ids) > 1}

    def method_spread(self):
        return dict(Counter(a.get("method") for a in self.accepted))

    def trojan_only_reject_rate(self):
        if not self.rejected:
            return 0.0
        n = sum(1 for r in self.rejected if "not applicable to clean" in r["reason"])
        return n / len(self.rejected)

    def render(self) -> str:
        L = ["# Phase-2 pilot report\n"]
        L.append(f"- spent: ${self.spent_usd:.4f}" + (f"  ABORTED: {self.aborted}" if self.aborted else ""))
        L.append(f"- attempted: {self.attempted}  accepted: {len(self.accepted)}  "
                 f"yield: {self.yield_rate:.0%}\n")
        L.append("## Taxonomy spread (accepted)")
        for cell, n in sorted(self.taxonomy_spread().items()):
            L.append(f"- {cell}: {n}")
        L.append("\n## Activation-proof method spread")
        for m, n in sorted(self.method_spread().items(), key=lambda x: str(x[0])):
            L.append(f"- {m}: {n}")
        dups = self.near_duplicate_clusters()
        L.append(f"\n## Near-duplicate clusters: {len(dups)}")
        for sig, ids in dups.items():
            L.append(f"- {sig}: {ids}")
        L.append(f"\n## Trojan-only-signal reject rate: {self.trojan_only_reject_rate():.0%} "
                 f"(of {len(self.rejected)} rejects) — high ⇒ self-referential witnesses")
        L.append("\n## Testbench-artifact spot-check (witnesses for manual review)")
        for a in self.accepted[:5]:
            L.append(f"- {a['sample_id']}: {a['witness']}")
        return "\n".join(L)


def run_pilot(specs, out_dir, *, api_model, pricing_key, total_usd_cap, per_run_usd_cap,
              yield_floor=0.20, yield_window=10, min_attempts_before_floor=8,
              client=None, max_repairs=3) -> PilotReport:
    """METERED — makes paid calls. Invoke ONLY after the operator sets
    ANTHROPIC_API_KEY and re-confirms caps in the live session.

    `specs` is an iterable of ``(sample_id, clean_rtl, InsertionSpec, manifest_meta)``
    where manifest_meta carries license/license_url/circuit_family/variant_group.
    Stops on YieldFloorAbort or BudgetExceeded (records the abort)."""
    I.load_env()
    guard = CG.CostGuard(total_usd_cap, per_run_usd_cap, yield_floor,
                         yield_window, min_attempts_before_floor)
    if client is None:
        client = I.AnthropicClient(model=api_model)      # the only paid path
    report = PilotReport()
    for sample_id, clean_rtl, spec, meta in specs:
        cell = f"{spec.activation}/{spec.trigger_mechanism}/{spec.payload}"
        prompt_hash = hashlib.sha256(I.build_prompt(spec).encode()).hexdigest()[:16]
        try:
            res = I.generate_sample(spec, client, guard, gauntlet_verify,
                                    model=pricing_key, max_repairs=max_repairs)
        except CG.YieldFloorAbort as e:
            report.aborted = f"yield-floor: {e}"
            break
        except CG.BudgetExceeded as e:
            report.aborted = f"budget: {e}"
            break
        if res.accepted:
            write_sample(out_dir, sample_id, clean_rtl, spec, res,
                         model=api_model, prompt_hash=prompt_hash, **meta)
            report.accepted.append({
                "sample_id": sample_id, "cell": cell,
                "sig": _signature("\n".join(res.ground_truth["added_text"])),
                "method": (res.verification or {}).get("activation_proof_method"),
                "witness": res.activation})
        else:
            report.rejected.append({"cell": cell, "reason": res.reason})
    report.spent_usd = guard.spent_usd
    return report
