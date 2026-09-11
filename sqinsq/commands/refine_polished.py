"""Refinement on top of an existing result file, without re-polishing in float.

Why this is separate from `sqinsq polish --refine`. Polishing in float64 is not a
deterministic descent to one answer: after the LP is made dimensionless the
solver takes a different path and arrives at a DIFFERENT local optimum. One
re-run came out better on 18 entries and worse on 14, by up to 8e-5. Both
branches are admissible (both confirmed by the foreign `check.py`), so the old
one cannot be thrown away: it has to be refined the same way, and the best of
the two taken per n.

The input is a directory of `squares-<n>.txt` files in Schadt's format (container
centred); the output is a directory of the same kind.

    sqinsq refine --src polished --dst polished-old-refined
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from sqinsq.paths import work_snapshot

from mpmath import mp, mpf

from sqinsq import refine, schadt, verify

mp.dps = 60

def load_state(path: Path):
    record = schadt.read(path)
    centers = schadt.centers_in_container(record)
    return refine.state_from_degrees(
        [c[0] for c in centers], [c[1] for c in centers], [c[2] for c in centers], record.side
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="polished")
    ap.add_argument("--dst", required=True)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--n", nargs="*", type=int)
    args = ap.parse_args()

    from sqinsq.commands.polish import packing_from_file, save_schadt_format_mp

    snap = work_snapshot(args.src)
    src = snap / args.src
    dst_name = args.dst
    (snap / dst_name).mkdir(exist_ok=True)

    files = sorted(src.glob("squares-*.txt"), key=lambda p: int(p.stem.split("-")[1]))
    if args.n:
        wanted = set(args.n)
        files = [f for f in files if int(f.stem.split("-")[1]) in wanted]

    print(f"{'n':>5} {'before':>22} {'after':>22} {'gain':>11} {'check':>7} {'sec':>6}")
    for path in files:
        n = int(path.stem.split("-")[1])
        t0 = time.time()
        state = load_state(path)
        before = state.s
        result_state, _ = refine.refine(state, iters=args.iters)
        save_schadt_format_mp(result_state, n, snap / dst_name)
        out = snap / dst_name / f"squares-{n}.txt"
        after = schadt.side_of(out)
        check = verify.check(packing_from_file(out), tol=mpf(0), expected_n=n)
        mark = "OK" if check.max_overlap == 0 else "FAIL"
        print(
            f"{n:>5} {mp.nstr(before, 17):>22} {mp.nstr(after, 17):>22} "
            f"{mp.nstr(before - after, 4):>11} {mark:>7} {time.time() - t0:>6.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
