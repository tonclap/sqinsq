"""How precise the registry coordinates are: contacts unrolled by tolerance.

The symbolic triage counts contacts at a strict tolerance and finds almost none. By
itself that proves nothing: perhaps the SVG coordinates are simply numerical and
the real contacts are smeared over 1e-6 rather than 1e-30.

The test is a comparison against a baseline: take entries whose exact expression
for s is ALREADY published (there the configuration is certainly rigid and the
contacts are real) and entries flagged "not yet analytically optimized", and see
at which tolerance each group builds up its structure. The number being compared
is contacts per tilted square: a rigid configuration must have noticeably more of
them than the three degrees of freedom require.

    sqinsq contact-tolerance --base 11 26 29 --target 179 206 103
"""

from __future__ import annotations

import argparse

from sqinsq.paths import snapshot_arg

from mpmath import mpf

from sqinsq import contacts, svgpack, table

TOLERANCES = ["1e-30", "1e-20", "1e-12", "1e-9", "1e-6", "1e-4", "1e-3", "1e-2"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--base", nargs="*", type=int, default=[5, 10, 11, 26, 29, 39, 50])
    ap.add_argument("--target", nargs="*", type=int, default=[179, 206, 207, 103, 131])
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot)
    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = {e.n: e for e in table.parse_table(html)}

    print("contacts per tilted square at different tolerances")
    print("(a rigid configuration needs >= 3 per square for s to be determined)")
    print()
    header = "  n  tilt " + " ".join(f"{t:>7}" for t in TOLERANCES) + "  flag"
    print(header)

    for group, ns in (("baseline (exact s published)", args.base), ("targets", args.target)):
        print(f"--- {group}")
        for n in ns:
            entry = entries.get(n)
            if entry is None:
                print(f"{n:>4}  no such entry")
                continue
            packing = svgpack.load(snap / "svg" / entry.svg)
            cells = []
            n_tilted = None
            for tol in TOLERANCES:
                report = contacts.analyse(packing, tol=mpf(tol))
                n_tilted = report.n_tilted
                per = report.equations / n_tilted if n_tilted else 0
                cells.append(f"{per:>7.2f}")
            mark = "NOT optimized" if entry.not_yet_optimized else ""
            print(f"{n:>4} {n_tilted:>5} " + " ".join(cells) + f"  {mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
