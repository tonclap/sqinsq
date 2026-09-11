"""Checking the analytic derivatives of the gap against finite differences.

The polisher linearises the constraints in (dx, dy, dtheta). If the derivative
of the gap is computed wrongly, the LP will confidently propose steps that break
the packing, and that looks like "the method does not work" rather than "the
formula has a bug". So the formula is checked separately, and before any runs.
"""

from __future__ import annotations

import argparse

import numpy as np

from sqinsq import polish

rng = np.random.default_rng(20260812)


def gap_of(state: polish.State, pairs: np.ndarray) -> np.ndarray:
    return polish.pair_separation(state, pairs)[0]


def main() -> int:
    # Takes no options, but still parses: without this `--help` would be
    # swallowed and the command would run its check instead of describing it.
    argparse.ArgumentParser(description=__doc__).parse_args()

    n = 6
    state = polish.State(
        cx=rng.uniform(0.5, 4.5, n),
        cy=rng.uniform(0.5, 4.5, n),
        th=rng.uniform(0, np.pi / 2, n),
        s=5.0,
    )
    pairs = np.array([(i, j) for i in range(n) for j in range(i + 1, n)], dtype=int)

    pts = state.corners()
    dpts = state.dcorners_dtheta()
    gap, owner, axis, ki, kj, _a, _dir = polish.pair_separation(state, pairs)

    worst = 0.0
    h = 1e-7
    for idx in range(len(pairs)):
        i, j = int(pairs[idx, 0]), int(pairs[idx, 1])
        u = axis[idx]
        perp = np.array([-u[1], u[0]])
        diff = pts[i, ki[idx]] - pts[j, kj[idx]]
        analytic = {
            ("x", i): u[0],
            ("y", i): u[1],
            ("t", i): float(u @ dpts[i, ki[idx]]),
            ("x", j): -u[0],
            ("y", j): -u[1],
            ("t", j): float(-u @ dpts[j, kj[idx]]),
        }
        analytic[("t", int(owner[idx]))] = analytic.get(("t", int(owner[idx])), 0.0) + float(
            perp @ diff
        )

        for (kind, sq), value in analytic.items():
            plus, minus = state.copy(), state.copy()
            arr_p = {"x": plus.cx, "y": plus.cy, "t": plus.th}[kind]
            arr_m = {"x": minus.cx, "y": minus.cy, "t": minus.th}[kind]
            arr_p[sq] += h
            arr_m[sq] -= h
            numeric = (gap_of(plus, pairs)[idx] - gap_of(minus, pairs)[idx]) / (2 * h)
            err = abs(numeric - value)
            worst = max(worst, err)
            if err > 1e-5:
                print(
                    f"MISMATCH pair ({i},{j}) in {kind}{sq}: "
                    f"analytic {value:+.9f}, differences {numeric:+.9f}, error {err:.2e}"
                )

    print(f"pairs checked: {len(pairs)}   largest derivative error: {worst:.3e}")
    return 0 if worst < 1e-5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
