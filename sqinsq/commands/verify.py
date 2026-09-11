"""Verify packings given as files: is each one admissible, and how tight is it.

This is the command an outsider needs first, and the one this project did not
have: everything else here verifies *our* pipeline or *the whole registry*, and
neither helps someone holding a single packing of their own.

Two formats are accepted, told apart by extension rather than by guessing:

* ``.svg`` — a registry-style picture, parsed the way the registry pages are;
* ``.txt`` — the coordinate format of Schadt's repository (``Final s:`` plus
  ``Square N: x=..., y=..., deg=...``), in which the container is centred.

The tolerance is **zero** by default, which is the only defensible default for a
claim: a packing with an overlap of 1e-40 is not a packing. Pass ``--tol`` to
measure instead of judge - for reading published coordinates that were rounded,
``--tol 1e-9`` is the sane value, and that is what the registry check uses.

    sqinsq verify square-238.svg
    sqinsq verify squares-238.txt --tol 1e-9
    sqinsq verify data/snapshot-2026-09-10/svg/*.svg

Exit code 1 means at least one packing was rejected. What it prints per file:
the number of squares, the declared side, the penetration depth of the worst
pair, how far the worst corner escapes the container, and the tight side - the
smallest axis-aligned square that actually contains the configuration. A tight
side noticeably below the declared one means the packing is not pressed against
the walls, so the declared value is not optimal even for its own arrangement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree

from mpmath import mp, mpf

from sqinsq import schadt, svgpack, verify

mp.dps = 60


def load(path: Path):
    """A packing from a file, by extension. Unknown extension is a refusal."""
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return svgpack.load(path)
    if suffix == ".txt":
        return schadt.to_packing(path)
    raise SystemExit(
        f"{path}: unknown extension {suffix!r}. Expected .svg (registry picture) "
        "or .txt (coordinate file)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="files to verify")
    parser.add_argument(
        "--tol",
        default="0",
        help="overlap tolerance; 0 (default) judges, 1e-9 measures rounded coordinates",
    )
    parser.add_argument(
        "--expect-n",
        type=int,
        help="fail unless the packing has exactly this many squares",
    )
    args = parser.parse_args()

    tol = mpf(args.tol)
    failures = 0

    for path in args.paths:
        if not path.exists():
            print(f"{path.name:<24} MISSING")
            failures += 1
            continue
        try:
            packing = load(path)
        except (svgpack.SvgParseError, ElementTree.ParseError, ValueError) as error:
            # A file that is not what its extension claims is a rejection with a
            # readable reason, not a traceback: ElementTree raises ParseError on
            # anything that is not XML, and schadt.read raises ValueError when
            # the coordinate file has no `Final s:` line.
            print(f"{path.name:<24} PARSE ERROR: {error}")
            failures += 1
            continue

        result = verify.check(packing, tol=tol, expected_n=args.expect_n)
        tight = verify.tight_side(packing)
        slack = packing.s - tight

        print(
            f"{path.name:<24} {'OK  ' if result.ok else 'FAIL'} "
            f"n={result.n:<5} s={mp.nstr(packing.s, 20)} "
            f"overlap={mp.nstr(result.max_overlap, 3)} "
            f"outside={mp.nstr(result.max_outside, 3)} "
            f"slack={mp.nstr(slack, 3)}"
        )
        for problem in result.problems:
            print(f"{'':<24}      {problem}")
        for warning in packing.warnings:
            print(f"{'':<24}      note: {warning}")
        if not result.ok:
            failures += 1

    print()
    print(f"verified {len(args.paths)} file(s) at tolerance {args.tol}, rejected {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
