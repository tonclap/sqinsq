"""Symbolic triage: which "not yet analytically optimized" entries are tractable.

The size of a symbolic system is set not by n but by the number of tilted
squares: axis-aligned ones fill the gaps in a grid and do not take part in
determining s. The script computes the structure of every flagged entry and
sorts them by increasing difficulty.

    sqinsq triage            # flagged entries only
    sqinsq triage --all      # the whole table (for calibration)
"""

from __future__ import annotations

import argparse
import csv

from sqinsq.paths import snapshot_arg

from sqinsq import contacts, svgpack, table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", help="snapshot directory (default: the newest)")
    ap.add_argument("--all", action="store_true", help="compute over the whole table")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot)
    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)
    if not args.all:
        entries = table.not_yet_optimized(entries)

    rows = []
    for entry in entries:
        svg_path = snap / "svg" / entry.svg
        if not svg_path.exists():
            continue
        packing = svgpack.load(svg_path)
        report = contacts.analyse(packing)
        rows.append(
            {
                "n": entry.n,
                "svg": entry.svg,
                "s": f"{float(packing.s):.12f}",
                "tilted": report.n_tilted,
                "angles": report.n_angles,
                "unknowns": report.unknowns,
                "equations": report.equations,
                "slack": report.equations - report.unknowns,
                "contacts_sq": len(report.contacts_square),
                "contacts_wall": len(report.contacts_wall),
                "angle_list": " ".join(f"{float(a):.6f}" for a in report.angles),
                "not_yet_optimized": int(entry.not_yet_optimized),
            }
        )

    rows.sort(key=lambda r: (r["tilted"], r["angles"]))
    out_csv = snap / ("triage_all.csv" if args.all else "triage_symbolic.csv")
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"entries: {len(rows)}   report: {out_csv}")
    print()
    print(f"{'n':>5} {'tilt':>5} {'angles':>6} {'unkn':>6} {'eqns':>6} {'slack':>6}  tilt angles")
    for row in rows:
        print(
            f"{row['n']:>5} {row['tilted']:>5} {row['angles']:>6} {row['unknowns']:>6} "
            f"{row['equations']:>6} {row['slack']:>6}  {row['angle_list'][:60]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
