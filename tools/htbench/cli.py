"""htbench command-line interface: `validate` and `roundtrip` (spec §10, §11)."""

from __future__ import annotations

import argparse
import sys


def _cmd_validate(args) -> int:
    from . import validate
    results = validate.validate_path(
        args.path, rtl_only=args.rtl_only, lint_sources=args.lint_sources
    )
    failed = 0
    for sid, (errors, warnings) in sorted(results.items()):
        for w in warnings:
            print(f"  [warn] {sid}: {w}")
        if errors:
            failed += 1
            print(f"FAIL {sid}")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"PASS {sid}")
    print(f"\n{len(results) - failed}/{len(results)} samples valid")
    return 1 if failed else 0


def _cmd_roundtrip(args) -> int:
    from . import roundtrip
    results = roundtrip.roundtrip_path(args.path, perturb=args.perturb)
    failed = 0
    for sid, (ok, msg) in sorted(results.items()):
        print(f"{'PASS' if ok else 'FAIL'} {sid}: {msg}")
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} samples round-trip stable")
    return 1 if failed else 0


def _cmd_elaborate(args) -> int:
    import json

    from . import elaborate as E

    chparams = {}
    for kv in args.chparam or []:
        if "=" not in kv:
            print(f"bad --chparam {kv!r}, expected K=V", file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        chparams[k] = v

    sv = None
    if args.sv:
        sv = True
    if args.no_sv:
        sv = False

    try:
        res = E.elaborate(args.sources, args.top, chparams=chparams,
                          systemverilog=sv, work_dir=args.work_dir)
    except E.ElaborationError as e:
        print(f"elaboration failed: {e}", file=sys.stderr)
        return 1

    if args.out:
        import shutil
        shutil.copyfile(res.verilog_path, args.out)

    prov = res.provenance()
    prov["verilog_path"] = args.out or res.verilog_path
    print(json.dumps(prov, indent=2))
    return 0


def _cmd_check_list(args) -> int:
    from . import circuit_list as C

    data = C.load(args.path)
    allow = C.load_allowlist(args.spec_dir)
    rep = C.check_circuit_list(data, allow)
    out = rep.render()
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(out)
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0 if rep.structurally_valid else 1


def _cmd_r9_rate(args) -> int:
    import json
    from pathlib import Path

    from . import r9_rate as R

    specs = json.loads(Path(args.specs).read_text())
    rep = R.measure_design_specs(specs)
    out = rep.render()
    if args.out:
        Path(args.out).write_text(out)
        print(f"wrote {args.out}")
    else:
        print(out)
    # Non-zero when the rate crosses the finding threshold, so a CI/batch run
    # surfaces it loudly.
    return 1 if rep.design_collision_rate >= R.FINDING_THRESHOLD else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="htbench")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate a sample dir or a directory of samples")
    v.add_argument("path")
    v.add_argument("--rtl-only", action="store_true")
    v.add_argument("--lint-sources", action="store_true")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("roundtrip", help="run the graph-regeneration invariance gate")
    r.add_argument("path")
    r.add_argument("--perturb", action="store_true")
    r.set_defaults(func=_cmd_roundtrip)

    e = sub.add_parser(
        "elaborate",
        help="Yosys-elaboration RTL front-end (sv2v + yosys -chparam -> Verilog-2005)",
    )
    e.add_argument("sources", nargs="+")
    e.add_argument("--top", required=True)
    e.add_argument("--chparam", action="append", metavar="K=V",
                   help="pin a parameter, e.g. --chparam CFG=33 (repeatable)")
    e.add_argument("--sv", action="store_true", help="force SystemVerilog (run sv2v)")
    e.add_argument("--no-sv", dest="no_sv", action="store_true",
                   help="force plain Verilog (skip sv2v)")
    e.add_argument("-o", "--out", help="write elaborated Verilog here")
    e.add_argument("--work-dir", dest="work_dir")
    e.set_defaults(func=_cmd_elaborate)

    c = sub.add_parser(
        "check-list",
        help="gate a Phase-1 circuit-list manifest before download (task #28)",
    )
    c.add_argument("path", help="circuit-list YAML (e.g. docs/phase1_candidates.yaml)")
    c.add_argument("--spec-dir", dest="spec_dir", default="spec",
                   help="dir holding licenses.json (the R10 allowlist)")
    c.add_argument("-o", "--out", help="write the report here instead of stdout")
    c.set_defaults(func=_cmd_check_list)

    r9 = sub.add_parser(
        "r9-rate",
        help="measure the HW2VEC R9 collision rate over a set of designs (task #27)",
    )
    r9.add_argument("specs", help="JSON list of {design_id, sources, top, chparams?}")
    r9.add_argument("-o", "--out", help="write the report here instead of stdout")
    r9.set_defaults(func=_cmd_r9_rate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
