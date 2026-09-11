"""Turn a set of packings into an audit record: one JSON per entry.

A claimed value is something you have to trust. The same claim as a file you can
re-verify in a minute is not. This command produces the second kind: for every
packing it writes what the value is, what verified it, what the packing looks
like structurally, and which bytes it came from.

    sqinsq results packings/squares-*.txt --out results/2026-08
    sqinsq results one.txt --out results --crosscheck   # add the foreign verdict

The structural part is the point, not decoration. An improvement in the 12th
significant digit is invisible in a picture, so "what actually changed here" has
to be answered in numbers: the contact graph does it - how many squares are
tilted, how many distinct angles they use, how many contacts hold the
configuration, and how that compares with the degrees of freedom. Those numbers
say what kind of packing it is, and they are cheap to compute and impossible to
argue with.

Deliberately **not** regenerated from a solver run. The files are read as they
are: polishing is not deterministic in outcome, so re-running it would write the
same names with different numbers, and a record that no longer matches the file
it describes is worse than no record at all.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from mpmath import mp, mpf

from sqinsq import contacts, schadt, svgpack, verify
from sqinsq.paths import external_file, lf_sha256

mp.dps = 60
DIGITS = 34


def load(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return svgpack.load(path)
    if suffix == ".txt":
        return schadt.to_packing(path)
    raise SystemExit(f"{path}: expected .svg or .txt, got {suffix!r}")


def entry_number(path: Path) -> int:
    """n out of `squares-238.txt` or `square-238.svg`."""
    stem = path.stem.split("-")
    for part in reversed(stem):
        if part.isdigit():
            return int(part)
    raise SystemExit(f"{path}: cannot tell which entry this is from the file name")


def foreign_verdict(coords: Path) -> str:
    """Run the third-party verifier on one coordinate file, in a scratch copy.

    It reads `squares.txt` from its own directory, so it gets a scratch one:
    writing our packings next to somebody else's code would make our runs look
    like edits of it.
    """
    checker = external_file("schadt_check.py")
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        shutil.copyfile(checker, workdir / checker.name)
        shutil.copyfile(coords, workdir / "squares.txt")
        proc = subprocess.run(
            [sys.executable, checker.name],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=600,
        )
    out = proc.stdout
    if "VALID" in out and "INVALID" not in out:
        return "valid"
    if "INVALID" in out:
        return "invalid"
    return "unreadable"


def record(path: Path, *, crosscheck: bool) -> dict:
    packing = load(path)
    result = verify.check(packing, tol=mpf(0))
    tight = verify.tight_side(packing)
    report = contacts.analyse(packing)

    return {
        "n": entry_number(path),
        "side": mp.nstr(packing.s, DIGITS),
        "verification": {
            # Zero tolerance: the verdict is about admissibility, not about a
            # number being small. Anything else would make "valid" meaningless.
            "tolerance": "0",
            "admissible": bool(result.ok),
            "max_overlap": mp.nstr(result.max_overlap, 6),
            "max_outside": mp.nstr(result.max_outside, 6),
            "problems": list(result.problems),
            "foreign_verifier": foreign_verdict(path) if crosscheck and path.suffix == ".txt" else None,
        },
        "tightness": {
            # How much room is left between the declared side and the smallest
            # axis-aligned square that actually contains the packing. Near zero
            # means the declared value is not merely valid but tight.
            "tight_side": mp.nstr(tight, DIGITS),
            "slack": mp.nstr(packing.s - tight, 6),
        },
        "structure": {
            # Contacts are counted at a strict tolerance, and that number is
            # much smaller than the one a reader expects: published coordinates
            # are numerical, so most real contacts sit at 1e-6 rather than at
            # 1e-30. Read `contacts_*` together with the tolerance, never alone -
            # a small count here means "the file is not exact", not "the packing
            # is loose". `sqinsq contact-tolerance` unrolls this properly.
            "contact_tolerance": mp.nstr(contacts.CONTACT_TOL, 3),
            "squares": packing.n,
            "tilted": report.n_tilted,
            "distinct_angles": report.n_angles,
            "contacts_square": len(report.contacts_square),
            "contacts_wall": len(report.contacts_wall),
            "unknowns": report.unknowns,
            "equations": report.equations,
            "tilt_angles_deg": [mp.nstr(a, 12) for a in report.angles[:32]],
        },
        "provenance": {
            "file": path.name,
            "sha256_lf": lf_sha256(path),
            "recorded": date.today().isoformat(),
            "generated_by": "sqinsq results",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="packings to record")
    parser.add_argument("--out", required=True, type=Path, help="directory for the records")
    parser.add_argument(
        "--crosscheck",
        action="store_true",
        help="also run the third-party verifier on each coordinate file (slow)",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    written = []
    rejected = 0

    for path in sorted(args.paths, key=entry_number):
        data = record(path, crosscheck=args.crosscheck)
        target = args.out / f"s{data['n']}.json"
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        written.append(data)
        mark = "ok  " if data["verification"]["admissible"] else "FAIL"
        if not data["verification"]["admissible"]:
            rejected += 1
        print(
            f"{mark} n={data['n']:<5} s={data['side'][:22]:<22} "
            f"tilted={data['structure']['tilted']:<5} "
            f"angles={data['structure']['distinct_angles']:<4} "
            f"slack={data['tightness']['slack']}"
        )

    print()
    print(f"wrote {len(written)} record(s) to {args.out}, rejected {rejected}")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
