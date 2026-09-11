"""Selecting the best result for every n across several runs.

Polishing is not deterministic in outcome: different LP formulations reach
different local optima, and no branch wins everywhere (one re-run gave 18
entries better in the new branch and 14 better in the old, spread up to 8e-5).
Taking "the last run" means silently losing what was already obtained; taking
"the best" without recording where it came from means losing reproducibility.

Hence: the minimum side across the sources, an exact check of precisely the file
that was selected, and a provenance table in `pick.csv` showing which entry came
from which branch.

    sqinsq pick-best --src polished-old-refined polished-fresh --dst polished
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil

from sqinsq.paths import work_snapshot

from mpmath import mp, mpf

from sqinsq.commands.polish import packing_from_file
from sqinsq import schadt, verify

mp.dps = 60
side_of = schadt.side_of


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="+", required=True)
    ap.add_argument("--dst", default="polished")
    args = ap.parse_args()

    snap = work_snapshot(*args.src)
    dst = snap / args.dst
    dst.mkdir(exist_ok=True)

    missing_dirs = [name for name in args.src if not (snap / name).is_dir()]
    if missing_dirs:
        raise SystemExit(f"no such directories in {snap.name}: {', '.join(missing_dirs)}")

    ns = sorted(
        {int(p.stem.split("-")[1]) for name in args.src for p in (snap / name).glob("squares-*.txt")}
    )
    if not ns:
        raise SystemExit(
            f"no squares-<n>.txt files in {', '.join(args.src)} - nothing to select from"
        )

    rows = []
    failures = 0
    print(f"{'n':>5} {'source':>22} {'side':>22} {'lead over runner-up':>21}")
    for n in ns:
        options = []
        for name in args.src:
            path = snap / name / f"squares-{n}.txt"
            if path.exists():
                options.append((side_of(path), name, path))
        options.sort(key=lambda t: t[0])
        best_side, best_name, best_path = options[0]

        # The selected file is checked, not "the one checked at generation time":
        # every downstream copy comes from exactly here.
        check = verify.check(packing_from_file(best_path), tol=mpf(0), expected_n=n)
        if check.max_overlap != 0:
            failures += 1
            print(f"{n:>5} FAIL: overlap {mp.nstr(check.max_overlap, 4)} in {best_name}")
            continue

        margin = options[1][0] - best_side if len(options) > 1 else mpf(0)
        if best_path.resolve() != (dst / best_path.name).resolve():
            shutil.copyfile(best_path, dst / best_path.name)
        rows.append(
            {
                "n": n,
                "source": best_name,
                "side": mp.nstr(best_side, 34),
                "margin_over_second": mp.nstr(margin, 6),
                "candidates": len(options),
            }
        )
        print(f"{n:>5} {best_name:>22} {mp.nstr(best_side, 17):>22} {mp.nstr(margin, 4):>17}")

    # The report is collected in memory and written in one piece. Opening the
    # file for writing BEFORE it was clear what to write has already cost one
    # finished `pick.csv`: a run with an empty source died on `rows[0]` while the
    # file was already truncated by mode "w" and not yet filled.
    if not rows:
        raise SystemExit("nothing to select: no candidate passed the check, the report is untouched")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    out = snap / "pick.csv"
    out.write_text(buffer.getvalue(), encoding="utf-8")

    by_source = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    print()
    print(f"selected: {len(rows)}, rejected: {failures}")
    for name, count in sorted(by_source.items()):
        print(f"  from {name}: {count}")
    print(f"provenance: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
