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

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
