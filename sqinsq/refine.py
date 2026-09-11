"""An arbitrary-precision relaxation stage on top of the float64 polisher.

Why it is needed. The polisher in ``polish`` works in float64 and stops when
the trust region shrinks to ~1e-14: below that a step stops being
distinguishable from noise, because a coordinate of order 10 carries only
~1e-16 of absolute precision. A published side is therefore right to about the
15th digit, while the registry prints 30+ and is checked by foreign code at 1e-100.

The trick is iterative refinement, exactly as in linear algebra:

* the configuration is kept in mpmath (``MPState``);
* the DERIVATIVES come from a float64 copy: they only set a direction, and
  their precision is enough for that;
* the RIGHT-HAND SIDES (gaps, distances to the walls) are computed in mpmath
  and converted to float as differences - a quantity of ~1e-14 survives the
  conversion with relative error 1e-16, that is absolute 1e-30;
* the LP step is applied to the mpmath state.

Every iteration therefore adds ~15 digits instead of stalling at 1e-16. The
truth is still not convergence but the exact check: a step is accepted only if
``verify.check`` with a zero tolerance confirms the packing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from mpmath import cos, mp, mpf, pi, sin

from . import polish, verify
from .svgpack import Packing, UnitSquare

# Corner offsets of a unit square from its centre - the same as polish.OFFSETS,
# but in exact arithmetic.
_HALF = mpf(1) / 2
_LOCAL = ((-_HALF, -_HALF), (_HALF, -_HALF), (_HALF, _HALF), (-_HALF, _HALF))


@dataclass
class MPState:
    """A configuration in mpmath: centres, angles (radians) and container side."""

    cx: list
    cy: list
    th: list
    s: object

    @property
    def n(self) -> int:
        return len(self.cx)

    def copy(self) -> "MPState":
        return MPState(list(self.cx), list(self.cy), list(self.th), self.s)

    def to_float(self) -> polish.State:
        return polish.State(
            cx=np.array([float(v) for v in self.cx]),
            cy=np.array([float(v) for v in self.cy]),
            th=np.array([float(v) for v in self.th]),
            s=float(self.s),
        )

    def apply(self, z: np.ndarray) -> "MPState":
        """Apply a raw LP step. Added in mpmath - anything else defeats the point."""
        n = self.n
        new = self.copy()
        new.cx = [self.cx[i] + mpf(float(z[i])) for i in range(n)]
        new.cy = [self.cy[i] + mpf(float(z[n + i])) for i in range(n)]
        new.th = [self.th[i] + mpf(float(z[2 * n + i])) for i in range(n)]
        new.s = self.s + mpf(float(z[3 * n]))
        return new

    def packing(self, source: str = "refined") -> Packing:
        squares = [
            UnitSquare(corners=[tuple(p) for p in quad]) for quad in Exact(self).corners
        ]
        return Packing(s=self.s, squares=squares, source=source, entities={}, warnings=[])


class Exact:
    """Exact geometry of a state: square corners and edge normals in mpmath.

    Used as the source of right-hand sides for ``polish.slp_step``.
    """

    def __init__(self, state: MPState):
        self.s = state.s
        self.corners = []
        self.axes = []
        for i in range(state.n):
            ca, sa = cos(state.th[i]), sin(state.th[i])
            cx, cy = state.cx[i], state.cy[i]
            self.corners.append(
                [(cx + dx * ca - dy * sa, cy + dx * sa + dy * ca) for dx, dy in _LOCAL]
            )
            # The same axis order as in polish._axes: (cos, sin) and (-sin, cos).
            self.axes.append([(ca, sa), (-sa, ca)])

    def axis(self, owner: int, a: int, direction: float):
        ux, uy = self.axes[owner][a]
        return (ux, uy) if direction > 0 else (-ux, -uy)

    def projection_gap(self, i: int, k: int, j: int, m: int, u) -> object:
        """u.(P_i[k] - P_j[m]) - the difference is taken BEFORE multiplying by the axis.

        The projections alone are of order 10, their difference is of order of
        the gap; it is the difference that must be computed, or precision is lost.
        """
        pi_, pj = self.corners[i][k], self.corners[j][m]
        return u[0] * (pi_[0] - pj[0]) + u[1] * (pi_[1] - pj[1])


def state_from_float(state: polish.State) -> MPState:
    return MPState(
        cx=[mpf(repr(float(v))) for v in state.cx],
        cy=[mpf(repr(float(v))) for v in state.cy],
        th=[mpf(repr(float(v))) for v in state.th],
        s=mpf(repr(float(state.s))),
    )


def state_from_degrees(xs, ys, degs, s) -> MPState:
    """A state from decimal strings x/y/degrees - what actually goes to the file."""
    factor = pi / 180
    return MPState(
        cx=[mpf(str(v)) for v in xs],
        cy=[mpf(str(v)) for v in ys],
        th=[mpf(str(v)) * factor for v in degs],
        s=mpf(str(s)),
    )


def max_overlap(state: MPState):
    return verify.check(state.packing(), tol=mpf(0)).max_overlap


def tight_side(state: MPState):
    """Smallest side of an origin-anchored axis-aligned container for this state.

    It is the one that gets declared: the side is computed from the same geometry
    that is verified, not read off the LP variable.
    """
    exact = Exact(state)
    hi = max(max(max(p[0], p[1]) for p in quad) for quad in exact.corners)
    lo = min(min(min(p[0], p[1]) for p in quad) for quad in exact.corners)
    return hi - min(lo, mpf(0))


def refine(
    state: MPState,
    *,
    iters: int = 30,
    trust0: float = 1e-12,
    contact_margin: float = 1e-4,
    verbose: bool = False,
):
    """Tighten a configuration in exact arithmetic. Returns (state, log).

    A step is accepted only if the side really decreased AND the exact check with
    a zero tolerance found no overlap: validity of a packing is binary.
    """
    # The container is first seated on the actual extent. In a file produced by
    # the float64 polisher the side is declared with a margin (~1e-13 above),
    # and that margin is free space: the LP minimises ds, not the extent, and
    # honestly spreads the squares into the gap without shrinking anything.
    best = state.copy()
    best_side = tight_side(best)
    best.s = best_side
    if max_overlap(best) != 0:
        return best, [("rejected", "the initial configuration already overlaps")]

    trust = trust0
    log = []
    for step in range(iters):
        exact = Exact(best)
        safety = 4.0 * trust * trust
        _, active, z = polish.slp_step(
            best.to_float(),
            trust=trust,
            contact_margin=contact_margin,
            safety=safety,
            exact=exact,
        )
        if z is None:
            trust *= 0.5
            if trust < 1e-40:
                break
            continue
        candidate = best.apply(z)
        side = tight_side(candidate)
        candidate.s = side  # the container always sits on the extent, see above
        gain = best_side - side
        ok = gain > 0 and max_overlap(candidate) == 0
        if verbose:
            print(
                f"    step {step:>2} trust={trust:.1e} active={active} "
                f"gain={mp.nstr(gain, 6)} {'accepted' if ok else 'rejected'}"
            )
        if ok:
            log.append((step, mp.nstr(gain, 6)))
            best, best_side = candidate, side
            # While steps keep passing, the trust region shrinks twice as slowly
            # as precision grows: the goal is not speed but keeping the
            # linearisation valid.
            if gain < mpf(trust) * mpf("1e-3"):
                trust *= 0.5
        else:
            trust *= 0.5
        if trust < 1e-40:
            break
    return best, log


