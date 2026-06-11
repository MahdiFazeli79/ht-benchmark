"""Pilot report + manifest builder (pure — no toolchain, light CI job)."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from htbench import pilot as P
from htbench import insertion as I

SCHEMA = Draft202012Validator(json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "schemas" / "trojan_manifest.schema.json").read_text()))


def _result():
    return I.InsertionResult(
        True, "module m(input a, output y);\n  wire t;\n  assign y = a;\nendmodule\n",
        {"line_ranges": [[2, 2]], "added_text": ["  wire t;"]}, 2,
        activation={"trigger": "a==8'hDE", "observable_effect": "y flips"},
        verification={"activation_proof_method": "input_driven",
                      "reachability_established": True, "divergence_attribution": "trigger_only"})


def _spec():
    return I.InsertionSpec("module m...", "m", "triggered", "internal", "combinational",
                           "degrade_performance")


def test_build_manifest_is_schema_valid_and_carries_grade():
    man = P.build_manifest("s_001", _spec(), _result(), model="claude-sonnet-x",
                           prompt_hash="abc123", license="MIT",
                           license_url="https://opensource.org/licenses/MIT",
                           circuit_family="adder", variant_group="pilot_add8")
    assert [e.message for e in SCHEMA.iter_errors(man)] == []
    assert man["class"] == "infected"
    assert man["verification"]["activation_proof_method"] == "input_driven"
    assert man["verification"]["divergence_attribution"] == "trigger_only"
    assert man["inserted_rtl"]["line_ranges"] == [[2, 2]]    # from the structural diff
    assert "temperature" not in man["generator"]            # omitted when not pinned (pre-pin manifests unchanged)


def test_build_manifest_logs_temperature_when_pinned():
    man = P.build_manifest("s_001", _spec(), _result(), model="claude-sonnet-x",
                           prompt_hash="abc123", license="MIT",
                           license_url="https://opensource.org/licenses/MIT",
                           circuit_family="adder", variant_group="pilot_add8",
                           temperature=1.0)
    assert [e.message for e in SCHEMA.iter_errors(man)] == []  # optional field stays schema-valid
    assert man["generator"]["temperature"] == 1.0             # sampling condition recorded per sample


def test_build_manifest_logs_prompt_version_when_set_and_omits_when_none():
    common = dict(model="claude-sonnet-x", prompt_hash="abc123", license="MIT",
                  license_url="https://opensource.org/licenses/MIT",
                  circuit_family="adder", variant_group="pilot_add8")
    with_v = P.build_manifest("s_001", _spec(), _result(), prompt_version="v2", **common)
    assert [e.message for e in SCHEMA.iter_errors(with_v)] == []
    assert with_v["generator"]["prompt_version"] == "v2"      # version travels with the sample
    without = P.build_manifest("s_001", _spec(), _result(), **common)
    assert [e.message for e in SCHEMA.iter_errors(without)] == []
    assert "prompt_version" not in without["generator"]       # absence ⇒ v1 (no backfill)


def test_report_metrics():
    r = P.PilotReport()
    cell = "triggered/combinational/degrade_performance"
    r.accepted = [
        {"sample_id": "a", "cell": cell, "sig": "x", "method": "input_driven", "witness": {}},
        {"sample_id": "b", "cell": cell, "sig": "x", "method": "input_driven", "witness": {}},
        {"sample_id": "c", "cell": "always_on/None/leak_information", "sig": "y",
         "method": "state_injection", "witness": {}}]
    r.rejected = [{"cell": cell, "reason": "witness not applicable to clean: ..."},
                  {"cell": cell, "reason": "functional_equivalence: not dormant"}]
    assert r.yield_rate == 3 / 5
    assert r.taxonomy_spread()[cell] == 2
    assert r.near_duplicate_clusters() == {"x": ["a", "b"]}      # a,b identical insertion
    assert r.method_spread()["input_driven"] == 2
    assert r.trojan_only_reject_rate() == 0.5                    # 1 of 2 rejects
    assert "pilot report" in r.render().lower()
    assert r.steering_conversion_rate() is None                 # no steered samples ⇒ nothing to measure


def test_attempt1_collapse_clusters_decouple_from_repair_path():
    r = P.PilotReport()
    # three same-prompt (cells 1-3) samples whose attempt-1 outputs collapse to "s1";
    # two accepted with DIVERGENT final sigs (repair-path), one rejected.
    r.accepted = [
        {"sample_id": "b2_001", "cell": "c", "sig": "final_a", "attempt1_sig": "s1",
         "method": "state_injection", "steered": True, "witness": {}},
        {"sample_id": "b2_002", "cell": "c", "sig": "final_b", "attempt1_sig": "s1",
         "method": "state_injection", "steered": True, "witness": {}}]
    r.rejected = [{"sample_id": "b2_003", "cell": "c", "reason": "witness not applicable to clean: x",
                   "attempt1_sig": "s1", "steered": True}]
    # final-accept clustering sees no dup (repair-path divergence hid the collapse)
    assert r.near_duplicate_clusters() == {}
    # attempt-1 clustering recovers it across all three (accepted + rejected)
    assert r.attempt1_collapse_clusters() == {"s1": ["b2_001", "b2_002", "b2_003"]}
    rendered = r.render()
    assert "collapse clusters (attempt-1" in rendered.lower()
    assert "docs/batch2_expectations.md" in rendered          # expected grades cited up front


def test_write_quarantine_persists_per_attempt_trail(tmp_path):
    AR = I.AttemptRecord
    trail = [
        AR(1, 100, 40, 0.0012, "witness not applicable to clean: cannot bind dut.trojan_cnt",
           infected_rtl="module counter8; /*t1*/ endmodule\n",
           witness={"trigger": "trojan_cnt==8'hC7", "observable_effect": "freeze"}),
        AR(2, 110, 45, 0.0013, "witness produced no divergence (infected == clean under trigger)",
           infected_rtl="module counter8; /*t2*/ endmodule\n",
           witness={"trigger": "count==8'hC7", "observable_effect": "freeze"})]
    res = I.InsertionResult(False, None, None, 3,
                            reason="witness produced no divergence (infected == clean under trigger)",
                            trail=trail)
    qdir = tmp_path / "q"
    d = P.write_quarantine(qdir, "batch2_001_counter8", "module counter8; endmodule\n", _spec(), res)
    # per-attempt RTL + witness on disk for both attempts
    assert (d / "clean.v").exists()
    assert (d / "attempt1_infected.v").exists() and (d / "attempt2_infected.v").exists()
    assert (d / "attempt1_witness.json").exists() and (d / "attempt2_witness.json").exists()
    trailj = json.loads((d / "trail.json").read_text())
    assert trailj["class"] == "rejected_noncorpus"           # never mistaken for corpus
    assert len(trailj["attempts"]) == 2
    assert trailj["attempts"][0]["reason"].startswith("witness not applicable")
    assert trailj["cost_usd"] == round(0.0012 + 0.0013, 6)   # per-sample cost on the rejected path too
    assert (qdir / "README_NOT_CORPUS.md").exists()          # quarantine root marked non-corpus


def test_batch2_specs_feasible_and_composed():
    from collections import Counter
    specs = P.batch2_specs()
    assert len(specs) == 12                                    # ~12-sample budget
    ids = [sid for sid, _, _, _ in specs]
    assert len(set(ids)) == 12 and all(s.startswith("batch2_") for s in ids)
    # construction did not raise ⇒ every cell is R1-R3 feasible
    cells = [(sp.top_module, sp.trigger_mechanism, sp.payload) for _, _, sp, _ in specs]
    # (a) sequential-fix validation: both mechanisms, across TWO hosts (not only counter8)
    seq = [c for c in cells if c[1] in ("sequential_counter", "sequential_fsm")]
    assert len(seq) == 5
    assert {c[0] for c in seq} == {"counter8", "accum8"}
    # (b) collapse-breadth: three distinct repeat-probe cells, 3 identical each
    triples = [c for c, n in Counter(cells).items() if n == 3]
    assert len(triples) == 3
    # (c) cost host present and materially larger than a toy host
    assert any(top == "alu8" for top, _, _ in cells)
    assert len(P._HOSTS["alu8"]) > 4 * len(P._HOSTS["add8"])
    # variant_group keys on host source (shared with batch 1), not on batch id
    vgs = {sp.top_module: meta["variant_group"] for _, _, sp, meta in specs}
    assert vgs["counter8"] == "pilot_counter8"


def test_steering_conversion_rate():
    r = P.PilotReport()
    # 2 steered → accepted, 1 steered → rejected, 1 unsteered accept (ignored by the metric)
    r.accepted = [
        {"sample_id": "a", "cell": "c", "sig": "x", "method": "state_injection",
         "steered": True, "witness": {}},
        {"sample_id": "b", "cell": "c", "sig": "y", "method": "state_injection",
         "steered": True, "witness": {}},
        {"sample_id": "d", "cell": "c", "sig": "z", "method": "input_driven",
         "steered": False, "witness": {}}]
    r.rejected = [{"cell": "c", "reason": "witness not applicable to clean: ...", "steered": True}]
    assert r.steered_count() == 3                               # 2 accepted + 1 rejected, all steered
    assert r.steering_conversion_rate() == 2 / 3                # 2 of 3 steered converted
    assert "steering conversion rate: 67%" in r.render().lower()


# --- the structural near-dup signature (rename-robust) ---

def test_structural_signature_is_rename_and_const_robust():
    a = P._structural_signature("wire trig = (a==8'hDE)&&(b==8'hAD);\nassign sum = trig?9'h000:(a+b);")
    b = P._structural_signature("wire t0 = (a==8'hC1)&&(b==8'h22);\nassign sum = t0?9'h000:(a+b);")
    c = P._structural_signature("assign sum = (a+b)^{8'd0,a[0]};")
    assert a == b      # renamed signals + different magic constants -> same structure
    assert a != c      # genuinely different structure -> different


# --- proposed spec set ---

def test_default_pilot_specs_feasible_spans_taxonomy_and_repeats_a_cell():
    from collections import Counter
    specs = P.default_pilot_specs()                         # raises if any cell is R1-R3 infeasible
    assert len(specs) == 12
    cells = {(s.activation, s.trigger_mechanism, s.payload) for _, _, s, _ in specs}
    assert len(cells) >= 6                                  # breadth across the taxonomy
    # amended probe: >=3 IDENTICAL-spec repeats (same HOST + cell) so collapse
    # clustering is unambiguous (no cross-host over-merge confound)
    host_cell = Counter((s.top_module, s.activation, s.trigger_source, s.trigger_mechanism, s.payload)
                        for _, _, s, _ in specs)
    assert max(host_cell.values()) >= 3
    ids = [sid for sid, _, _, _ in specs]
    assert len(set(ids)) == len(ids)                        # unique sample ids


# --- GUARD-TRIP: prove the cost guard is ACTIVE inside run_pilot (no toolchain) ---

def test_run_pilot_yield_floor_aborts(tmp_path):
    # every response is unparseable -> every sample rejects -> after min_attempts the
    # yield floor trips and the pilot stops (no gauntlet/toolchain needed).
    client = I.MockLLMClient(["no blocks here"])
    specs = [(f"p_{i:03d}", "module m(input a, output y); assign y=a; endmodule", _spec(), {})
             for i in range(10)]
    rep = P.run_pilot(specs, tmp_path, api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1.0,
                      yield_floor=0.20, yield_window=10, min_attempts_before_floor=8,
                      client=client, max_repairs=0)
    assert rep.aborted.startswith("yield-floor")
    assert not rep.accepted and len(rep.rejected) < 10      # stopped early


def test_run_pilot_records_api_error_separately_and_continues(tmp_path):
    # A transient API/SDK error is recorded as an infra error (NOT a model reject,
    # so it doesn't pollute yield) and the run continues.
    class _Boom(I.LLMClient):
        def complete(self, prompt):
            raise RuntimeError("api down")

    rep = P.run_pilot([("p_001", "module m(input a, output y); assign y=a; endmodule", _spec(), {})],
                      tmp_path, api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1.0, client=_Boom())
    assert not rep.accepted and not rep.rejected
    assert len(rep.errors) == 1 and "api down" in rep.errors[0]["error"]
    assert rep.spent_usd == 0.0


def test_run_pilot_budget_refuses_before_spending(tmp_path):
    # per-run cap is below any call's cost -> pre_call_check refuses the FIRST call,
    # before the client is invoked. Nothing spends.
    client = I.MockLLMClient(["whatever"])
    specs = [("p_001", "module m(input a, output y); assign y=a; endmodule", _spec(), {})]
    rep = P.run_pilot(specs, tmp_path, api_model="x", pricing_key="claude-sonnet-4",
                      total_usd_cap=10.0, per_run_usd_cap=1e-9, client=client)
    assert rep.aborted.startswith("budget")
    assert not rep.accepted and rep.spent_usd == 0.0
