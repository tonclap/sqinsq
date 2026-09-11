"""A rigorous check of a packing in interval arithmetic.

Why yet another verifier. Ours and the foreign one both compute in POINT
arithmetic: every number is an approximation, and the conclusion "the gap is
3e-7" rests on rounding errors being small. Usually that is enough. But when a
result contradicts a published closed form (entries without the flag), agreement
between two point implementations stops being an argument: both can be wrong the
same way, and both trust their own rounding.

Interval arithmetic (`mpmath.iv`) returns not a number but a guaranteed interval
containing the true value. If the LOWER bound of the gap is positive, the squares
are separated - under any implementation of arithmetic, with no assumptions about
rounding. That is a proof, not evidence.

The price is speed: intervals are about 20 times more expensive, so there is no
broad float phase here, only the exact one. Running it over the whole registry
is pointless; running it on disputed entries is not.

    sqinsq verify-interval --src polished-unflagged --n 69 83
    sqinsq verify-interval --src polished --n 179
"""

from __future__ import annotations

import argparse
import time

from sqinsq.paths import work_snapshot

from mpmath import iv, mp

from sqinsq import schadt

mp.dps = 60
iv.dps = 60


def corners_iv(cx, cy, deg):
    """The four corners of a unit square, as intervals.

    Sine and cosine are taken in interval form: the angle is given as a decimal
    string, converting it to radians already introduces uncertainty, and that
    uncertainty must reach the result rather than get lost.
    """
    angle = iv.mpf(str(deg)) * iv.pi / 180
    c, s = iv.cos(angle), iv.sin(angle)
    x0, y0 = iv.mpf(str(cx)), iv.mpf(str(cy))
    half = iv.mpf(1) / 2
    out = []
    for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half)):
        out.append((x0 + dx * c - dy * s, y0 + dx * s + dy * c))
    return out


def separated(a, b) -> bool:
    """True means provably separated: an axis was found with a strictly positive gap."""
    for quad in (a, b):
        for i in (0, 1):
            ax = -(quad[i + 1][1] - quad[i][1])
            ay = quad[i + 1][0] - quad[i][0]
            pa = [ax * x + ay * y for x, y in a]
            pb = [ax * x + ay * y for x, y in b]
            lo_a = min(pa, key=lambda v: v.a)
            hi_a = max(pa, key=lambda v: v.b)
            lo_b = min(pb, key=lambda v: v.a)
            hi_b = max(pb, key=lambda v: v.b)
            # Lower bound of the gap: the worst case inside the intervals.
            if (lo_b.a - hi_a.b) > 0 or (lo_a.a - hi_b.b) > 0:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="polished")
    ap.add_argument("--n", nargs="*", type=int, required=True)
    args = ap.parse_args()

    snap = work_snapshot(args.src)
    failures = 0
    for n in args.n:
        path = snap / args.src / f"squares-{n}.txt"
        if not path.exists():
            print(f"n={n}: no file {path}")
            failures += 1
            continue

        t0 = time.time()
        record = schadt.read(path)
        side = iv.mpf(str(record.side))
        half = side / 2
        quads = [corners_iv(x, y, deg) for x, y, deg in record.rows]

        # Containment: provably inside if the upper bound of a coordinate does
        # not cross the container boundary.
        outside = []
        for idx, quad in enumerate(quads):
            for x, y in quad:
                if x.a < (-half).b or x.b > half.a or y.a < (-half).b or y.b > half.a:
                    outside.append(idx)
                    break

        # Overlap: a walk over pairs, pruned by the distance between centres.
        centers = [
            (sum((p[0] for p in q), iv.mpf(0)) / 4, sum((p[1] for p in q), iv.mpf(0)) / 4)
            for q in quads
        ]
        limit = iv.mpf("1.4143")
        touching = []
        for i in range(len(quads)):
            for j in range(i + 1, len(quads)):
                dx = centers[i][0] - centers[j][0]
                dy = centers[i][1] - centers[j][1]
                if (dx * dx + dy * dy).a > (limit * limit).b:
                    continue
                if not separated(quads[i], quads[j]):
                    touching.append((i + 1, j + 1))

        elapsed = time.time() - t0
        verdict = "PROVED" if not outside and not touching else "NOT PROVED"
        print(
            f"n={n:<5} squares {record.n:<5} side {record.side} "
            f"{verdict}  ({elapsed:.1f} c)"
        )
        if outside:
            print(f"      may stick out of the container: {outside[:8]}")
        if touching:
            print(f"      pairs with no proven gap: {len(touching)}, first {touching[:6]}")
        if outside or touching:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
