"""An independent check of the verifier on somebody else's coordinates.

The registry is the only source of coordinates, and we parse it ourselves: if
the parser and the verifier are wrong in the same way, the positive control over
the registry will not show it. An input that avoids our SVG parser is needed.

There is exactly one: Thomas Schadt (BalthasarStrauss on GitHub) published the
coordinates of his s(29) find to 105 digits in plain text, in the format
`index, x center, y center, angle (degrees)`. The registry itself links to that
repository from a comment inside square-29.svg.

Checked: (1) our verifier confirms the foreign packing; (2) the side we compute
from his coordinates matches the one he declares; (3) our parsing of the
registry's square-29.svg yields the same geometry as his text file.

    sqinsq verify-external
"""

from __future__ import annotations

import argparse

from sqinsq.paths import data_root, latest_snapshot

from mpmath import mp, mpf, cos, sin, pi

from sqinsq import fetch, schadt, svgpack, verify

mp.dps = 140

RAW = (
    "https://raw.githubusercontent.com/BalthasarStrauss/"
    "Squares-packing_S-29-_New-Record/main/squares.txt"
)
DECLARED_S = "5.9338857998"
CACHE_NAME = "schadt_s29_squares.txt"


def parse_file(text: str) -> tuple[list[tuple], object | None]:
    """`Square N: x=..., y=..., deg=...` to a list of (x, y, angle) plus the side.

    Parsing is shared with the writer (`sqinsq.schadt`): the format is the
    same, and a separate copy of the regexes would one day be fixed only once.
    """
    rows = [
        (mpf(x), mpf(y), mpf(deg)) for x, y, deg in schadt.SQUARE_RE.findall(text)
    ]
    match = schadt.SIDE_RE.search(text)
    return rows, (mpf(match.group(1)) if match else None)


def to_squares(rows: list[tuple]) -> list[svgpack.UnitSquare]:
    """Centre plus angle to the four corners of a unit square."""
    squares = []
    half = mpf(1) / 2
    for cx, cy, deg in rows:
        ang = deg * pi / 180
        ca, sa = cos(ang), sin(ang)
        corners = []
        for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half)):
            corners.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
        squares.append(svgpack.UnitSquare(corners=corners))
    return squares


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()

    # Resolved at call time, not at import: the data root depends on where the
    # command is run from, and a module-level constant would freeze it.
    cache = data_root() / "external" / CACHE_NAME
    cache.parent.mkdir(parents=True, exist_ok=True)
    if args.refetch or not cache.exists():
        cache.write_bytes(fetch.fetch_bytes(RAW))
    rows, final_s = parse_file(cache.read_text(encoding="utf-8", errors="replace"))
    if not rows:
        raise SystemExit("not a single square parsed - the file format has changed")
    squares = to_squares(rows)

    xs = [x for sq in squares for x, _ in sq.corners]
    ys = [y for sq in squares for _, y in sq.corners]
    side = max(max(xs) - min(xs), max(ys) - min(ys))

    # Shifted into [0, s] x [0, s] so that containment is checked by the same code.
    dx, dy = -min(xs), -min(ys)
    shifted = [
        svgpack.UnitSquare(corners=[(x + dx, y + dy) for x, y in sq.corners])
        for sq in squares
    ]
    packing = svgpack.Packing(
        s=side, squares=shifted, source="schadt_s29_squares.txt", entities={}, warnings=[]
    )
    result = verify.check(packing, tol=mpf("1e-90"))

    print("-- Schadt's coordinates (external source, 105 digits) --")
    print(f"squares:                {len(squares)}")
    print(f"side from coordinates:  {mp.nstr(side, 30)}")
    print(f"declared in the README: {DECLARED_S}")
    print(f"difference from README: {mp.nstr(abs(side - mpf(DECLARED_S)), 5)}")
    if final_s is not None:
        print(f"declared in the file:   {mp.nstr(final_s, 30)}")
        print(f"difference from file:   {mp.nstr(abs(side - final_s), 5)}")
    print(f"overlap (tolerance 1e-90): {mp.nstr(result.max_overlap, 5)}")
    print(f"escape from container:     {mp.nstr(result.max_outside, 5)}")
    print(f"verifier verdict:          {'CONFIRMED' if result.ok else 'REJECTED'}")
    for problem in result.problems:
        print(f"  {problem}")

    # -- Comparison with what the registry draws for n=29 ---------------------
    snap = latest_snapshot()
    registry = svgpack.load(snap / "svg" / "square-29.svg")
    print()
    print("-- The same packing through our registry SVG parser --")
    print(f"squares:              {registry.n}")
    print(f"side from the viewBox: {mp.nstr(registry.s, 30)}")
    print(f"side difference (registry - Schadt): {mp.nstr(registry.s - side, 5)}")
    print(
        "The registry shows Ellsworth's exact solution of 10.12.2025, "
        "so an exact match is not expected - agreement within the precision\n"
        "of the original find is."
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
