"""Contact graph of a packing, and triage for the symbolic track.

The question behind it: 32 registry entries are marked "Not yet analytically optimized" - the
configuration was found numerically, but there is no exact expression for the
side. Deriving one means writing the system of contact equations and solving it
symbolically. Before doing that one has to know which of the 32 are tractable at
all: the size of the system is set not by the number of squares n, but by the
number of TILTED squares and of distinct angles.

Axis-aligned squares (angle a multiple of 90 degrees) almost always just fill
the gaps in a grid: they do not take part in determining s, and dragging them
into a symbolic system is pointless.

Only the structure is computed here. No equations - that is the next step.
"""

from __future__ import annotations

from dataclasses import dataclass

from mpmath import mpf, fmod

from .svgpack import Packing, UnitSquare
from .verify import separation

CONTACT_TOL = mpf("1e-12")
ANGLE_TOL = mpf("1e-9")


def normalized_angle(square: UnitSquare):
    """Square angle reduced to [0, 90) - a square repeats itself every 90 degrees."""
    ang = fmod(square.angle_deg, 90)
    if ang < 0:
        ang += 90
    if 90 - ang < ANGLE_TOL:
        ang = mpf(0)
    return ang


def is_axis_aligned(square: UnitSquare) -> bool:
    return normalized_angle(square) < ANGLE_TOL


@dataclass
class ContactReport:
    source: str
    n: int
    s: object
    tilted: list[int]
    angles: list  # the distinct tilt angles, ascending
    contacts_square: list[tuple[int, int]]
    contacts_wall: list[tuple[int, str]]

    @property
    def n_tilted(self) -> int:
        return len(self.tilted)

    @property
    def n_angles(self) -> int:
        return len(self.angles)

    @property
    def unknowns(self) -> int:
        """Unknowns of the symbolic system: 3 per tilted square, plus s itself."""
        return 3 * self.n_tilted + 1

    @property
    def equations(self) -> int:
        return len(self.contacts_square) + len(self.contacts_wall)


def analyse(packing: Packing, *, tol=CONTACT_TOL) -> ContactReport:
    """Build the contact graph and isolate the tilted part of the packing."""
    squares = packing.squares
    s = packing.s

    tilted = [i for i, sq in enumerate(squares) if not is_axis_aligned(sq)]

    angles: list = []
    for i in tilted:
        ang = normalized_angle(squares[i])
        if not any(abs(ang - a) < ANGLE_TOL for a in angles):
            angles.append(ang)
    angles.sort()

    # Square-square contacts: only those involving a tilted square are counted -
    # contacts inside an axis-aligned block do not determine the solution.
    tilted_set = set(tilted)
    contacts_square: list[tuple[int, int]] = []
    for idx, i in enumerate(tilted):
        for j in range(len(squares)):
            if j == i or (j in tilted_set and j <= i):
                continue
            ci = squares[i].center
            cj = squares[j].center
            if (ci[0] - cj[0]) ** 2 + (ci[1] - cj[1]) ** 2 > 3:
                continue
            if abs(separation(squares[i], squares[j])) <= tol:
                contacts_square.append((i, j))
        del idx

    contacts_wall: list[tuple[int, str]] = []
    for i in tilted:
        for x, y in squares[i].corners:
            for value, name in ((x, "left"), (s - x, "right"), (y, "bottom"), (s - y, "top")):
                if abs(value) <= tol:
                    pair = (i, name)
                    if pair not in contacts_wall:
                        contacts_wall.append(pair)

    return ContactReport(
        source=packing.source,
        n=len(squares),
        s=s,
        tilted=tilted,
        angles=angles,
        contacts_square=contacts_square,
        contacts_wall=contacts_wall,
    )
