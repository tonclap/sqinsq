"""Take a snapshot of the registry and lay the table out as CSV.

    sqinsq snapshot            # download everything to data/snapshot-<today>
    sqinsq snapshot --no-svg   # index page and CSV only
    sqinsq snapshot --refetch  # re-download even what is already there
"""

from __future__ import annotations

import argparse

from sqinsq.paths import data_root

from sqinsq import fetch, table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-svg", action="store_true", help="do not download SVGs")
    ap.add_argument("--refetch", action="store_true", help="re-download existing files")
    ap.add_argument("--date", help="override the snapshot date (YYYY-MM-DD)")
    args = ap.parse_args()

    result = fetch.snapshot(
        data_root(),
        date=args.date,
        svg_names=[] if args.no_svg else None,
        refetch=args.refetch,
    )

    html = (result.directory / fetch.INDEX_PAGE).read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)
    table.write_csv(entries, result.directory / "table.csv")

    covered = sorted({n for e in entries for n in e.ns})
    pending = table.not_yet_optimized(entries)

    print(f"snapshot:          {result.directory}")
    print(f"index page:        {result.index_bytes} bytes")
    print(f"SVG:               downloaded {result.svg_downloaded}, already there {result.svg_skipped}")
    if result.svg_failed:
        print(f"SVG not downloaded: {len(result.svg_failed)}")
        for line in result.svg_failed:
            print(f"    {line}")
    print(f"entries in table:  {len(entries)}")
    print(f"n covered:         {len(covered)} (from {covered[0]} to {covered[-1]})")
    print(f"\"not yet analytically optimized\": {len(pending)}")
    print("    n = " + ", ".join(str(e.n) for e in pending))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
