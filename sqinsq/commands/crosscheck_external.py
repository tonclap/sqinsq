"""Run every polished packing through the FOREIGN verifier.

Our verifier and our polisher were written by the same head: if they are wrong
in the same way, an internal check will not show it. So the result is also run
through `check.py` from the repository of Thomas Schadt (BalthasarStrauss) - an
independent implementation with its own Taylor series for sine and cosine, its
own separating-axis test, Decimal arithmetic at 300 digits, epsilon 1e-100.

ALL polished entries are checked, not a sample: "32 out of 32 improved" is
exactly the shape a systematic error takes, and picking convenient cases would
be the worst possible response to it.

    sqinsq crosscheck
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from sqinsq.paths import external_file, snapshot_arg

CHECKER_NAME = "schadt_check.py"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--src", default="polished", help="directory with coordinate files")
    ap.add_argument("--n", nargs="*", type=int, help="only these n")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot, args.src)
    polished = sorted(
        (snap / args.src).glob("squares-*.txt"),
        key=lambda p: int(p.stem.split("-")[1]),
    )
    if args.n:
        wanted = set(args.n)
        polished = [p for p in polished if int(p.stem.split("-")[1]) in wanted]
    if not polished:
        raise SystemExit("no polished packings: run sqinsq polish first")
    checker = external_file(CHECKER_NAME)

    # The foreign verifier reads `squares.txt` from its own directory, but our
    # packings must not be written into `data/external/`: that directory holds
    # other people's data, and our runs would start looking like edits of it.
    workdir = snap / "crosscheck-run"
    workdir.mkdir(exist_ok=True)
    shutil.copyfile(checker, workdir / CHECKER_NAME)
    valid = invalid = 0
    for path in polished:
        n = int(path.stem.split("-")[1])
        shutil.copyfile(path, workdir / "squares.txt")
        proc = subprocess.run(
            [sys.executable, CHECKER_NAME],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        out = proc.stdout
        verdict = "VALID" if "VALID" in out and "INVALID" not in out else "INVALID"
        s_line = next((ln for ln in out.splitlines() if ln.startswith("S: ")), "S: ?")
        print(f"n={n:>5}  {verdict:<8} {s_line}")
        if verdict == "VALID":
            valid += 1
        else:
            invalid += 1
            for line in out.splitlines():
                if line.startswith("FAIL"):
                    print(f"        {line}")

    print()
    print(f"confirmed by the foreign verifier: {valid}, rejected: {invalid}")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
