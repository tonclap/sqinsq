"""Compare our format parsing with the foreign `check.py` - geometry, not verdicts.

`sqinsq crosscheck` asks the foreign code for a VALID/INVALID verdict. That
is not enough: the verdict would agree even if it and we read the FILE
differently, as long as both readings are admissible packings. Here the geometry
itself is compared: the corner coordinates that his loader (Decimal, 300 digits,
its own Taylor series for sin/cos) and ours (`sqinsq.schadt`, mpmath, 60 digits)
get out of one and the same file.

It also checks whether his repository has been updated: the content is compared
with the cached copy (`--refetch`).

A discrepancy is expected at the level of OUR precision (~1e-60), not his: the
bottleneck is mpmath at dps=60. Anything noticeably larger means the format is
read differently - a different sign convention for the angle, say, or a
different order of a square's corners.

    sqinsq agreement
    sqinsq agreement --refetch
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import urllib.request

from sqinsq.paths import external_file, work_snapshot

from mpmath import mp, mpf

from sqinsq import schadt

mp.dps = 60
CHECKER_NAME = "schadt_check.py"
CHECKER_URL = (
    "https://raw.githubusercontent.com/BalthasarStrauss/"
    "Squares-packing_S-29-_New-Record/main/check.py"
)
# Threshold of significance: our side is computed at 60 digits, his at 300.
# A discrepancy above this is no longer precision but a different reading.
TOLERANCE = mpf("1e-50")


def load_foreign():
    spec = importlib.util.spec_from_file_location("schadt_check", external_file(CHECKER_NAME))
    module = importlib.util.module_from_spec(spec)
    sys.modules["schadt_check"] = module
    spec.loader.exec_module(module)  # run() is under __main__, not executed on import
    return module


def _normalize(text: str) -> str:
    """Line endings to LF. `\\r\\r\\n` is not exotic but a real trace of downloading.

    Our copy sat for half a year with doubled CRs (a PowerShell redirect on the
    first save). Python executes such a file, so the defect never showed, but the
    comparison "our copy against the author's" reported a false "it changed".
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def refetch() -> str:
    request = urllib.request.Request(CHECKER_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        remote = response.read().decode("utf-8")
    local = external_file(CHECKER_NAME).read_text(encoding="utf-8")

    if _normalize(remote) == _normalize(local):
        if local != _normalize(local):
            print("foreign check.py: unchanged, but OUR copy is not stored in LF - rewrite it")
            return "mangled"
        print("foreign check.py: unchanged")
        return "same"

    print("foreign check.py: CHANGED upstream - the difference is not in line endings")
    print("  update the copy and re-run `sqinsq crosscheck`: earlier verdicts came from the old one")
    return "changed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true", help="compare with the author's repository")
    args = ap.parse_args()

    if args.refetch and refetch() in ("changed", "mangled"):
        return 1

    foreign = load_foreign()
    snap = work_snapshot("submission")
    files = sorted(
        (snap / "submission").glob("squares-*.txt"), key=lambda p: int(p.stem.split("-")[1])
    )
    if not files:
        raise SystemExit(f"no coordinate files in {snap / 'submission'}")

    worst_corner = mpf(0)
    worst_side = mpf(0)
    worst_where = ""
    problems = []
    for path in files:
        n = int(path.stem.split("-")[1])
        their_side, their_squares = foreign.ld(str(path))
        record = schadt.read(path)

        if len(their_squares) != record.n:
            problems.append(f"n={n}: he read {len(their_squares)} squares, we read {record.n}")
            continue

        side_gap = abs(mpf(str(their_side)) - record.side)
        if side_gap > worst_side:
            worst_side = side_gap

        # Our corners are in the centred frame, like his: to_packing shifts them
        # into [0, s], so we shift them back.
        ours = schadt.to_packing(record)
        half = record.side / 2
        for square, their in zip(ours.squares, their_squares):
            # His traversal order is different (dx in the outer loop, dy in the
            # inner one), so we compare sets of corners, not positions.
            theirs = sorted((mpf(str(x)), mpf(str(y))) for x, y in their["pts"])
            mine = sorted((x - half, y - half) for x, y in square.corners)
            for (tx, ty), (mx, my) in zip(theirs, mine):
                gap = max(abs(tx - mx), abs(ty - my))
                if gap > worst_corner:
                    worst_corner, worst_where = gap, f"n={n}"

    print(f"files compared: {len(files)}")
    print(f"worst corner discrepancy: {mp.nstr(worst_corner, 6)} ({worst_where})")
    print(f"worst side discrepancy: {mp.nstr(worst_side, 6)}")
    if worst_corner > TOLERANCE or worst_side > TOLERANCE:
        problems.append("discrepancy above the precision threshold - the format is read differently")
    if problems:
        for line in problems:
            print(f"  {line}")
        return 1
    print("format parsing agrees with the foreign one within our precision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
