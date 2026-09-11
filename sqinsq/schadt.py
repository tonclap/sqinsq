"""The text coordinate format from Schadt's repository - reading and writing.

This is the format the foreign verifier `check.py` reads, and therefore the
format results are exchanged in. Parsing used to live in seven places (`polish`,
`make_svg`, `refine_polished`, `pick_best`, `verify_external` and two reporting
scripts), and the copies had already drifted: in one of them the side regex had
no exponent, so on a value like `1.7e1` it would silently read "1.7". Here there
is one copy.

The coordinate convention is the main source of confusion in this format:

* in the FILE the container is centred, coordinates lie in [-s/2, s/2];
* inside this project a packing lives in [0, s].

So `read` returns the file as it is, and `to_packing` returns a shifted packing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mpmath import cos, mp, mpf, pi, sin

from .svgpack import Packing, UnitSquare

SIDE_RE = re.compile(r"Final\s+s:\s*([-\d.eE+]+)")
SQUARE_RE = re.compile(
    r"Square\s+\d+:\s*x=([-\d.eE+]+),\s*y=([-\d.eE+]+),\s*deg=([-\d.eE+]+)"
)
_HALF = mpf(1) / 2


@dataclass
class Record:
    """Contents of a file: the side and square centres in the centred frame."""

    side: object
    rows: list[tuple]  # (x, y, deg) - lines of the file, already as mpf
    source: str

    @property
    def n(self) -> int:
        return len(self.rows)


def read(path: Path) -> Record:
    text = Path(path).read_text(encoding="utf-8")
    match = SIDE_RE.search(text)
    if not match:
        raise ValueError(f"{path}: no 'Final s:' line - this is not a coordinate file")
    rows = [(mpf(x), mpf(y), mpf(deg)) for x, y, deg in SQUARE_RE.findall(text)]
    if not rows:
        raise ValueError(f"{path}: not a single 'Square N: ...' line")
    return Record(side=mpf(match.group(1)), rows=rows, source=Path(path).name)


def side_of(path: Path):
    """Only the side - when parsing coordinates is pointless (selection, reporting)."""
    text = Path(path).read_text(encoding="utf-8")
    match = SIDE_RE.search(text)
    if not match:
        raise ValueError(f"{path}: no 'Final s:' line - this is not a coordinate file")
    return mpf(match.group(1))


def centers_in_container(record: Record) -> list[tuple]:
    """Centres in the [0, s] frame - the one the rest of the code works in."""
    half = record.side / 2
    return [(x + half, y + half, deg) for x, y, deg in record.rows]


def to_packing(source) -> Packing:
    """A packing from a file (or an already parsed record), in the [0, s] frame.

    Checking the in-memory state is not enough: what goes into the file is a
    rounded decimal, and it is that decimal which has to be admissible.
    """
    record = source if isinstance(source, Record) else read(source)
    squares = []
    for cx, cy, deg in centers_in_container(record):
        angle = deg * pi / 180
        c, s = cos(angle), sin(angle)
        squares.append(
            UnitSquare(
                corners=[
                    (cx + dx * c - dy * s, cy + dx * s + dy * c)
                    for dx, dy in ((-_HALF, -_HALF), (_HALF, -_HALF), (_HALF, _HALF), (-_HALF, _HALF))
                ]
            )
        )
    return Packing(
        s=record.side, squares=squares, source=record.source, entities={}, warnings=[]
    )


def reach_of(rows: list[tuple]):
    """Largest absolute corner coordinate - half of the extent.

    Computed from exactly the lines that go into the file: the foreign verifier
    keeps the container as [-S/2, S/2]^2 and measures precisely this.
    """
    reach = mpf(0)
    for x, y, deg in rows:
        angle = mpf(deg) * pi / 180
        c, s = cos(angle), sin(angle)
        cx, cy = mpf(x), mpf(y)
        for dx, dy in ((-_HALF, -_HALF), (_HALF, -_HALF), (_HALF, _HALF), (-_HALF, _HALF)):
            reach = max(reach, abs(cx + dx * c - dy * s), abs(cy + dx * s + dy * c))
    return reach


def write(out_dir: Path, n: int, rows: list[tuple], side, digits: int | None = None):
    """Write a coordinate file. `rows` are already the (x, y, deg) strings printed.

    The side is printed with the same number of digits as the coordinates: a file
    whose side is more precise than its coordinates is misleading - it will be
    checked by the coordinates anyway.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    side_text = mp.nstr(side, digits) if digits else str(side)
    lines = [f"Final s: {side_text}", ""]
    for i, (x, y, deg) in enumerate(rows, start=1):
        lines.append(f"Square {i}: x={x}, y={y}, deg={deg}")
    path = out_dir / f"squares-{n}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
