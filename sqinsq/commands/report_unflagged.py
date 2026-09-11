"""Summary over entries WITHOUT the flag: is there slack where the registry is silent.

The report is assembled from the files themselves, not from a run log: a pass
over 142 entries takes more than an hour and was once interrupted on the 141st,
taking with it the CSV that is written at the very end. The files were already
on disk by then - so the summary is recoverable, and an hour need not be spent again.

What is computed. For every entry: the published side from the table against the
side the polisher reaches, plus an exact check of the file that was written. Only
a gain above 1e-6 with zero overlap counts as an improvement.


How to read the result. This is a control, not a search: most of these entries
have an exact value published, and a gain there would more likely mean an error
on our side than a find. Any plus must pass the foreign verifier before it counts
as a result.

    sqinsq report-unflagged
"""

from __future__ import annotations

import argparse
import csv
import io

from sqinsq.paths import work_snapshot

from mpmath import mp, mpf

from sqinsq import schadt, table, verify

mp.dps = 60
SIGNIFICANT = mpf("1e-6")


def main() -> int:
    # Takes no options, but still parses: the snapshot is resolved below, and
    # without this `--help` would die on a missing snapshot instead of
    # explaining what the command does.
    argparse.ArgumentParser(description=__doc__).parse_args()

    snap = work_snapshot("polished-unflagged")
    src = snap / "polished-unflagged"
    if not src.is_dir():
        raise SystemExit(f"no directory {src}: run `sqinsq polish --all-unflagged` first")

    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)
    flagged = {e.n for e in table.not_yet_optimized(entries)}
    published = {
        e.n: mpf(e.s_decimal)
        for e in entries
        if e.n not in flagged and e.s_decimal is not None
    }

    rows = []
    hits = []
    invalid = []
    for path in sorted(src.glob("squares-*.txt"), key=lambda p: int(p.stem.split("-")[1])):
        n = int(path.stem.split("-")[1])
        if n not in published:
            continue
        side = schadt.side_of(path)
        gain = published[n] - side
        result = verify.check(schadt.to_packing(path), tol=mpf(0), expected_n=n)
        ok = result.max_overlap == 0
        if not ok:
            invalid.append(n)
        if gain > SIGNIFICANT and ok:
            hits.append((n, published[n], side, gain))
        rows.append(
            {
                "n": n,
                "s_published": mp.nstr(published[n], 17),
                "s_polished": mp.nstr(side, 34),
                "gain": mp.nstr(gain, 4),
                "verified": int(ok),
            }
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    out = snap / "unflagged-report.csv"
    out.write_text(buffer.getvalue(), encoding="utf-8")

    gains = sorted(mpf(r["gain"]) for r in rows)
    print(f"unflagged entries computed: {len(rows)} of {len(published)}")
    print(f"gain: from {mp.nstr(gains[0], 4)} to {mp.nstr(gains[-1], 4)}")
    print(f"above the threshold {mp.nstr(SIGNIFICANT, 2)} with zero overlap: {len(hits)}")
    for n, pub, side, gain in hits:
        print(f"  n={n}: {mp.nstr(pub, 17)} -> {mp.nstr(side, 20)} (gain {mp.nstr(gain, 4)})")
    if invalid:
        print(f"files with an overlap (not a result but a defect of the run): {invalid}")
    print(f"table: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
