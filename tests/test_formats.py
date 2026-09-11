"""Round-trips through the two formats this project has to read and write.

The SVG on the registry page is the only place the published coordinates exist:
there is no data file behind it. So the parser in `sqinsq.svgpack` is not a
convenience — it is the single copy of "what the registry actually says", and a
silent misread would produce wrong numbers with full confidence.

Both tests below are round-trips rather than fixtures on purpose: a fixture
pins one file, a round-trip pins the *relationship* between writing and reading,
which is what breaks when either side is refactored.
"""

from __future__ import annotations

from mpmath import mpf

from sqinsq import schadt, svgpack
from sqinsq.svgemit import from_centers, to_svg

# Three squares, one axis-aligned, one rotated by a plain angle, one rotated by
# an angle with no short decimal form — the third is the one that catches
# precision loss in the emitter.
#
# Centres are 1.5 apart, comfortably above the sqrt(2) diameter of a unit
# square, so the packing is valid whatever the rotations are. That is not
# fussiness: at spacing 1.0 the rotated square overlaps its axis-aligned
# neighbour by 0.183, and the round-trip test would then be failing on invalid
# input while looking like a parser bug.
CENTERS = [
    (mpf("0.75"), mpf("0.75"), mpf(0)),
    (mpf("2.25"), mpf("0.75"), mpf(30)),
    (mpf("0.75"), mpf("2.25"), mpf("17.3456789012345678901234567890")),
]


def test_svg_round_trip_preserves_geometry(tmp_path):
    """Emit a packing as registry-style SVG, parse it back, compare corners."""
    original = from_centers(CENTERS, 3)

    path = tmp_path / "square-3.svg"
    path.write_text(to_svg(original, comment="round-trip test"), encoding="utf-8")
    reparsed = svgpack.load(path)

    assert reparsed.n == original.n
    assert abs(reparsed.s - original.s) < mpf("1e-25")

    for before, after in zip(original.squares, reparsed.squares):
        for (x0, y0), (x1, y1) in zip(before.corners, after.corners):
            assert abs(x1 - x0) < mpf("1e-25")
            assert abs(y1 - y0) < mpf("1e-25")


def test_svg_round_trip_survives_the_verifier(tmp_path):
    """A packing that was valid before emission is still valid after re-reading.

    Weaker than the corner comparison above and worth having anyway: it is the
    check `sqinsq make-svg` actually performs on every file it writes.
    """
    from sqinsq import verify

    original = from_centers(CENTERS, 3)
    path = tmp_path / "square-3.svg"
    path.write_text(to_svg(original), encoding="utf-8")

    assert verify.check(svgpack.load(path), tol=mpf(0), expected_n=3).ok


def test_coordinate_file_round_trip(tmp_path):
    """Schadt's coordinate format: what we write is what we read back."""
    rows = [(mpf("0.5"), mpf("0.5"), mpf(0)), (mpf("-0.5"), mpf("0.25"), mpf("12.5"))]
    side = mpf("2.25")

    path = schadt.write(tmp_path, 2, rows, side, digits=40)
    record = schadt.read(path)

    assert record.n == 2
    assert abs(record.side - side) < mpf("1e-30")
    for (x0, y0, d0), (x1, y1, d1) in zip(rows, record.rows):
        assert abs(x1 - x0) < mpf("1e-30")
        assert abs(y1 - y0) < mpf("1e-30")
        assert abs(d1 - d0) < mpf("1e-30")


def test_coordinate_file_without_side_is_refused(tmp_path):
    """A file with no `Final s:` line is not a coordinate file — say so, don't guess."""
    path = tmp_path / "squares-2.txt"
    path.write_text("Square 1: x=0, y=0, deg=0\n", encoding="utf-8")

    try:
        schadt.read(path)
    except ValueError:
        return
    raise AssertionError("a file without a side was accepted as a coordinate file")
