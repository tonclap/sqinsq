"""Generate the registry-format SVG and close the loop: read it back and check it.

A picture that describes different numbers from the value claimed next to it is
worse than no picture at all: it looks like evidence and is not. So this is not
"drawn and done": the generated SVG is immediately read by our own registry
parser, checked by the verifier, and its coordinates compared with the originals.

    sqinsq make-svg --n 179
    sqinsq make-svg --all
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from sqinsq.paths import snapshot_arg

from mpmath import mp, mpf

from sqinsq import schadt, svgemit, svgpack, verify

mp.dps = 60

def load_polished(path: Path):
    """Centres in the [0, s] frame and the side - format parsing is in `sqinsq.schadt`."""
    record = schadt.read(path)
    return schadt.centers_in_container(record), record.side


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--src", default="polished", help="directory with coordinates")
    ap.add_argument("--dst", default="submission", help="where to put the SVGs")
    ap.add_argument("--n", nargs="*", type=int)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot, args.src)
    src_dir = snap / args.src
    out_dir = snap / args.dst
    out_dir.mkdir(exist_ok=True)

    files = sorted(src_dir.glob("squares-*.txt"), key=lambda p: int(p.stem.split("-")[1]))
    if not args.all:
        if not args.n:
            raise SystemExit("pass --n or --all")
        wanted = set(args.n)
        files = [f for f in files if int(f.stem.split("-")[1]) in wanted]
        # A silent "checked: 0, rejected: 0" after a typo in the number reads as
        # success - while nothing has been rebuilt at all.
        missing = sorted(wanted - {int(f.stem.split("-")[1]) for f in files})
        if missing:
            raise SystemExit(
                f"no polished packings for n={missing} in {src_dir}: "
                "run `sqinsq polish` first, or check the number"
            )

    failures = 0
    for path in files:
        n = int(path.stem.split("-")[1])
        centers, side = load_polished(path)
        packing = svgemit.from_centers(centers, side, source=f"square-{n}.svg")

        svg_text = svgemit.to_svg(
            packing,
            comment=(
                f"Improved packing of {n} unit squares.\n"
                "    Obtained by numerically relaxing the packing published in the\n"
                "    squares in squares registry (entry marked "
                '"Not yet analytically optimized").'
            ),
        )
        out_path = out_dir / f"square-{n}.svg"
        out_path.write_text(svg_text, encoding="utf-8")

        # Coordinates are written in the same pass. Building them separately has
        # already produced a mismatch: the pictures were rebuilt after a re-run
        # while `squares-<n>.txt` in the output directory stayed from the previous
        # solver - two different packings in one folder, and the checks could not
        # see it, because each compared itself with its own half.
        shutil.copyfile(path, out_dir / path.name)

        # -- The loop closes: we read what we wrote, with our registry parser ---
        reparsed = svgpack.load(out_path)
        result = verify.check(reparsed, tol=mpf(0), expected_n=n)

        drift = mpf(0)
        for a, b in zip(packing.squares, reparsed.squares):
            for (ax, ay), (bx, by) in zip(a.corners, b.corners):
                drift = max(drift, abs(ax - bx), abs(ay - by))

        ok = result.max_overlap == 0 and reparsed.n == n and drift < mpf("1e-30")
        print(
            f"n={n:<5} squares {reparsed.n:<5} overlap {mp.nstr(result.max_overlap, 3):<9} "
            f"read-back drift {mp.nstr(drift, 3):<9} {'OK' if ok else 'FAIL'}"
        )
        if not ok:
            failures += 1
            for problem in result.problems:
                print(f"      {problem[:140]}")

    print()
    print(f"output directory: {out_dir}")
    print(f"checked: {len(files)}, rejected: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
