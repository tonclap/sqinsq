"""Packing verifier: containment inside the box, and no overlap between squares.

Written before the solver, deliberately. Without a verifier any "record" the
solver reports is most likely a numerical error that swallowed a microscopic
intersection, and publishing one costs more than never reporting it.

Method: the separating axis theorem (SAT) for convex quadrilaterals. Two squares
do not intersect if and only if there is an axis among their edge normals on
which the projections do not overlap. Touching (a gap of exactly 0) is legal:
dense packings are held together by contacts, so the threshold is stated
explicitly rather than assumed.

Broad phase in float (a grid over centres), exact phase in mpmath. A pair can
only intersect if the centres are closer than sqrt(2), a unit square's diameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from mpmath import mpf, sqrt

from .svgpack import Packing, UnitSquare

DEFAULT_TOL = mpf("1e-9")
DIAG = math.sqrt(2.0)


def _axes(square: UnitSquare) -> list[tuple]:
    """The two distinct edge normals of a square (the other two are antiparallel)."""
    out = []
    for i in (0, 1):
        (x0, y0) = square.corners[i]
        (x1, y1) = square.corners[i + 1]
        out.append((-(y1 - y0), x1 - x0))
    return out


def _project(square: UnitSquare, axis: tuple) -> tuple:
    ax, ay = axis
    values = [ax * x + ay * y for x, y in square.corners]
    return min(values), max(values)


# Threshold below which the float phase is not allowed to decide. Coordinates
# here are at most ~45; double carries 2.2e-16 relative precision, so the error
# of a projection is a few times 1e-14. A threshold of 1e-9 keeps five orders of
# margin: anything closer to zero goes to exact arithmetic. The float phase may
# conclude "separated" only above the threshold, and "overlapping" never.
FLOAT_SAFE_GAP = 1e-9


def _float_corners(square: UnitSquare) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in square.corners]


def _float_verdict(a: list, b: list) -> tuple[bool, int]:
    """Fast float SAT phase: ``(definitely separated, index of the best axis)``.

    A first value of True means the squares are separated with margin and the
    exact check is unnecessary. False does not mean "they overlap": it means
    "float may not decide", and the pair goes to the exact check. This asymmetry
    is the point - validity is binary, and approximate arithmetic can rule pairs
    out, never rule them in.

    The second value is meaningful only when the first is False: it is the index
    of the axis (in the order ``_axes(a) + _axes(b)``) with the largest float
    gap, that is, the most likely separating one. The exact phase starts there
    and almost always finishes there too. The verdict does not depend on the
    order: a pair is separated if ANY axis separates it.
    """
    best_gap = -float("inf")
    best_index = 0
    index = 0
    for quad in (a, b):
        for i in (0, 1):
            x0, y0 = quad[i]
            x1, y1 = quad[i + 1]
            ax, ay = -(y1 - y0), x1 - x0
            pa = [ax * x + ay * y for x, y in a]
            pb = [ax * x + ay * y for x, y in b]
            gap = max(min(pa) - max(pb), min(pb) - max(pa))
            if gap > FLOAT_SAFE_GAP:
                return True, 0
            if gap > best_gap:
                best_gap, best_index = gap, index
            index += 1
    return False, best_index


def _axis_order(first: int) -> tuple[int, ...]:
    """Order in which to walk the four axes, starting from the float phase hint."""
    return (first,) + tuple(k for k in range(4) if k != first)


def separation(a: UnitSquare, b: UnitSquare, *, axes: list | None = None):
    """Largest gap over the SAT axes.

    ``>= 0`` - the squares are separated (0 means touching); ``< 0`` - they
    intersect, and the magnitude is the depth along the least violated axis.
    """
    best = None
    for axis in axes if axes is not None else _axes(a) + _axes(b):
        norm = sqrt(axis[0] ** 2 + axis[1] ** 2)
        if norm == 0:
            continue
        lo_a, hi_a = _project(a, axis)
        lo_b, hi_b = _project(b, axis)
        gap = max(lo_a - hi_b, lo_b - hi_a) / norm
        if best is None or gap > best:
            best = gap
    return best if best is not None else mpf(0)


class _Geometry:
    """Square axes and self-projections, computed once.

    A square takes part in eight pairs on average, and its two normals - plus its
    own projections onto them - do not depend on the partner. In the exact check
    two of a pair's four axes always belong to one of the squares, so this cache
    removes half of the mpmath multiplications in the hottest place of the verifier.
    """

    def __init__(self, squares: list[UnitSquare]):
        self.squares = squares
        self.axes = [_axes(square) for square in squares]
        # The cache is lazy and per axis: the walk almost always stops on the
        # first axis, so most squares never project onto their second one, and
        # computing it up front would be pure loss.
        self._own: dict[tuple[int, int], tuple] = {}

    def own_projection(self, i: int, k: int) -> tuple:
        """Projection of square ``i`` onto its own axis ``k`` (0 or 1)."""
        cached = self._own.get((i, k))
        if cached is None:
            cached = _project(self.squares[i], self.axes[i][k])
            self._own[(i, k)] = cached
        return cached

    def depth(self, i: int, j: int, first: int = 0):
        """Penetration depth of the pair (i, j); ``first`` is the float phase hint.

        Unlike ``separation``, the size of the gap is not computed for SEPARATED
        pairs - and they are the vast majority. As soon as an axis with a
        non-negative gap is found the pair is separated, and dividing by the axis
        length (an mpmath square root per axis) is pointless. Only a real
        overlap is normalised.
        """
        a, b = self.squares[i], self.squares[j]
        axes = self.axes[i] + self.axes[j]
        for k in _axis_order(first):
            axis = axes[k]
            # Two of the four axes belong to i and two to j: on its own axis a
            # square's projection is reused across all of its pairs, so only the
            # foreign one has to be recomputed.
            lo_a, hi_a = self.own_projection(i, k) if k < 2 else _project(a, axis)
            lo_b, hi_b = self.own_projection(j, k - 2) if k >= 2 else _project(b, axis)
            if lo_a - hi_b >= 0 or lo_b - hi_a >= 0:
                return mpf(0)
        return -separation(a, b, axes=axes)


@dataclass
class VerifyResult:
    source: str
    n: int
    s: object
    ok: bool
    max_overlap: object  # penetration depth of the worst pair (0 = contacts only)
    worst_pair: tuple | None
    max_outside: object  # how far the worst corner sticks out of the container
    problems: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mark = "OK " if self.ok else "FAIL"
        return (
            f"{mark} {self.source:<18} n={self.n:<5} s={float(self.s):.12f} "
            f"overlap={float(self.max_overlap):.2e} outside={float(self.max_outside):.2e}"
        )


def check(packing: Packing, *, tol=DEFAULT_TOL, expected_n: int | None = None) -> VerifyResult:
    """Check a packing: every square inside the container and no square overlapping."""
    problems: list[str] = []
    squares = packing.squares
    s = packing.s

    if expected_n is not None and len(squares) != expected_n:
        problems.append(f"{len(squares)} squares, but the table promises {expected_n}")

    # -- Containment ----------------------------------------------------------
    # Not everything is computed exactly: first a float estimate of how far each
    # corner sticks out, then exactly - only for corners that could be the
    # maximum (their float estimate is within FLOAT_SAFE_GAP of the best one).
    # A lagging corner cannot become the maximum: the discrepancy between float
    # and exact values here is ~1e-14, five orders below the threshold.
    s_float = float(s)
    estimates = []
    best_estimate = -float("inf")
    for square in squares:
        for x, y in square.corners:
            xf, yf = float(x), float(y)
            estimate = max(-xf, xf - s_float, -yf, yf - s_float)
            estimates.append(estimate)
            if estimate > best_estimate:
                best_estimate = estimate

    max_outside = mpf(0)
    if best_estimate > -FLOAT_SAFE_GAP:
        cutoff = best_estimate - FLOAT_SAFE_GAP
        index = 0
        for square in squares:
            for x, y in square.corners:
                if estimates[index] >= cutoff:
                    outside = max(-x, x - s, -y, y - s)
                    if outside > max_outside:
                        max_outside = outside
                index += 1
    if max_outside > tol:
        problems.append(f"a square sticks out of the container by {max_outside}")

    # -- Overlap: broad phase on a grid, exact phase is SAT in mpmath ----------
    centers = []
    for square in squares:
        cx, cy = square.center
        centers.append((float(cx), float(cy)))

    cell = DIAG
    grid: dict[tuple[int, int], list[int]] = {}
    for idx, (cx, cy) in enumerate(centers):
        key = (int(math.floor(cx / cell)), int(math.floor(cy / cell)))
        grid.setdefault(key, []).append(idx)

    max_overlap = mpf(0)
    worst_pair: tuple | None = None
    limit = DIAG + 1e-6
    seen: set[tuple[int, int]] = set()
    float_corners = [_float_corners(square) for square in squares]
    geom = _Geometry(squares)
    for (gx, gy), bucket in grid.items():
        neighbours: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbours.extend(grid.get((gx + dx, gy + dy), ()))
        for i in bucket:
            for j in neighbours:
                if j <= i:
                    continue
                pair = (i, j)
                if pair in seen:
                    continue
                seen.add(pair)
                dx = centers[i][0] - centers[j][0]
                dy = centers[i][1] - centers[j][1]
                if dx * dx + dy * dy > limit * limit:
                    continue
                # Middle phase: pairs that are certainly far apart are discarded
                # in float. A pair that survives is checked exactly - approximate
                # arithmetic never returns the verdict "admissible".
                separated, first = _float_verdict(float_corners[i], float_corners[j])
                if separated:
                    continue
                depth = geom.depth(i, j, first)
                if depth > max_overlap:
                    max_overlap = depth
                    worst_pair = pair
    if max_overlap > tol:
        problems.append(f"overlap of depth {max_overlap} in pair {worst_pair}")

    return VerifyResult(
        source=packing.source,
        n=len(squares),
        s=s,
        ok=not problems,
        max_overlap=max_overlap,
        worst_pair=worst_pair,
        max_outside=max_outside,
        problems=problems,
    )


def tight_side(packing: Packing):
    """Smallest axis-aligned square side that contains these squares.

    Answers the question "is the real side smaller than the declared one": if the
    result is noticeably below ``packing.s``, the packing is not pressed tight
    against the walls, and the declared s is not optimal for this configuration.
    """
    xs = [x for sq in packing.squares for x, _ in sq.corners]
    ys = [y for sq in packing.squares for _, y in sq.corners]
    return max(max(xs) - min(xs), max(ys) - min(ys))
