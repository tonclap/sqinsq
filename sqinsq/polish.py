"""Polishing a published configuration: tighten the side, keep the topology.

Why this is the way in. The registry itself shows that published configurations
are not fully tightened: Ellsworth improved Schadt's s(29) packing by 5.2e-5
after publication, and Schadt writes about his own find: "This particular
solution is most certainly not fully optimized, and minor improvements can still
be made".
32 entries of the table are marked "not yet analytically optimized", that is,
they are the output of annealing that was never brought to a rigid
configuration. We take them as they are and tighten them numerically.

The method is sequential linear programming (SLP):

1. an active set is collected from the current configuration: square-square
   contacts (with a fixed separating axis) and square-wall contacts;
2. the constraints are linearised in the displacements (dx, dy, dtheta) and in
   the change of the side ds;
3. inside a trust region the LP "minimise ds" is solved;
4. the step is applied, the set is rebuilt, the trust region adapts.

The linearisation makes the constraint set approximate, so the truth here is not
convergence of the LP but the exact verifier from ``verify``: a step is accepted
only if the mpmath check confirms the packing. This is the same rule the solver
follows: an "improvement of 1e-12" without exact geometry is not a record.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from .svgpack import Packing

# Corner offsets of a unit square from its centre, before rotation.
OFFSETS = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]])


@dataclass
class State:
    """A configuration in float: centres, angles (radians) and container side."""

    cx: np.ndarray
    cy: np.ndarray
    th: np.ndarray
    s: float

    @property
    def n(self) -> int:
        return len(self.cx)

    def copy(self) -> "State":
        return State(self.cx.copy(), self.cy.copy(), self.th.copy(), self.s)

    def corners(self) -> np.ndarray:
        """(n, 4, 2) - the corners of every square."""
        cos, sin = np.cos(self.th), np.sin(self.th)
        rot = np.stack(
            [np.stack([cos, -sin], axis=-1), np.stack([sin, cos], axis=-1)], axis=-2
        )  # (n, 2, 2)
        local = OFFSETS[None, :, :]  # (1, 4, 2)
        pts = np.einsum("nij,nkj->nki", rot, np.repeat(local, self.n, axis=0))
        pts[:, :, 0] += self.cx[:, None]
        pts[:, :, 1] += self.cy[:, None]
        return pts

    def dcorners_dtheta(self) -> np.ndarray:
        """(n, 4, 2) - derivative of the corners with respect to theta."""
        cos, sin = np.cos(self.th), np.sin(self.th)
        drot = np.stack(
            [np.stack([-sin, -cos], axis=-1), np.stack([cos, -sin], axis=-1)], axis=-2
        )
        local = np.repeat(OFFSETS[None, :, :], self.n, axis=0)
        return np.einsum("nij,nkj->nki", drot, local)


def state_from_packing(packing: Packing) -> State:
    cx, cy, th = [], [], []
    for square in packing.squares:
        center = square.center
        cx.append(float(center[0]))
        cy.append(float(center[1]))
        (x0, y0), (x1, y1) = square.corners[0], square.corners[1]
        th.append(float(np.arctan2(float(y1 - y0), float(x1 - x0))))
    return State(np.array(cx), np.array(cy), np.array(th), float(packing.s))


def _axes(state: State) -> np.ndarray:
    """(n, 2, 2) - the two edge normals of every square."""
    cos, sin = np.cos(state.th), np.sin(state.th)
    return np.stack(
        [np.stack([cos, sin], axis=-1), np.stack([-sin, cos], axis=-1)], axis=-2
    )


def neighbour_pairs(state: State, margin: float) -> np.ndarray:
    """Pairs whose centres are closer than sqrt(2) + margin: only they can touch."""
    limit = np.sqrt(2.0) + margin
    cell = limit
    grid: dict[tuple[int, int], list[int]] = {}
    for i in range(state.n):
        key = (int(np.floor(state.cx[i] / cell)), int(np.floor(state.cy[i] / cell)))
        grid.setdefault(key, []).append(i)
    pairs = set()
    for (gx, gy), bucket in grid.items():
        near: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(grid.get((gx + dx, gy + dy), ()))
        for i in bucket:
            for j in near:
                if j <= i:
                    continue
                if (state.cx[i] - state.cx[j]) ** 2 + (
                    state.cy[i] - state.cy[j]
                ) ** 2 <= limit * limit:
                    pairs.add((i, j))
    return np.array(sorted(pairs), dtype=int).reshape(-1, 2)


def pair_separation(state: State, pairs: np.ndarray):
    """For every pair: the best separating axis and the gap along it.

    The roles are fixed: i = pairs[:, 0], j = pairs[:, 1]. The axis ``u`` is
    oriented so that the gap equals ``min_k u.P_i[k] - max_m u.P_j[m]``: a
    positive gap means i lies entirely "to the right" of j along u, i.e. apart.

    There are eight candidates: two edge normals of each square, in both senses.

    Returns (gap, owner, axis, k_i, k_j, a, direction). ``owner`` is needed
    because the axis rotates together with its own square, which contributes to
    the derivative; (owner, a, direction) together allow the same axis to be
    reconstructed in exact arithmetic (see ``refine``).
    """
    pts = state.corners()
    axes = _axes(state)
    m = len(pairs)
    i_idx, j_idx = pairs[:, 0], pairs[:, 1]
    ar = np.arange(m)

    best_gap = np.full(m, -np.inf)
    best_axis = np.zeros((m, 2))
    best_owner = np.zeros(m, dtype=int)
    best_ki = np.zeros(m, dtype=int)
    best_kj = np.zeros(m, dtype=int)
    best_a = np.zeros(m, dtype=int)
    best_dir = np.ones(m)

    for side in (0, 1):
        owner = pairs[:, side]
        for a in (0, 1):
            for direction in (1.0, -1.0):
                u = axes[owner, a] * direction  # (m, 2)
                proj_i = np.einsum("mkd,md->mk", pts[i_idx], u)
                proj_j = np.einsum("mkd,md->mk", pts[j_idx], u)
                ki = np.argmin(proj_i, axis=1)
                kj = np.argmax(proj_j, axis=1)
                gap = proj_i[ar, ki] - proj_j[ar, kj]
                better = gap > best_gap
                best_gap = np.where(better, gap, best_gap)
                best_axis = np.where(better[:, None], u, best_axis)
                best_owner = np.where(better, owner, best_owner)
                best_ki = np.where(better, ki, best_ki)
                best_kj = np.where(better, kj, best_kj)
                best_a = np.where(better, a, best_a)
                best_dir = np.where(better, direction, best_dir)
    return best_gap, best_owner, best_axis, best_ki, best_kj, best_a, best_dir


def slp_step(
    state: State,
    *,
    trust: float,
    contact_margin: float,
    safety: float,
    exact=None,
):
    """One SLP step. Returns a new state, or None if the LP did not solve.

    ``safety`` is the margin by which the linearised constraints are tightened
    beyond what is necessary. It covers the second-order linearisation error
    (~trust^2), so the step stays admissible in exact geometry too, not only in
    the linear model. As the trust region shrinks, the margin shrinks with it.

    ``exact`` (``refine.Exact``) enables iterative refinement: the derivatives
    stay in float64 - their precision is enough, they only set a direction -
    while the right-hand sides are computed in mpmath and converted to float as
    DIFFERENCES. A difference of order 1e-14 survives the conversion with
    relative error 1e-16, that is absolute 1e-30, so every iteration adds ~15
    digits instead of stalling at 1e-16 of a coordinate of order 10.
    """
    n = state.n
    nvar = 3 * n + 1
    pts = state.corners()
    dpts = state.dcorners_dtheta()

    rows_i: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    rhs: list[float] = []

    def add_row(entries, bound):
        r = len(rhs)
        for idx, value in entries:
            rows_i.append(r)
            cols.append(int(idx))
            vals.append(float(value))
        rhs.append(bound)

    # -- Containment: 0 <= corner <= s ---------------------------------------
    for i in range(n):
        for k in range(4):
            for axis, base in ((0, 0), (1, n)):
                c = pts[i, k, axis]
                dc = dpts[i, k, axis]
                if exact is None:
                    low, high = c, state.s - c
                else:
                    ce = exact.corners[i][k][axis]
                    low, high = float(ce), float(exact.s - ce)
                # c + dc*dθ + dcenter >= safety
                add_row([(base + i, -1.0), (2 * n + i, -dc)], low - safety)
                # c + dc*dθ + dcenter <= (s + ds) - safety
                add_row(
                    [(base + i, 1.0), (2 * n + i, dc), (3 * n, -1.0)],
                    high - safety,
                )

    # -- Non-intersection along a fixed separating axis ----------------------
    pairs = neighbour_pairs(state, margin=contact_margin + 4 * trust)
    active = 0
    reach = 8 * trust  # how far a corner can travel into the active set per step
    if len(pairs):
        gap, owner, axis, ki, kj, a_idx, a_dir = pair_separation(state, pairs)
        keep = gap < contact_margin + 4 * trust
        for idx in np.nonzero(keep)[0]:
            i, j = int(pairs[idx, 0]), int(pairs[idx, 1])
            u = axis[idx]
            perp = np.array([-u[1], u[0]])
            owner_i = int(owner[idx])

            proj_i = pts[i] @ u
            proj_j = pts[j] @ u
            # The gap is min over the corners of i minus max over those of j,
            # that is, a minimum of several linear functions. For nearly parallel
            # squares the minimum is attained at two corners at once, and
            # linearising on one of them overstates the gap: under rotation it is
            # the other one that drops. Hence every corner that can become active.
            near_i = np.nonzero(proj_i <= proj_i.min() + reach)[0]
            near_j = np.nonzero(proj_j >= proj_j.max() - reach)[0]
            u_exact = (
                None
                if exact is None
                else exact.axis(owner_i, int(a_idx[idx]), float(a_dir[idx]))
            )
            for k in near_i:
                for m in near_j:
                    if exact is None:
                        g = float(proj_i[k] - proj_j[m])
                    else:
                        # The difference of corners is taken in mpmath BEFORE
                        # conversion: the projections alone are of order 10, their
                        # difference is of order of the gap, and only it survives.
                        g = float(exact.projection_gap(i, k, j, m, u_exact))
                    diff = pts[i, k] - pts[j, m]
                    entries = [
                        (i, u[0]),
                        (n + i, u[1]),
                        (2 * n + i, float(u @ dpts[i, k])),
                        (j, -u[0]),
                        (n + j, -u[1]),
                        (2 * n + j, float(-u @ dpts[j, m])),
                        # The axis rotates together with its own square.
                        (2 * n + owner_i, float(perp @ diff)),
                    ]
                    # g + grad·Δ >= safety  →  -grad·Δ <= g - safety
                    add_row([(c, -v) for c, v in entries], g - safety)
                    active += 1

    a_ub = coo_matrix(
        (vals, (rows_i, cols)), shape=(len(rhs), nvar)
    ).tocsr()
    # The problem is made dimensionless: variables are measured in units of trust,
    # right-hand sides are divided by trust. Without this HiGHS treats a
    # constraint as satisfied within an ABSOLUTE tolerance of ~1e-7, and at
    # trust=1e-13 the whole scale of the problem drowns in that tolerance - the
    # solver confidently returns a step that pushes squares 1.5*trust out of the
    # container. After the division the constraint scale is ~1, and the same
    # tolerance means 1e-7*trust.
    b_ub = np.array(rhs) / trust
    cost = np.zeros(nvar)
    cost[3 * n] = 1.0  # minimise ds

    bounds = [(-1.0, 1.0)] * nvar
    res = linprog(cost, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        return None, active, None
    z = res.x * trust
    new = state.copy()
    new.cx = state.cx + z[:n]
    new.cy = state.cy + z[n : 2 * n]
    new.th = state.th + z[2 * n : 3 * n]
    new.s = state.s + z[3 * n]
    # The raw step is returned separately: on the exact stage it cannot be
    # recovered by subtraction (new - state): there 1e-14 meets a coordinate of
    # order 10, and the digits burn.
    return new, active, z


def worst_violation(state: State) -> float:
    """Largest violation: overlap or escape from the container (in float)."""
    pts = state.corners()
    outside = max(
        float(-pts[:, :, 0].min()),
        float(pts[:, :, 0].max() - state.s),
        float(-pts[:, :, 1].min()),
        float(pts[:, :, 1].max() - state.s),
    )
    pairs = neighbour_pairs(state, margin=0.0)
    overlap = 0.0
    if len(pairs):
        gap = pair_separation(state, pairs)[0]
        overlap = float(max(0.0, -gap.min()))
    return max(outside, overlap)
