"""Writing a packing out as SVG in the registry's format.

The registry's own rules ask for a picture matching the original in
"orientation, color, pixel size, file type, and name", with no frame and no text.
The registry draws packings in a recognisable style: the side is lifted into a
DTD entity, ``viewBox="0 0 &s; &s;"``, grey fill ``#B2B2B2`` over a white
backdrop, every square a ``<use xlink:href="#one">`` with its own transform.

The value of this module is not the picture but the **closed loop**: what we
generate is read back by our own parser and checked by the verifier. If the loop
closes, the picture describes exactly the numbers claimed alongside it, and not
approximately those.
"""

from __future__ import annotations

from mpmath import mp, mpf, atan2, cos, pi, sin

from .svgpack import Packing

HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!--
{comment}
-->
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [
    <!ENTITY s "{s}">
]>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" \
width="100%" height="100%" viewBox="0 0 &s; &s;" \
style="fill:#B2B2B2; stroke:black; stroke-width:0.0013" id="svg">
    <defs>
        <rect width="&s;" height="&s;" id="outer"/>
        <rect width="1" height="1" id="one"/>
    </defs>
    <use xlink:href="#outer" style="fill:white; stroke:none"/>
"""

FOOTER = """    <use xlink:href="#outer" style="fill:none"/>
</svg>
"""


def _corner_and_angle(square, digits: int):
    """Bottom-left corner of a square and its rotation, as the registry writes them."""
    (x0, y0), (x1, y1) = square.corners[0], square.corners[1]
    ang = atan2(y1 - y0, x1 - x0)
    return x0, y0, ang * 180 / pi


def to_svg(packing: Packing, *, comment: str = "", digits: int = 34) -> str:
    """A packing to SVG text in the registry style."""
    parts = [
        HEADER.format(
            comment=comment.strip() or "Packing of unit squares.",
            s=mp.nstr(packing.s, digits),
        )
    ]
    for square in packing.squares:
        x, y, deg = _corner_and_angle(square, digits)
        if abs(deg) < mpf(10) ** -(digits - 4):
            transform = f"translate({mp.nstr(x, digits)} {mp.nstr(y, digits)})"
        else:
            transform = (
                f"translate({mp.nstr(x, digits)} {mp.nstr(y, digits)}) "
                f"rotate({mp.nstr(deg, digits)})"
            )
        parts.append(f'    <use xlink:href="#one" transform="{transform}"/>\n')
    parts.append(FOOTER)
    return "".join(parts)


def from_centers(centers, side, *, source: str = "generated") -> Packing:
    """(x, y, angle in degrees) plus the side, to a packing."""
    from .svgpack import UnitSquare

    half = mpf(1) / 2
    squares = []
    for cx, cy, deg in centers:
        ang = mpf(deg) * pi / 180
        ca, sa = cos(ang), sin(ang)
        corners = [
            (mpf(cx) + dx * ca - dy * sa, mpf(cy) + dx * sa + dy * ca)
            for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half))
        ]
        squares.append(UnitSquare(corners=corners))
    return Packing(
        s=mpf(side), squares=squares, source=source, entities={}, warnings=[]
    )
