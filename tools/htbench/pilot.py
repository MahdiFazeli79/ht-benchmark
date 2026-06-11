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


# Verilog keywords kept verbatim in the structural signature (everything else that
# looks like an identifier is a signal name and gets canonicalized).
_VERILOG_KEYWORDS = frozenset({
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "logic",
    "assign", "always", "always_comb", "always_ff", "begin", "end", "if", "else",
    "case", "casez", "endcase", "posedge", "negedge", "or", "and", "not", "xor",
    "xnor", "nand", "nor", "parameter", "localparam", "integer", "genvar",
    "generate", "endgenerate", "for", "initial", "default", "signed", "unsigned"})


def _structural_signature(text: str) -> str:
    """Rename-robust signature of the inserted Trojan text — the near-dup key.

    Verilog keywords/operators are kept; magic-constant literals (`8'hC7`) collapse
    to LIT; IDENTIFIERS (signal names) are canonicalized to id0,id1,... by first
    appearance. So two structurally-identical Trojans with renamed signals — and
    with different trigger constants — hash the SAME, catching the mode collapse a
    text hash would miss.

    BLIND SPOTS (disclosed, not silently absorbed): it canonicalizes ALL identifiers
    including host-signal refs, so structurally-identical Trojans keying *different*
    host nets also cluster (acceptable for mode-collapse detection, but it over-merges
    host targets); and deeper structural equivalence — statement reordering, logically
    equal but different shape — is NOT caught. That needs DFG-isomorphism on the
    insertion graph, a documented follow-up."""
    norm = re.sub(r"\s+", " ", text.strip())
    norm = re.sub(r"\d+'[sS]?[bodhBODH][0-9a-fA-FxzXZ?_]+", "LIT", norm)   # magic literals
    mapping: dict[str, str] = {}

    def repl(m):
        tok = m.group(0)
        if tok == "LIT" or tok.lower() in _VERILOG_KEYWORDS:
            return tok
        return mapping.setdefault(tok, f"id{len(mapping)}")

    canon = re.sub(r"[A-Za-z_]\w*", repl, norm)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _attempt1_sig(result):
    """Structural signature of a sample's ATTEMPT-1 inserted text, by the SAME
    rename-robust function as the final-accept signature so the two are comparable.
    None when attempt 1 never produced a valid structural diff (parse error / empty
    diff) — nothing to cluster, distinct from a real collapse hit."""
    added = result.attempt1_added_text
    return _structural_signature("\n".join(added)) if added else None


def build_manifest(sample_id, spec, result, *, model, prompt_hash, license, license_url,
                   circuit_family, variant_group, sim_tool="iverilog", synth_tool="yosys",
                   temperature=None, prompt_version=None):
    """Construct a schema-valid infected trojan_manifest.json. `inserted_rtl.line_ranges`
    comes from the SAME structural diff the validator's R6 uses, so it passes by
    construction; the round-10 grade rides in `verification`. `temperature` (when the
    client pins one) is recorded in `generator` so sampling conditions are recoverable
    per sample; omitted when None so pre-pin manifests stay byte-identical."""
    grade = result.verification or {}
    verification = {"compile_pass": True, "synth_pass": True,
                    "functional_equiv_pass": True, "synth_survival_pass": True,
                    "activation_proof_pass": True, "sim_tool": sim_tool, "synth_tool": synth_tool}
    for k in ("activation_proof_method", "reachability_established", "divergence_attribution"):
        if k in grade:
            verification[k] = grade[k]
    generator = {"model": model, "prompt_hash": prompt_hash, "attempt_count": result.attempts}
    if temperature is not None:
        generator["temperature"] = temperature
    if prompt_version is not None:
        generator["prompt_version"] = prompt_version
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
        "generator": generator,
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


_QUARANTINE_README = (
    "# Rejected samples — NOT corpus\n\n"
    "These samples failed the gauntlet and are NOT part of the benchmark. They are kept\n"
    "as data about the GENERATOR (why insertion failed, per attempt) for diagnosis. A\n"
    "corpus loader must never read this directory.\n")


def write_quarantine(quarantine_dir, sample_id, clean_rtl, spec, result) -> Path:
    """Persist a rejected sample's full per-attempt trail to a quarantine directory —
    never the corpus dir. Each attempt's infected RTL and witness (or the raw response
    when it did not parse) land on disk alongside a trail.json of reason + tokens +
    cost per attempt, so the failure mechanism can be confirmed without paying to
    regenerate it. Marked NOT-corpus by construction."""
    qroot = Path(quarantine_dir)
    qroot.mkdir(parents=True, exist_ok=True)
    readme = qroot / "README_NOT_CORPUS.md"
    if not readme.exists():
        readme.write_text(_QUARANTINE_README)
    d = qroot / sample_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "clean.v").write_text(clean_rtl)
    attempts = []
    for r in result.trail:
        if r.infected_rtl is not None:
            (d / f"attempt{r.attempt}_infected.v").write_text(r.infected_rtl)
        if r.witness is not None:
            (d / f"attempt{r.attempt}_witness.json").write_text(json.dumps(r.witness, indent=2))
        if r.raw_text is not None:
            (d / f"attempt{r.attempt}_raw.txt").write_text(r.raw_text)
        attempts.append({"attempt": r.attempt, "reason": r.reason,
                         "in_tokens": r.in_tokens, "out_tokens": r.out_tokens,
                         "cost_usd": round(r.cost_usd, 6),
                         "parsed": r.infected_rtl is not None})
    (d / "trail.json").write_text(json.dumps({
        "sample_id": sample_id, "class": "rejected_noncorpus",
        "top_module": spec.top_module, "taxonomy_cell":
            f"{spec.activation}/{spec.trigger_mechanism}/{spec.payload}",
        "final_reason": result.reason, "cost_usd": round(result.cost_usd, 6),
        "attempts": attempts}, indent=2))
    return d


@dataclass
class PilotReport:
    accepted: list = field(default_factory=list)   # {sample_id, cell, sig, method, witness}
    rejected: list = field(default_factory=list)   # {cell, reason} — model failed the gauntlet
    errors: list = field(default_factory=list)     # {cell, error} — infra/API failure, NOT a reject
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

    def attempt1_collapse_clusters(self):
        """Near-dup clusters over ATTEMPT-1 inserted text (same-prompt by construction),
        pooling accepted AND rejected samples. This reads base-sampling collapse free of
        repair-path divergence: final-accept clustering (near_duplicate_clusters) measures
        the as-stored corpus, but for a sample whose attempt 1 rejected and was steered,
        the accepted attempt-2 output carries its own repair history, so identical specs
        no longer share a prompt. Attempt-1 outputs do, so the collapse signal and the
        v2-fix measurement stop contaminating each other."""
        clusters = defaultdict(list)
        for s in (*self.accepted, *self.rejected):
            sig = s.get("attempt1_sig")
            if sig:
                clusters[sig].append(s["sample_id"])
        return {sig: ids for sig, ids in clusters.items() if len(ids) > 1}

    def method_spread(self):
        return dict(Counter(a.get("method") for a in self.accepted))

    def trojan_only_reject_rate(self):
        if not self.rejected:
            return 0.0
        n = sum(1 for r in self.rejected if "not applicable to clean" in r["reason"])
        return n / len(self.rejected)

    def steered_count(self):
        """Samples whose loop hit a Trojan-internal witness and got the v2 steering."""
        return (sum(1 for a in self.accepted if a.get("steered"))
                + sum(1 for r in self.rejected if r.get("steered")))

    def steering_conversion_rate(self):
        """Of the witnesses the v2 steering fired on (rejected Trojan-internal on an
        early attempt), the fraction that converted to an accept. The decision input
        for the v3 escalation: high ⇒ general steering suffices; low ⇒ the
        net-naming variant is the next versioned change. Returns None when the
        steering never fired (nothing to measure), distinct from a 0% conversion."""
        total = self.steered_count()
        if not total:
            return None
        return sum(1 for a in self.accepted if a.get("steered")) / total

    def render(self) -> str:
        L = ["# Phase-2 pilot report\n"]
        L.append("> SCOPE: hosts are toy self-authored modules (8-bit adder/mux/…). This"
                 " pilot validates the PIPELINE and the COST MODEL, **not** insertion"
                 " feasibility on realistic cores — synth-survival and insertion difficulty"
                 " on a toy host do not generalize (a Trojan there can be folded away or"
                 " trivially preserved in ways a real core won't).\n")
        L.append(f"- spent: ${self.spent_usd:.4f}" + (f"  ABORTED: {self.aborted}" if self.aborted else ""))
        L.append(f"- attempted: {self.attempted}  accepted: {len(self.accepted)}  "
                 f"yield: {self.yield_rate:.0%}\n")
        L.append("## Taxonomy spread (accepted)")
        for cell, n in sorted(self.taxonomy_spread().items()):
            L.append(f"- {cell}: {n}")
        L.append("\n## Activation-proof method spread")
        L.append("(sequential cells are EXPECTED to grade state_injection / "
                 "reachability=false by design — host-register witnesses, the round-10 "
                 "weaker-evidence tier, not a defect. See docs/batch2_expectations.md.)")
        for m, n in sorted(self.method_spread().items(), key=lambda x: str(x[0])):
            L.append(f"- {m}: {n}")
        dups = self.near_duplicate_clusters()
        L.append(f"\n## Near-duplicate clusters (final accepted): {len(dups)}")
        for sig, ids in dups.items():
            L.append(f"- {sig}: {ids}")
        a1 = self.attempt1_collapse_clusters()
        L.append(f"\n## Collapse clusters (attempt-1, same-prompt; accepted+rejected): {len(a1)}")
        L.append("(repair-path-free base-sampling collapse signal — read THIS for the "
                 "sequential repeat-probe, the final-accept clusters above for the as-stored corpus)")
        for sig, ids in a1.items():
            L.append(f"- {sig}: {ids}")
        L.append(f"\n## Trojan-only-signal reject rate: {self.trojan_only_reject_rate():.0%} "
                 f"(of {len(self.rejected)} rejects) — high ⇒ self-referential witnesses")
        conv = self.steering_conversion_rate()
        conv_str = "n/a (steering never fired)" if conv is None else f"{conv:.0%}"
        L.append(f"\n## v2 steering conversion rate: {conv_str} "
                 f"(of {self.steered_count()} steered witnesses) — accepts after a Trojan-internal "
                 f"reject; low ⇒ escalate to the net-naming variant (v3)")
        L.append("\n## Per-sample cost (USD)")
        for s in (*self.accepted, *self.rejected):
            c = s.get("cost_usd")
            tag = "" if s in self.accepted else " (rejected)"
            L.append(f"- {s.get('sample_id', s.get('cell'))}: "
                     f"{'n/a' if c is None else f'${c:.4f}'}{tag}")
        if self.errors:
            L.append(f"\n## Infra/API errors (NOT model rejects): {len(self.errors)}")
            for e in self.errors:
                L.append(f"- {e['cell']}: {e['error']}")
        L.append("\n## Testbench-artifact spot-check (witnesses for manual review)")
        for a in self.accepted[:5]:
            L.append(f"- {a['sample_id']}: {a['witness']}")
        return "\n".join(L)


# --- proposed pilot spec set (for review; self-authored hosts, no download) ----- #

_HOSTS = {
    "add8": "module add8(input [7:0] a, input [7:0] b, output [8:0] sum);\n  assign sum = a + b;\nendmodule\n",
    "mux2x8": "module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);\n  assign y = sel ? b : a;\nendmodule\n",
    "cmp8": "module cmp8(input [7:0] a, input [7:0] b, output gt);\n  assign gt = (a > b);\nendmodule\n",
    "shift8": "module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);\n  assign y = d << sh;\nendmodule\n",
    "counter8": ("module counter8(input clk, input rst_n, input en, output reg [7:0] count);\n"
                 "  always @(posedge clk or negedge rst_n) if(!rst_n) count<=0; else if(en) count<=count+1;\n"
                 "endmodule\n"),
    # second SEQUENTIAL host (batch 2): host-state register `acc` gives the v2
    # steering a host-observable signal to key the witness on, so the fix isn't
    # validated only against counter8.
    "accum8": ("module accum8(input clk, input rst_n, input en, input [7:0] din,\n"
               "               output reg [7:0] acc);\n"
               "  always @(posedge clk or negedge rst_n)\n"
               "    if(!rst_n) acc <= 8'b0; else if(en) acc <= acc + din;\n"
               "endmodule\n"),
    # larger self-authored host (batch 2): a multi-op ALU, materially more source
    # than the toy hosts, so the prompt-token-vs-cost slope can be measured (an
    # intermediate cost point; a real-core point needs a separately-gated download).
    "alu8": ("module alu8(input [7:0] a, input [7:0] b, input [2:0] op,\n"
             "           output reg [7:0] y, output reg cout, output zero);\n"
             "  always @(*) begin\n"
             "    cout = 1'b0;\n"
             "    case(op)\n"
             "      3'd0: {cout, y} = a + b;\n"
             "      3'd1: {cout, y} = a - b;\n"
             "      3'd2: y = a & b;\n"
             "      3'd3: y = a | b;\n"
             "      3'd4: y = a ^ b;\n"
             "      3'd5: y = ~a;\n"
             "      3'd6: y = a << 1;\n"
             "      3'd7: y = a >> 1;\n"
             "    endcase\n"
             "  end\n"
             "  assign zero = (y == 8'b0);\n"
             "endmodule\n"),
}
_FAMILY = {"add8": "adder", "mux2x8": "mux", "cmp8": "comparator",
           "shift8": "shifter", "counter8": "counter",
           "accum8": "accumulator", "alu8": "alu"}

# (host, activation, trigger_source, trigger_mechanism, payload). Designed for a
# ~12-sample budget: SPAN the taxonomy (2 activations, 3 trigger mechanisms, 4
# payloads, 5 hosts) AND REPEAT one cell across 4 hosts so near-dup clustering can
# detect mode collapse (the LLM emitting the same Trojan shape). All R1-R3 feasible.
_PILOT_CELLS = [
    # mode-collapse probe (amended): 3 IDENTICAL-spec repeats (same host + cell) so
    # clustering is unambiguous — same prompt, identical hash = real collapse, with no
    # signature-over-merge confound. Plus 1 cross-host instance of the same cell to
    # CHARACTERIZE the over-merge (does the signature merge across hosts?) rather than
    # be fooled by it. (Running rows 1-4 as 4 different hosts would make the probe's
    # positive signal indistinguishable from the signature's known false positive.)
    ("add8", "triggered", "internal", "combinational", "degrade_performance"),
    ("add8", "triggered", "internal", "combinational", "degrade_performance"),
    ("add8", "triggered", "internal", "combinational", "degrade_performance"),
    ("mux2x8", "triggered", "internal", "combinational", "degrade_performance"),
    # breadth across payloads / trigger sources (combinational)
    ("add8", "triggered", "internal", "combinational", "modify_functionality"),
    ("mux2x8", "triggered", "external", "combinational", "leak_information"),
    ("cmp8", "triggered", "internal", "combinational", "denial_of_service"),
    # sequential trigger mechanisms (host-state → state-injection proofs)
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    ("counter8", "triggered", "internal", "sequential_fsm", "modify_functionality"),
    # always-on (R3-feasible payloads only)
    ("add8", "always_on", None, None, "leak_information"),
    ("shift8", "always_on", None, None, "degrade_performance"),
    # one external-trigger combinational for trigger-source spread
    ("shift8", "triggered", "external", "combinational", "modify_functionality"),
]


def default_pilot_specs(license="CC-BY-4.0",
                        license_url="https://creativecommons.org/licenses/by/4.0/"):
    """The proposed pilot spec set (for review). Self-authored small hosts, no
    download. Each InsertionSpec is R1-R3-checked at construction, so an infeasible
    cell would raise here, not reach the prompt."""
    specs = []
    for i, (host, act, tsrc, tmech, payload) in enumerate(_PILOT_CELLS, 1):
        spec = I.InsertionSpec(_HOSTS[host], host, act, tsrc, tmech, payload)
        meta = {"license": license, "license_url": license_url,
                "circuit_family": _FAMILY[host], "variant_group": f"pilot_{host}"}
        specs.append((f"pilot_{i:03d}_{host}", _HOSTS[host], spec, meta))
    return specs


# --- proposed BATCH-2 spec set (for review; self-authored hosts, no download) --- #

# Batch 2 answers three load-bearing questions in one ~12-sample budget (see
# docs/batch2_expectations.md): (a) does prompt_v2 recover sequential yield, (b) is
# mode collapse uniform or cell-dependent, (c) what is the prompt-token cost slope.
# All R1-R3 feasible at construction. The RUN is Tier-3 (gated in the run session).
_BATCH2_CELLS = [
    # (a) sequential-fix validation + collapse probe on a SEQUENTIAL cell. Three
    # IDENTICAL repeats of the EXACT pilot-1 reject cell, now under v2 steering: the
    # conversion-rate metric reads these, near-dup clustering reads collapse here.
    # Expect state_injection / reachability=false grades (host-register witnesses) —
    # design, not defect.
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    # the other pilot-1 sequential reject (second mechanism), one instance
    ("counter8", "triggered", "internal", "sequential_fsm", "modify_functionality"),
    # second sequential HOST so the fix is not validated only on counter8
    ("accum8", "triggered", "internal", "sequential_counter", "degrade_performance"),
    # (b) collapse-breadth probe cell #2: 3 identical combinational repeats
    ("mux2x8", "triggered", "internal", "combinational", "degrade_performance"),
    ("mux2x8", "triggered", "internal", "combinational", "degrade_performance"),
    ("mux2x8", "triggered", "internal", "combinational", "degrade_performance"),
    # collapse-breadth probe cell #3: 3 identical combinational repeats
    ("cmp8", "triggered", "internal", "combinational", "denial_of_service"),
    ("cmp8", "triggered", "internal", "combinational", "denial_of_service"),
    ("cmp8", "triggered", "internal", "combinational", "denial_of_service"),
    # (c) cost-scaling point: one larger self-authored host (intermediate, not a real
    # core — a real-core cost point needs a separately-gated download). One sample.
    ("alu8", "triggered", "internal", "combinational", "modify_functionality"),
]


def batch2_specs(license="CC-BY-4.0",
                 license_url="https://creativecommons.org/licenses/by/4.0/"):
    """The proposed batch-2 spec set (for review). Sequential cells under prompt_v2,
    repeat-probes on three cells for collapse breadth, one larger host for the cost
    slope. Self-authored hosts, no download. R1-R3-checked at construction. The
    variant_group keys on host SOURCE (pilot_<host>), not batch, so batch-1 and
    batch-2 samples of the same host correctly share a split-atomic group."""
    specs = []
    for i, (host, act, tsrc, tmech, payload) in enumerate(_BATCH2_CELLS, 1):
        spec = I.InsertionSpec(_HOSTS[host], host, act, tsrc, tmech, payload)
        meta = {"license": license, "license_url": license_url,
                "circuit_family": _FAMILY[host], "variant_group": f"pilot_{host}"}
        specs.append((f"batch2_{i:03d}_{host}", _HOSTS[host], spec, meta))
    return specs


# --- targeted sequential re-run (c): just the 5 cells that failed batch 2, under --- #
# full instrumentation, to confirm the mechanism (divergence-window vs Trojan-internal
# witness) with the failing RTL in the quarantine dir. ~$0.15 at observed rates. The
# RUN is Tier-3 (gated in the run session). Same hosts/cells as batch 2's sequential
# subset, so variant_group still keys on host source.
_SEQ_RECHECK_CELLS = [
    # the 3 identical counter8 repeats (mechanism + collapse-on-sequential), the exact
    # batch-2 reject cell — 3 independent attempts at the same wall
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    ("counter8", "triggered", "internal", "sequential_counter", "denial_of_service"),
    # the second mechanism, and the second host — so the read isn't counter8-only
    ("counter8", "triggered", "internal", "sequential_fsm", "modify_functionality"),
    ("accum8", "triggered", "internal", "sequential_counter", "degrade_performance"),
]


def sequential_recheck_specs(license="CC-BY-4.0",
                             license_url="https://creativecommons.org/licenses/by/4.0/"):
    """The (c) re-run spec set (for review): batch 2's 5 sequential cells, nothing
    else. Under full instrumentation (per-attempt trail, quarantine, divergence-cycle
    diagnostic), each failure self-classifies and a divergence-window failure reports
    its fix parameter. R1-R3-checked at construction. variant_group keys on host
    source (pilot_<host>), shared with batch 1/2."""
    specs = []
    for i, (host, act, tsrc, tmech, payload) in enumerate(_SEQ_RECHECK_CELLS, 1):
        spec = I.InsertionSpec(_HOSTS[host], host, act, tsrc, tmech, payload)
        meta = {"license": license, "license_url": license_url,
                "circuit_family": _FAMILY[host], "variant_group": f"pilot_{host}"}
        specs.append((f"seqrecheck_{i:03d}_{host}", _HOSTS[host], spec, meta))
    return specs


def run_pilot(specs, out_dir, *, api_model, pricing_key, total_usd_cap, per_run_usd_cap,
              yield_floor=0.20, yield_window=10, min_attempts_before_floor=8,
              client=None, max_repairs=3, quarantine_dir=None) -> PilotReport:
    """METERED — makes paid calls. Invoke ONLY after the operator sets
    ANTHROPIC_API_KEY and re-confirms caps in the live session.

    `specs` is an iterable of ``(sample_id, clean_rtl, InsertionSpec, manifest_meta)``
    where manifest_meta carries license/license_url/circuit_family/variant_group.
    Stops on YieldFloorAbort or BudgetExceeded (records the abort). Rejected samples
    are quarantined (full per-attempt trail) to `quarantine_dir`, defaulting to a
    sibling ``<out_dir>_rejected`` — never the corpus dir."""
    I.load_env()
    out_dir = str(out_dir)
    quarantine_dir = quarantine_dir or (out_dir.rstrip("/") + "_rejected")
    Path(out_dir).mkdir(parents=True, exist_ok=True)     # always exists (for the report/cleanliness)
    guard = CG.CostGuard(total_usd_cap, per_run_usd_cap, yield_floor,
                         yield_window, min_attempts_before_floor)
    if client is None:
        client = I.AnthropicClient(model=api_model)      # the only paid path
    sampling_temperature = getattr(client, "temperature", None)   # logged per manifest (None ⇒ omitted)
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
        except Exception as e:                       # API/SDK/infra error — record, keep going
            report.errors.append({"cell": cell, "error": f"{type(e).__name__}: {e}"})
            continue
        if res.accepted:
            write_sample(out_dir, sample_id, clean_rtl, spec, res,
                         model=api_model, prompt_hash=prompt_hash,
                         temperature=sampling_temperature,
                         prompt_version=I.PROMPT_VERSION, **meta)
            report.accepted.append({
                "sample_id": sample_id, "cell": cell,
                "sig": _structural_signature("\n".join(res.ground_truth["added_text"])),
                "attempt1_sig": _attempt1_sig(res),
                "method": (res.verification or {}).get("activation_proof_method"),
                "steered": res.steered, "cost_usd": res.cost_usd, "witness": res.activation})
        else:
            write_quarantine(quarantine_dir, sample_id, clean_rtl, spec, res)   # diagnosis, not corpus
            report.rejected.append({"sample_id": sample_id, "cell": cell, "reason": res.reason,
                                    "attempt1_sig": _attempt1_sig(res), "steered": res.steered,
                                    "cost_usd": res.cost_usd})
    report.spent_usd = guard.spent_usd
    return report
