"""Parser for the registry SVGs: shapes to unit-square coordinates.

There is no open dataset of coordinates: the only source is the SVG inside the
registry pages ("For more information on each packing, view its SVG's source
code"). The format is unfriendly to a machine:

* high-precision constants live in internal DTD entities ``<!ENTITY s "...">``
  with 30+ digits - those are the ones to take, not the 16 digits of the caption;
* squares are drawn as nested groups with ``translate``/``rotate``/``scale``;
* adjacent squares are often merged into a single ``<path>`` outline
  (``M2,0 V-1 H1 V-2 H0 V0`` is three squares in an L shape, not one);
* outlines with ``fill:none`` are decorative edges over the fill, not figures.

Hence the order of work: expand the entities, walk the tree accumulating the
affine transform, decompose filled rectangles and rectilinear outlines into unit
cells, and return the four corners of every square.

All arithmetic is in ``mpmath`` with room to spare: captions give ~16 digits,
entities give 30+, and losing them at the parsing stage would be pointless.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from mpmath import mp, mpf, cos, sin, sqrt, atan2, pi

mp.dps = 50

SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

ENTITY_RE = re.compile(r'<!ENTITY\s+(\S+)\s+"([^"]*)"\s*>')
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
DOCTYPE_RE = re.compile(r"<!DOCTYPE.*?\]\s*>", re.S)
DOCTYPE_SIMPLE_RE = re.compile(r"<!DOCTYPE[^>\[]*>", re.S)
NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")

# Matrix as in SVG: (a, b, c, d, e, f), x' = a*x + c*y + e; y' = b*x + d*y + f
Matrix = tuple


class SvgParseError(RuntimeError):
    pass


IDENTITY: Matrix = (mpf(1), mpf(0), mpf(0), mpf(1), mpf(0), mpf(0))


def mat_mul(m: Matrix, n: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def apply(m: Matrix, x, y) -> tuple:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(text: str) -> Matrix:
    """SVG transform attribute to an affine matrix (applied left to right)."""
    result = IDENTITY
    pos = 0
    for match in TRANSFORM_RE.finditer(text or ""):
        if text[pos : match.start()].strip():
            raise SvgParseError(f"unparsed piece of transform: {text!r}")
        pos = match.end()
        kind = match.group(1)
        args = [mpf(v) for v in NUM_RE.findall(match.group(2))]
        if kind == "matrix":
            if len(args) != 6:
                raise SvgParseError(f"matrix expects 6 numbers: {match.group(0)!r}")
            m = tuple(args)
        elif kind == "translate":
            tx = args[0] if args else mpf(0)
            ty = args[1] if len(args) > 1 else mpf(0)
            m = (mpf(1), mpf(0), mpf(0), mpf(1), tx, ty)
        elif kind == "scale":
            sx = args[0] if args else mpf(1)
            sy = args[1] if len(args) > 1 else sx
            m = (sx, mpf(0), mpf(0), sy, mpf(0), mpf(0))
        elif kind == "rotate":
            ang = args[0] * pi / 180
            rot = (cos(ang), sin(ang), -sin(ang), cos(ang), mpf(0), mpf(0))
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                m = mat_mul(
                    (mpf(1), mpf(0), mpf(0), mpf(1), cx, cy),
                    mat_mul(rot, (mpf(1), mpf(0), mpf(0), mpf(1), -cx, -cy)),
                )
            else:
                m = rot
        else:
            raise SvgParseError(f"transform {kind} is not supported")
        result = mat_mul(result, m)
    if text and text[pos:].strip():
        raise SvgParseError(f"unparsed tail of transform: {text[pos:]!r}")
    return result


@dataclass
class UnitSquare:
    """A unit square: four corners in traversal order, clockwise or counter."""

    corners: list[tuple]

    @property
    def center(self) -> tuple:
        xs = [p[0] for p in self.corners]
        ys = [p[1] for p in self.corners]
        return (sum(xs) / 4, sum(ys) / 4)

    @property
    def angle_deg(self):
        (x0, y0), (x1, y1) = self.corners[0], self.corners[1]
        return atan2(y1 - y0, x1 - x0) * 180 / pi


@dataclass
class Packing:
    """A packing: the side of the enclosing square and the list of unit squares."""

    s: object
    squares: list[UnitSquare]
    source: str
    entities: dict
    warnings: list[str]

    @property
    def n(self) -> int:
        return len(self.squares)


def _style_of(elem: ET.Element, inherited: dict) -> dict:
    style = dict(inherited)
    raw = elem.get("style", "")
    for part in raw.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            style[key.strip()] = value.strip()
    for attr in ("fill", "stroke"):
        if elem.get(attr) is not None:
            style[attr] = elem.get(attr)
    return style


def _tag(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1]


# The registry uses exactly three fills: #B2B2B2 (the squares themselves), white
# (the container backdrop) and none (decorative edges). White is background.
BACKGROUND_FILLS = {"white", "#fff", "#ffffff"}


def is_background(style: dict) -> bool:
    return style.get("fill", "").strip().lower() in BACKGROUND_FILLS


def _parse_path_polygons(d: str) -> list[list[tuple]]:
    """A rectilinear ``d`` to a list of closed outlines (lists of vertices).

    M/m, L/l, H/h, V/v, Z/z are supported, and that is enough: every filled
    outline in the registry is rectilinear. A curve in a filled outline would mean
    the figure is not a set of unit cells, so we fail loudly instead of skipping.
    """
    tokens = re.findall(r"[MmLlHhVvZzCcSsQqTtAa]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    polys: list[list[tuple]] = []
    current: list[tuple] = []
    x = y = mpf(0)
    start = (x, y)
    i = 0
    cmd = None
    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"[A-Za-z]", tok):
            cmd = tok
            i += 1
            if cmd in "Zz":
                if current:
                    polys.append(current)
                    current = []
                x, y = start
                continue
        if cmd is None:
            raise SvgParseError(f"path does not start with a command: {d!r}")
        if cmd in "MmLl":
            dx, dy = mpf(tokens[i]), mpf(tokens[i + 1])
            i += 2
            if cmd in "ml":
                x, y = x + dx, y + dy
            else:
                x, y = dx, dy
            if cmd in "Mm":
                if current:
                    polys.append(current)
                current = [(x, y)]
                start = (x, y)
                cmd = "l" if cmd == "m" else "L"
            else:
                current.append((x, y))
        elif cmd in "Hh":
            dx = mpf(tokens[i])
            i += 1
            x = x + dx if cmd == "h" else dx
            current.append((x, y))
        elif cmd in "Vv":
            dy = mpf(tokens[i])
            i += 1
            y = y + dy if cmd == "v" else dy
            current.append((x, y))
        else:
            raise SvgParseError(f"path command {cmd!r} is not supported (not rectilinear)")
    if current:
        polys.append(current)
    return polys


def _shoelace(poly: list[tuple]):
    total = mpf(0)
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        total += x0 * y1 - x1 * y0
    return total / 2


def _point_in_poly(px, py, poly: list[tuple]) -> bool:
    inside = False
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        if (y0 > py) != (y1 > py):
            xint = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
            if px < xint:
                inside = not inside
    return inside


MAX_GRID_CELLS = 400_000


def _cells_single_lattice(poly: list[tuple], tol) -> list[tuple] | None:
    """Fast path: every vertex sits on one and the same unit lattice.

    That is how most merged outlines are built. Returns None if there is more than
    one lattice - then the general tiler takes over.

    Since all vertices sit on the lattice, membership of a cell is an integer
    question and is decided exactly: coordinates are doubled (vertices become even,
    cell centres odd) and ray crossings are counted by cross multiplication without
    division. Not one tolerance and not one mpf in the hot loop - and it is
    quadratic in the size of the outline.
    """
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, y0 = min(xs), min(ys)
    ipoly: list[tuple[int, int]] = []
    for px, py in poly:
        cell_x, cell_y = px - x0, py - y0
        ix, iy = round(float(cell_x)), round(float(cell_y))
        if abs(cell_x - ix) > tol or abs(cell_y - iy) > tol:
            return None
        ipoly.append((2 * ix, 2 * iy))

    width = int(round(float(max(xs) - x0)))
    height = int(round(float(max(ys) - y0)))
    edges = [(ipoly[i], ipoly[(i + 1) % len(ipoly)]) for i in range(len(ipoly))]

    found = []
    for j in range(height):
        py = 2 * j + 1
        # The ray is traced row by row: edges that can cross it at all are
        # selected once per row, not again for every cell.
        crossing = [
            ((ax, ay), (bx, by)) for (ax, ay), (bx, by) in edges if (ay > py) != (by > py)
        ]
        if not crossing:
            continue
        for i in range(width):
            px = 2 * i + 1
            inside = False
            for (ax, ay), (bx, by) in crossing:
                dy = by - ay
                # px < ax + (py - ay) * (bx - ax) / dy, without the division
                left, right = (px - ax) * dy, (py - ay) * (bx - ax)
                if left < right if dy > 0 else left > right:
                    inside = not inside
            if inside:
                found.append((i, j))

    # The walk goes by rows (cheaper for selecting edges), but the order of cells
    # must stay column-major: it defines the numbering of squares in the packing,
    # and the pair indices in verifier reports refer to it.
    cells = [(x0 + i, y0 + j) for i, j in sorted(found)]

    area = abs(_shoelace(poly))
    if abs(area - len(cells)) > tol:
        raise SvgParseError(f"outline area {area} differs from the cell count {len(cells)}")
    return cells


def _lattice_lines(coords: list, lo, hi, tol) -> list:
    """All lines of the form "vertex coordinate plus an integer" within range."""
    lines = []
    span = int(float(hi - lo)) + 2
    for c in coords:
        k0 = int(float(lo - c)) - 1
        for k in range(k0, k0 + span + 2):
            value = c + k
            if lo - tol <= value <= hi + tol:
                lines.append(value)
    lines.sort()
    dedup = []
    for value in lines:
        if not dedup or value - dedup[-1] > tol:
            dedup.append(value)
    return dedup


def _cells_general(poly: list[tuple], tol) -> list[tuple]:
    """General tiler: an outline made of squares on different lattices.

    This is how the registry draws "brickwork" - adjacent squares are shifted by a
    non-integer amount relative to each other, and a single lattice is not enough
    (for example ``M0,1 H1 V0 H1.5 V-1 H9.5 ...`` in square-203a).

    Method: cut the plane by all lines "vertex plus an integer", mark the
    subcells inside the outline, then greedily lay unit squares starting from the
    lowest-leftmost uncovered subcell. For a region tileable by unit squares its
    bottom-left corner must be a corner of a tile - which makes the greedy choice
    exact here rather than heuristic.
    """
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    xlines = _lattice_lines(xs, min(xs), max(xs), tol)
    ylines = _lattice_lines(ys, min(ys), max(ys), tol)
    if (len(xlines) - 1) * (len(ylines) - 1) > MAX_GRID_CELLS:
        raise SvgParseError(
            f"grid for parsing the outline is too large: "
            f"{(len(xlines) - 1) * (len(ylines) - 1)} subcells"
        )

    inside: dict[tuple[int, int], bool] = {}
    for i in range(len(xlines) - 1):
        cx = (xlines[i] + xlines[i + 1]) / 2
        for j in range(len(ylines) - 1):
            cy = (ylines[j] + ylines[j + 1]) / 2
            if _point_in_poly(cx, cy, poly):
                inside[(i, j)] = False  # False = not covered by a tile yet

    def index_of(lines: list, value) -> int | None:
        lo, hi = 0, len(lines) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if abs(lines[mid] - value) <= tol:
                return mid
            if lines[mid] < value:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    tiles = []
    for j in range(len(ylines) - 1):
        for i in range(len(xlines) - 1):
            if inside.get((i, j)) is not False:
                continue
            ox, oy = xlines[i], ylines[j]
            i_end = index_of(xlines, ox + 1)
            j_end = index_of(ylines, oy + 1)
            if i_end is None or j_end is None:
                raise SvgParseError(
                    f"outline is not tileable by unit squares: "
                    f"no lattice line at ({ox + 1}, {oy + 1})"
                )
            for ii in range(i, i_end):
                for jj in range(j, j_end):
                    if inside.get((ii, jj)) is not False:
                        raise SvgParseError(
                            "outline is not tileable by unit squares: "
                            f"subcell ({ii}, {jj}) is outside the outline or already taken"
                        )
                    inside[(ii, jj)] = True
            tiles.append((ox, oy))

    area = abs(_shoelace(poly))
    if abs(area - len(tiles)) > tol:
        raise SvgParseError(f"outline area {area} differs from the tile count {len(tiles)}")
    return tiles


def _cells_of_polygon(poly: list[tuple], tol=mpf("1e-9")) -> list[tuple]:
    """A rectilinear outline to a list of bottom-left corners of unit squares."""
    cells = _cells_single_lattice(poly, tol)
    if cells is not None:
        return cells
    return _cells_general(poly, tol)


def load(path: Path | str) -> Packing:
    """Read a packing SVG and return its geometry."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    warnings: list[str] = []

    # Entities refer to each other: <!ENTITY tr1 "translate(1 -&v2;)">.
    # Expand to a fixed point, otherwise an unresolved reference is left inside
    # a substituted value.
    entities = {name: value for name, value in ENTITY_RE.findall(text)}
    for _ in range(16):
        changed = False
        for name, value in list(entities.items()):
            for other, repl in entities.items():
                token = f"&{other};"
                if token in value and other != name:
                    value = value.replace(token, repl)
                    changed = True
            entities[name] = value
        if not changed:
            break
    else:
        raise SvgParseError(f"{path.name}: entities reference each other in a cycle")

    body = DOCTYPE_RE.sub("", text)
    body = DOCTYPE_SIMPLE_RE.sub("", body)
    body = COMMENT_RE.sub("", body)
    # square-71.svg: a closing '-->' with no opening '<!--' - the registry file is
    # not valid XML. We repair it locally, but record it as a noticed defect.
    if "-->" in body:
        warnings.append("dangling '-->' with no opening comment")
        body = body.replace("-->", "")
    for name, value in entities.items():
        body = body.replace(f"&{name};", value)
    leftover = re.findall(r"&(?!amp;|lt;|gt;|quot;|apos;|#)([A-Za-z_][\w.-]*);", body)
    if leftover:
        raise SvgParseError(f"{path.name}: unexpanded entities {sorted(set(leftover))}")

    root = ET.fromstring(body)

    # Map id to element, first occurrence in document order (what a browser does
    # with duplicate ids - and the registry has them: #one is declared twice).
    idmap: dict[str, ET.Element] = {}
    for elem in root.iter():
        eid = elem.get("id")
        if eid and eid not in idmap:
            idmap[eid] = elem

    viewbox = root.get("viewBox")
    if not viewbox:
        raise SvgParseError(f"{path.name}: no viewBox")
    vb = [mpf(v) for v in NUM_RE.findall(viewbox)]
    if len(vb) != 4:
        raise SvgParseError(f"{path.name}: unexpected viewBox {viewbox!r}")
    s = vb[2]
    if abs(vb[2] - vb[3]) > mpf("1e-20"):
        raise SvgParseError(f"{path.name}: viewBox is not square: {viewbox!r}")
    # Some packings are drawn around the origin: viewBox="-hs -hs s s".
    # Everything is shifted so that the container is always [0, s] x [0, s].
    origin: Matrix = (mpf(1), mpf(0), mpf(0), mpf(1), -vb[0], -vb[1])

    squares: list[UnitSquare] = []
    unit_tol = mpf("1e-9")

    # The caches live for exactly one parse: their values are mpf, their precision
    # depends on the current mp.dps, and they must not outlive a change of it.
    transform_cache: dict[str, Matrix] = {}
    rigid_checked: set[Matrix] = set()

    def transform_of(text: str) -> Matrix:
        """A parsed transform. The same strings repeat hundreds of times per file."""
        cached = transform_cache.get(text)
        if cached is None:
            cached = parse_transform(text)
            transform_cache[text] = cached
        return cached

    def check_rigid(m: Matrix) -> None:
        """The matrix must map a unit square onto a unit square.

        Checked on the matrix rather than on every square: the side lengths of the
        image do not depend on the cell offset, they are ``|(a, b)|`` and
        ``|(c, d)|``. Orthogonality is checked here too - four unit sides alone
        still admit a shear (a rhombus), which the old per-side check let through.
        """
        if m in rigid_checked:
            return
        a, b, c, d = m[0], m[1], m[2], m[3]
        for length in (sqrt(a * a + b * b), sqrt(c * c + d * d)):
            if abs(length - 1) > unit_tol:
                raise SvgParseError(
                    f"{path.name}: side {length} is not 1 - the transform is not rigid"
                )
        if abs(a * c + b * d) > unit_tol:
            raise SvgParseError(
                f"{path.name}: transform is not orthogonal (shear): {m}"
            )
        rigid_checked.add(m)

    def emit_quad(m: Matrix, ox, oy) -> None:
        check_rigid(m)
        squares.append(
            UnitSquare(
                corners=[
                    apply(m, ox, oy),
                    apply(m, ox + 1, oy),
                    apply(m, ox + 1, oy + 1),
                    apply(m, ox, oy + 1),
                ]
            )
        )

    def walk(elem: ET.Element, m: Matrix, style: dict, depth: int = 0) -> None:
        if depth > 64:
            raise SvgParseError(f"{path.name}: nesting too deep (a cycle in use?)")
        tag = _tag(elem)
        if tag in ("defs", "script", "title", "desc", "metadata", "style"):
            return
        own_style = _style_of(elem, style)
        m = mat_mul(m, transform_of(elem.get("transform", "")))
        filled = own_style.get("fill", "black").strip().lower() != "none"

        if tag in ("svg", "g", "a"):
            for child in elem:
                walk(child, m, own_style, depth + 1)
            return

        if tag == "use":
            href = elem.get(XLINK_HREF) or elem.get("href")
            if not href:
                raise SvgParseError(f"{path.name}: use without a reference")
            if not href.startswith("#"):
                # square-273.svg: xlink:href="corner" with no hash. By the spec
                # that is a reference to an external file, not to an element of
                # this document: a browser does not resolve it and draws nothing.
                # We repeat that behaviour - otherwise we get 275 squares instead
                # of 273, doubling a pair that the file already draws explicitly.
                warnings.append(
                    f"use xlink:href={href!r} without '#' - not resolved, as in a browser"
                )
                return
            target = idmap.get(href[1:])
            if target is None:
                raise SvgParseError(f"{path.name}: use refers to {href!r}, which is absent")
            dx = mpf(elem.get("x", "0"))
            dy = mpf(elem.get("y", "0"))
            m2 = mat_mul(m, (mpf(1), mpf(0), mpf(0), mpf(1), dx, dy))
            walk(target, m2, own_style, depth + 1)
            return

        if tag == "rect":
            if not filled or is_background(own_style):
                return
            w = mpf(elem.get("width", "0"))
            h = mpf(elem.get("height", "0"))
            x = mpf(elem.get("x", "0"))
            y = mpf(elem.get("y", "0"))
            # Trivial packings are drawn as a single rectangle over the whole block:
            # <rect width="2" height="2"/> is four squares, not one.
            wi, hi = int(round(float(w))), int(round(float(h)))
            if abs(w - wi) > unit_tol or abs(h - hi) > unit_tol or wi < 1 or hi < 1:
                raise SvgParseError(
                    f"{path.name}: filled rectangle {w}x{h} does not split "
                    "into a whole number of unit cells"
                )
            for i in range(wi):
                for j in range(hi):
                    emit_quad(m, x + i, y + j)
            return

        if tag == "path":
            if not filled or is_background(own_style):
                return
            for poly in _parse_path_polygons(elem.get("d", "")):
                if len(poly) < 3:
                    continue
                for ox, oy in _cells_of_polygon(poly):
                    emit_quad(m, ox, oy)
            return

        if tag in ("line", "polyline"):
            return
        if tag == "circle":
            # square-71.svg still has an unclosed debug marker (a blue dot,
            # r=0.005) - a defect of the registry file, not ours. It is not a
            # figure of the packing; noted and skipped, but not silently.
            warnings.append(f"<circle> in the markup ignored: {elem.attrib}")
            return
        raise SvgParseError(f"{path.name}: element <{tag}> is not supported")

    walk(root, origin, {}, 0)
    return Packing(
        s=s, squares=squares, source=path.name, entities=entities, warnings=warnings
    )
