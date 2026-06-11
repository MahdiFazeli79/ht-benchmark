"""Sample validator — schema + rules R1-R9 (spec §10).

A file can be schema-valid yet sample-invalid; this validator is the
sample-validity authority. It enforces the JSON Schemas, the cross-field rules
R1-R9, handle uniqueness and forbidden-key patterns, label-handle resolution,
and the manifest-matches-files diff. Exit non-zero on any failure.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from . import handles as H
from . import resolve as R
from . import hw2vec_compat as HW

_REPO = Path(__file__).resolve().parents[2]          # ht-bench/
_SPEC = _REPO / "spec"


def _load(p: Path):
    return json.loads(p.read_text())


def _schemas(spec_dir: Path):
    sd = spec_dir / "schemas"
    return {
        "manifest": Draft202012Validator(_load(sd / "trojan_manifest.schema.json")),
        "labels_rtl": Draft202012Validator(_load(sd / "labels_rtl.schema.json")),
        "labels_netlist": Draft202012Validator(_load(sd / "labels_netlist.schema.json")),
        "metadata": Draft202012Validator(_load(sd / "metadata.schema.json")),
        "graph": Draft202012Validator(_load(sd / "graph.schema.json")),
    }


def _added_line_ranges(clean: str, infected: str) -> list[list[int]]:
    """Contiguous [start,end] (1-based) line ranges present in `infected` but
    not in `clean`, by line-level diff."""
    a = clean.splitlines()
    b = infected.splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ranges: list[list[int]] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            ranges.append([j1 + 1, j2])      # 1-based inclusive in infected.v
    return ranges


def validate_sample(sample_dir, rtl_only=False, lint_sources=False, spec_dir=_SPEC):
    """Return (errors, warnings) for one sample directory."""
    sd = Path(sample_dir)
    errors: list[str] = []
    warnings: list[str] = []
    S = _schemas(Path(spec_dir))

    def need(name):
        p = sd / name
        if not p.exists():
            errors.append(f"missing required file: {name}")
            return None
        return _load(p)

    manifest = need("trojan_manifest.json")
    labels_rtl = need("labels_rtl.json")
    metadata = need("metadata.json")
    dfg = None
    gp = sd / "graphs" / "dfg_rtl.json"
    if gp.exists():
        dfg = _load(gp)
    else:
        errors.append("missing required file: graphs/dfg_rtl.json")

    labels_net = None
    net = None
    if not rtl_only:
        lp = sd / "labels_netlist.json"
        np_ = sd / "graphs" / "netlist.json"
        labels_net = _load(lp) if lp.exists() else None
        net = _load(np_) if np_.exists() else None

    # --- 1. schema validation ---
    if manifest is not None:
        errors += [f"manifest: {e.message}" for e in S["manifest"].iter_errors(manifest)]
    if labels_rtl is not None:
        errors += [f"labels_rtl: {e.message}" for e in S["labels_rtl"].iter_errors(labels_rtl)]
    if metadata is not None:
        errors += [f"metadata: {e.message}" for e in S["metadata"].iter_errors(metadata)]
    if dfg is not None:
        errors += [f"dfg_rtl: {e.message}" for e in S["graph"].iter_errors(dfg)]
    if labels_net is not None:
        errors += [f"labels_netlist: {e.message}" for e in S["labels_netlist"].iter_errors(labels_net)]
    if net is not None:
        errors += [f"netlist: {e.message}" for e in S["graph"].iter_errors(net)]

    if errors:                      # schema failures make deeper checks unsafe
        return errors, warnings
    if manifest is None or dfg is None or labels_rtl is None:
        return errors, warnings

    cls = manifest["class"]
    tax = manifest.get("taxonomy")

    # --- 2. cross-field rules R1-R9 ---
    if cls == "infected" and tax is not None:
        act = tax["activation"]
        if act == "always_on":
            if tax["trigger_source"] is not None or tax["trigger_mechanism"] is not None:
                errors.append("R1: always_on must have null trigger_source and trigger_mechanism")
            if tax["payload"] not in ("leak_information", "degrade_performance"):
                errors.append("R3: always_on payload must be leak_information or degrade_performance")
        elif act == "triggered":
            if tax["trigger_source"] is None or tax["trigger_mechanism"] is None:
                errors.append("R2: triggered must have non-null trigger_source and trigger_mechanism")

    ver = manifest["verification"]
    if not (ver["compile_pass"] and ver["synth_pass"]):
        errors.append("R4: compile_pass and synth_pass must both be true")
    if cls == "infected":
        for flag in ("functional_equiv_pass", "synth_survival_pass", "activation_proof_pass"):
            if not ver.get(flag, False):
                errors.append(f"R4: infected sample requires {flag} == true")
        if manifest["source_kind"] == "llm_generated" and manifest["generator"]["model"] == "none":
            errors.append("R5: llm_generated requires generator.model != 'none'")

    # R6: manifest matches files
    clean_v = (sd / "clean.v").read_text() if (sd / "clean.v").exists() else None
    inf_v = (sd / "infected.v").read_text() if (sd / "infected.v").exists() else None
    if clean_v is None or inf_v is None:
        errors.append("R6: clean.v and infected.v required")
    else:
        added = _added_line_ranges(clean_v, inf_v)
        if cls == "clean":
            if added:
                errors.append("R6: clean sample must have clean.v == infected.v (empty diff)")
        else:
            declared = [list(r) for r in manifest["inserted_rtl"]["line_ranges"]]
            if sorted(added) != sorted(declared):
                errors.append(f"R6: diff line ranges {added} != manifest inserted_rtl.line_ranges {declared}")

    # R7: class consistency
    rtl_lbls = labels_rtl["labels"]
    if cls == "clean":
        if rtl_lbls != {}:
            errors.append("R7: clean sample labels_rtl.labels must be {}")
        if labels_net is not None and labels_net["labels"] != {}:
            errors.append("R7: clean sample labels_netlist.labels must be {}")
    else:
        if rtl_lbls == {}:
            errors.append("R7: infected sample labels_rtl.labels must be non-empty")

    # R8: clean negative-class realism (non-empty graphs)
    if cls == "clean":
        if not dfg["nodes"] or not dfg["edges"]:
            errors.append("R8: clean sample dfg_rtl.json must have non-empty nodes and edges")
        if net is not None and (not net["nodes"] or not net["edges"]):
            errors.append("R8: clean sample netlist.json must have non-empty nodes and edges")

    # --- 3/4. handle hygiene: forbidden keys, uniqueness, scheme ---
    for gname, g in (("dfg_rtl", dfg), ("netlist", net)):
        if g is None:
            continue
        hs = [n["handle"] for n in g["nodes"]]
        for h in hs:
            if H.is_forbidden_key(h):
                errors.append(f"{gname}: forbidden handle key: {h!r}")
            # R11: a handle must be positively classifiable. An unclassified
            # handle (neither source-intrinsic nor known tool-synthetic) fails
            # loud rather than defaulting to intrinsic — the canary proved new
            # artifact classes keep appearing (spec §10 R11).
            elif H.classify_handle(h) == "unclassified":
                errors.append(
                    f"{gname}: R11 unclassified handle {h!r} (neither "
                    f"source-intrinsic nor known tool-synthetic)"
                )
        if len(set(hs)) != len(hs):
            dupes = {h for h in hs if hs.count(h) > 1}
            errors.append(f"{gname}: duplicate handles: {sorted(dupes)}")

    for lname, lbls in (("labels_rtl", labels_rtl), ("labels_netlist", labels_net)):
        if lbls is None:
            continue
        for key in lbls["labels"]:
            if H.is_forbidden_key(key):
                errors.append(f"{lname}: forbidden handle key: {key!r}")
            # A label must reference a real signal: intrinsic or structural, never
            # a synthetic tool net or an unclassified handle (R11).
            elif H.classify_handle(key) in ("synthetic", "unclassified"):
                errors.append(
                    f"{lname}: R11 label key {key!r} is "
                    f"{H.classify_handle(key)}, not a source-intrinsic signal"
                )

    # --- 5. label-handle resolution ---
    try:
        R.resolve_rtl(dfg, labels_rtl)
    except KeyError as e:
        errors.append(f"resolve: {e}")
    if net is not None and labels_net is not None:
        try:
            R.resolve_netlist(net, labels_net)
        except KeyError as e:
            errors.append(f"resolve: {e}")

    # --- R9: injectivity under HW2VEC name transform ---
    try:
        HW.assert_injective([n["handle"] for n in dfg["nodes"]])
    except ValueError as e:
        errors.append(str(e))

    # --- R10: license redistributability intake gate ---
    lic_path = Path(spec_dir) / "licenses.json"
    if lic_path.exists():
        allow = {x.lower() for x in _load(lic_path)["redistributable_allowlist"]}
        if manifest["license"].lower() not in allow:
            errors.append(
                f"R10: license {manifest['license']!r} not in the redistributable "
                f"allowlist (spec/licenses.json); sample rejected at intake."
            )

    # --- optional source lint ---
    if lint_sources:
        known = set(_load(Path(spec_dir) / "sources.json")["known_sources"])
        if manifest["source"] not in known:
            warnings.append(f"source {manifest['source']!r} not in spec/sources.json")

    return errors, warnings


def validate_path(path, rtl_only=False, lint_sources=False, spec_dir=_SPEC):
    """Validate a sample dir or a directory of samples. Returns dict
    sample_id -> (errors, warnings)."""
    p = Path(path)
    samples = [p] if (p / "trojan_manifest.json").exists() else sorted(
        d for d in p.iterdir() if d.is_dir() and (d / "trojan_manifest.json").exists()
    )
    return {s.name: validate_sample(s, rtl_only, lint_sources, spec_dir) for s in samples}
