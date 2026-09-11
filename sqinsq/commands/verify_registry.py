"""Positive control: the verifier must confirm the ENTIRE registry.

The rule: the verifier is run on every known packing of the registry and must
confirm them all. Rejecting one means a bug in the verifier, not in the registry.

Checked for every entry:
  1. the SVG parses without errors;
  2. the number of parsed squares matches the n in the caption;
  3. every square lies inside the container of side s;
  4. there are no pairwise overlaps (contacts are allowed);
  5. s from the viewBox matches the decimal approximation in the caption;
  6. the packing really is pressed against the walls (otherwise the declared s
     is not optimal even for its own configuration).

    sqinsq verify-registry                 # the whole snapshot
    sqinsq verify-registry --only 11 29 50 # a selection
"""

from __future__ import annotations

import argparse
import csv
import time

from sqinsq.paths import snapshot_arg

from mpmath import mpf

from sqinsq import svgpack, table, verify


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", help="snapshot directory (default: the newest)")
    ap.add_argument("--only", nargs="*", type=int, help="check only these n")
    ap.add_argument("--tol", default="1e-9", help="tolerance for overlap and escape")
    ap.add_argument("--verbose", action="store_true", help="print every entry")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot)
    tol = mpf(args.tol)
    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)
    if args.only:
        wanted = set(args.only)
        entries = [e for e in entries if wanted & set(e.ns)]

    rows = []
    failures = []
    started = time.time()
    for entry in entries:
        svg_path = snap / "svg" / entry.svg
        row = {
            "n": entry.n,
            "label": entry.label,
            "svg": entry.svg,
            "status": "",
            "parsed_n": "",
            "s_svg": "",
            "s_table": entry.s_decimal or "",
            "s_delta": "",
            "tight_side": "",
            "slack": "",
            "max_overlap": "",
            "max_outside": "",
            "not_yet_optimized": int(entry.not_yet_optimized),
            "warnings": "",
            "problem": "",
        }
        if not svg_path.exists():
            row["status"] = "MISSING"
            row["problem"] = "no such file in the snapshot"
            failures.append(row)
            rows.append(row)
            continue
        try:
            packing = svgpack.load(svg_path)
        except Exception as exc:  # noqa: BLE001 - any parse error is a rejection
            row["status"] = "PARSE"
            row["problem"] = f"{type(exc).__name__}: {exc}"
            failures.append(row)
            rows.append(row)
            continue

        result = verify.check(packing, tol=tol, expected_n=entry.n)
        tight = verify.tight_side(packing)
        row["warnings"] = "; ".join(packing.warnings)
        row["parsed_n"] = result.n
        row["s_svg"] = f"{packing.s}"
        row["tight_side"] = f"{tight}"
        row["slack"] = f"{packing.s - tight}"
        row["max_overlap"] = f"{result.max_overlap}"
        row["max_outside"] = f"{result.max_outside}"

        problems = list(result.problems)
        if entry.s_decimal:
            declared = mpf(entry.s_decimal)
            delta = abs(packing.s - declared)
            row["s_delta"] = f"{delta}"
            # The caption shows a truncated value (the \Nn macro), so the
            # comparison goes by the last digit shown, not by full precision.
            digits = len(entry.s_decimal.split(".")[1]) if "." in entry.s_decimal else 0
            if delta > mpf(10) ** (-digits) * 2:
                problems.append(f"s from the SVG differs from the caption by {delta}")
        if packing.s - tight > tol:
            problems.append(f"packing is not pressed to the walls: gap {packing.s - tight}")

        row["status"] = "OK" if not problems else "FAIL"
        row["problem"] = "; ".join(problems)
        if problems:
            failures.append(row)
        rows.append(row)
        if args.verbose:
            print(f"{row['status']:<6} n={entry.n:<5} {entry.svg}")

    out_csv = snap / "verify.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["status"] == "OK")
    noted = [r for r in rows if r["warnings"]]
    print()
    print(f"snapshot:  {snap.name}")
    print(f"entries:   {len(rows)}   confirmed: {ok}   rejected: {len(failures)}")
    print(f"time:      {time.time() - started:.1f} s   report: {out_csv}")
    if noted:
        print()
        print("Remarks about the registry's own files (not a rejection, but a defect):")
        for row in noted:
            print(f"  n={row['n']:<5} {row['svg']:<18} {row['warnings']}")
    if failures:
        print()
        print("NOT CONFIRMED (a bug in the verifier, not in the registry):")
        for row in failures[:40]:
            print(f"  n={row['n']:<5} {row['status']:<7} {row['problem'][:150]}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
