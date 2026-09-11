"""A dump of verifier verdicts over every packing - the baseline for refactoring.

The verifier is the single support of the whole result, and "I did not change
the meaning, only sped it up" is not an argument here: import and compilation
catch syntax, not a lost branch. So a dump is taken before an optimisation (206
packings: 174 from the registry and 32 of our own), taken again after,
and compared DIGIT BY DIGIT rather than by "the tests passed".

    sqinsq verify-dump --out data/verify-baseline.json
    sqinsq verify-dump --out data/verify-after.json --compare data/verify-baseline.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sqinsq.paths import work_snapshot

from mpmath import mp, mpf, nstr

from sqinsq import verify
from sqinsq.svgpack import load

mp.dps = 60
DIGITS = 40  # deliberately more than any of the compared numbers carries


def dump_one(path: Path) -> dict:
    packing = load(path)
    result = verify.check(packing, tol=mpf(0))
    return {
        "file": path.name,
        "n": result.n,
        "s": nstr(packing.s, DIGITS),
        "max_overlap": nstr(result.max_overlap, DIGITS),
        "max_outside": nstr(result.max_outside, DIGITS),
        "worst_pair": list(result.worst_pair) if result.worst_pair else None,
        "problems": result.problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare")
    args = ap.parse_args()

    # Registry names are not always "square-<number>": there are forms like
    # square-170b. Sorting by file name is fine - what matters is a stable order.
    snap = work_snapshot("svg", "submission")
    paths = sorted((snap / "svg").glob("square-*.svg"))
    paths += sorted((snap / "submission").glob("square-*.svg"))

    rows = []
    t0 = time.time()
    for path in paths:
        rows.append(dump_one(path) | {"dir": path.parent.name})
    elapsed = time.time() - t0

    out = Path(args.out)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"packings: {len(rows)}, time: {elapsed:.1f} s, dump: {out}")

    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        if len(before) != len(rows):
            print(f"DIFFERENCE: there were {len(before)} packings, now {len(rows)}")
            return 1
        diffs = [
            (a["dir"], a["file"], key, a[key], b[key])
            for a, b in zip(before, rows)
            for key in a
            if a[key] != b[key]
        ]
        if diffs:
            print(f"DIFFERENCES: {len(diffs)}")
            for d in diffs[:20]:
                print(f"  {d[0]}/{d[1]} {d[2]}: was {d[3]!r}, now {d[4]!r}")
            return 1
        print(f"verdicts match on all {len(rows)} packings, to the last digit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
