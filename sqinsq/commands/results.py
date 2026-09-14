"""Turn a set of packings into an audit record: one JSON per entry.

A claimed value is something you have to trust. The same claim as a file you can
re-verify in a minute is not. This command produces the second kind: for every
packing it writes what the value is, what verified it, what the packing looks
like structurally, and which bytes it came from.

    sqinsq results packings/squares-*.txt --out results/2026-08
    sqinsq results one.txt --out results --crosscheck             # every foreign verifier
    sqinsq results one.txt --out results --crosscheck ellsworth   # just one of them

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
import sys
from datetime import date
from pathlib import Path

from mpmath import mp, mpf

from sqinsq import contacts, foreign, schadt, svgpack, verify
from sqinsq.paths import lf_sha256

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


def previous(target: Path, sha256_lf: str) -> dict | None:
    """The record already on disk, if it describes the same bytes.

    A record is re-written whenever a new field appears in it - the verdict of a
    second foreign verifier, here - and the date it was first written is part of
    the claim, not bookkeeping. So it is carried over when the file behind the
    record is provably the same one, and only then.
    """
    if not target.exists():
        return None
    try:
        old = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return old if old.get("provenance", {}).get("sha256_lf") == sha256_lf else None


def record(path: Path, *, verifiers: list[str], target: Path) -> dict:
    packing = load(path)
    result = verify.check(packing, tol=mpf(0))
    tight = verify.tight_side(packing)
    report = contacts.analyse(packing)
    sha = lf_sha256(path)
    old = previous(target, sha)

    verdicts: dict[str, str] = {}
    if old:
        verdicts.update(old["verification"].get("foreign_verifiers", {}))
        # Records written before there was a second foreign verifier carry a
        # single `foreign_verifier`, and it always meant Schadt's. Migrated here
        # rather than dropped: it is a verdict that was actually obtained, and
        # re-running it costs hours.
        legacy = old["verification"].get("foreign_verifier")
        if legacy and "schadt" not in verdicts:
            verdicts["schadt"] = legacy
    if path.suffix == ".txt":
        for key in verifiers:
            verdicts[key], _ = foreign.run(foreign.VERIFIERS[key], path)

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
            # One entry per foreign implementation that has actually been run on
            # this file, by name. A verifier that was not run is absent rather
            # than null: "we did not ask" and "it had nothing to say" are
            # different statements, and only the first one is true here.
            "foreign_verifiers": verdicts,
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
            "sha256_lf": sha,
            "recorded": old["provenance"]["recorded"] if old else date.today().isoformat(),
            "updated": date.today().isoformat(),
            "generated_by": "sqinsq results",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="packings to record")
    parser.add_argument("--out", required=True, type=Path, help="directory for the records")
    parser.add_argument(
        "--crosscheck",
        nargs="*",
        choices=sorted(foreign.VERIFIERS),
        help="also run these foreign verifiers on each coordinate file (slow); "
        "no names means all of them",
    )
    args = parser.parse_args()

    verifiers = sorted(foreign.VERIFIERS) if args.crosscheck == [] else (args.crosscheck or [])

    args.out.mkdir(parents=True, exist_ok=True)
    written = []
    rejected = 0

    paths = sorted(args.paths, key=entry_number)

    # Before any verdict is recorded, each foreign verifier is shown a packing it
    # must reject. One that agrees with everything would fill the records with
    # "valid" and make them worse than empty - see sqinsq/foreign.py.
    control_file = next((p for p in paths if p.suffix == ".txt"), None)
    for key in verifiers:
        if control_file is None:
            raise SystemExit("--crosscheck needs at least one .txt coordinate file")
        ok, verdict = foreign.negative_control(foreign.VERIFIERS[key], control_file)
        if not ok:
            raise SystemExit(
                f"negative control failed for {key}: on a packing with two squares placed on\n"
                f"top of each other it answered {verdict!r} instead of 'invalid'. Nothing was\n"
                f"written - a verdict from a verifier that cannot disagree is not evidence."
            )
        print(f"negative control ok: {key} rejects a deliberate overlap in {control_file.name}")

    for path in paths:
        target = args.out / f"s{entry_number(path)}.json"
        data = record(path, verifiers=verifiers, target=target)
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
