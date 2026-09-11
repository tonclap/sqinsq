"""Tools for the registry of best known packings of unit squares in a square.

Modules:
    fetch     - dated snapshot of the registry (HTML plus every SVG)
    table     - parser for the registry table: n, s, attribution, flags
    svgpack   - parser for the SVGs: shapes to square coordinates
    verify    - verifier: containment and absence of overlap
"""

__all__ = ["fetch", "table", "svgpack", "verify"]
