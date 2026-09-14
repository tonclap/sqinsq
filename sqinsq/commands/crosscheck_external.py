"""Run every polished packing through the FOREIGN verifiers.

Our verifier and our polisher were written by the same head: if they are wrong
in the same way, an internal check will not show it. So the result is also run
through implementations written by other people - `check.py` by Thomas Schadt
(BalthasarStrauss) and, since 2026-09-12, `check_packing.py` by David Ellsworth,
who keeps the registry this project submits to. Both are described in
`sqinsq/foreign.py`; both are downloaded from pinned commits by
`sqinsq fetch-external`.

ALL polished entries are checked, not a sample: "32 out of 32 improved" is
exactly the shape a systematic error takes, and picking convenient cases would
be the worst possible response to it.

    sqinsq crosscheck                          # every verifier available
    sqinsq crosscheck --verifier ellsworth     # just one
    sqinsq crosscheck --src polished --n 238

Each verifier is first shown a packing it must REJECT (one square moved on top
of another). A verifier that fails that control is not run on real files at all:
its agreement would carry no information.
"""

from __future__ import annotations

import argparse

from sqinsq import foreign
from sqinsq.paths import snapshot_arg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--src", default="polished", help="directory with coordinate files")
    ap.add_argument("--n", nargs="*", type=int, help="only these n")
    ap.add_argument(
        "--verifier",
        nargs="*",
        choices=sorted(foreign.VERIFIERS),
        default=sorted(foreign.VERIFIERS),
        help="which foreign verifiers to run (default: all of them)",
    )
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

    failures = 0
    for key in args.verifier:
        verifier = foreign.VERIFIERS[key]
        # The smallest file available, so that proving the verifier can fail
        # costs seconds rather than the run itself.
        control_file = min(polished, key=lambda p: int(p.stem.split("-")[1]))
        ok, verdict = foreign.negative_control(verifier, control_file)
        print(f"== {key} ({verifier.author})")
        if not ok:
            failures += 1
            print(
                f"   NEGATIVE CONTROL FAILED: on a packing with two squares placed on top of\n"
                f"   each other it answered {verdict!r} instead of 'invalid'. Not run further -\n"
                f"   agreement from a verifier that cannot disagree proves nothing."
            )
            continue
        print(f"   negative control ok (rejects a deliberate overlap in {control_file.name})")

        valid = invalid = unreadable = 0
        for path in polished:
            n = int(path.stem.split("-")[1])
            result, output = foreign.run(verifier, path)
            s_line = next((ln for ln in output.splitlines() if ln.startswith("S: ")), "S: ?")
            print(f"   n={n:>5}  {result.upper():<10} {s_line}")
            if result == foreign.VALID:
                valid += 1
            elif result == foreign.INVALID:
                invalid += 1
                for line in output.splitlines():
                    if line.startswith(("FAIL", "OVERLAP")):
                        print(f"           {line}")
            else:
                unreadable += 1
                print(f"           no verdict in the output; first line: {output.splitlines()[:1]}")

        print(f"   confirmed: {valid}, rejected: {invalid}, no verdict: {unreadable}")
        failures += invalid + unreadable

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
