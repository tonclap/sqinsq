"""Tighten a published packing: minimise the side, keep the topology.

The truth here is not convergence of the LP but the exact verifier: a step is
accepted only if the geometry stays admissible. An improvement counts from 1e-6
upwards and is re-checked in mpmath.

    sqinsq polish --n 179
    sqinsq polish --n 103 131 179 206 --iters 60
    sqinsq polish --all-flagged
"""

from __future__ import annotations

import argparse
import csv
import io
import time
from pathlib import Path

from sqinsq.paths import snapshot_arg

from mpmath import mp, mpf

from sqinsq import polish, refine, schadt, svgpack, table, verify

SIGNIFICANT = mpf("1e-6")  # threshold at which an improvement counts
# Zero budget for violations. The first version allowed 1e-12, reasoning that
# "this is nine orders below the significance threshold" - and produced 7
# packings out of 32 with an overlap of ~5e-13, which Schadt's verifier at
# epsilon 1e-100 rejected. Validity of a packing is binary: any overlap makes it
# inadmissible, no matter how much smaller than the gain it is.
VIOLATION_BUDGET = 0.0


def repair(state, *, rounds: int = 12):
    """Separate squares that overlap in exact arithmetic.

    Why a separate phase. Polishing runs in float64, and some results come out
    with an overlap of ~5e-13: our own verifier at tolerance 1e-11 lets them
    through, while Schadt's `check.py` at epsilon 1e-100 rejects them (which is
    what happened: 7 out of 32 on the first run). A microscopic overlap is not an
    admissible packing, and reporting one as a result is out of the question.

    The cure: the same LP step, but with a positive gap in the constraints. The
    LP finds the smallest side at which there is clearance everywhere; the price
    is a growth of s by about the gap, i.e. ~1e-11 against a gain of ~1e-4.
    """
    from mpmath import mpf

    from sqinsq import verify as verify_mod

    best = state.copy()
    overlap = verify_mod.check(packing_from_state_exact(best), tol=mpf(0)).max_overlap
    trust = 1e-9
    for _ in range(rounds):
        if overlap == 0:
            return best, True
        candidate, _, _ = polish.slp_step(
            best, trust=trust, contact_margin=1e-7, safety=trust * 1e-2
        )
        if candidate is not None:
            new_overlap = verify_mod.check(
                packing_from_state_exact(candidate), tol=mpf(0)
            ).max_overlap
            # A step is accepted only if the overlap really decreased: without
            # this check the repair introduces violations larger than the original.
            if new_overlap < overlap:
                best, overlap = candidate, new_overlap
                continue
        trust *= 0.5
        if trust < 1e-15:
            break
    return best, overlap == 0


def packing_from_state_exact(state):
    """A packing from a state - exactly the decimals that will go into the file.

    The difference matters: ``repr`` prints the shortest decimal that round-trips
    to the same double, but as a rational number it is not equal to the binary
    value. What is written out has to be checked, not what sits in memory, or the
    check and the file drift apart by ~1e-17.
    """
    from mpmath import cos, mpf, pi, sin

    import numpy as np

    from sqinsq.svgpack import Packing, UnitSquare

    half = mpf(1) / 2
    squares = []
    for i in range(state.n):
        cx = mpf(repr(float(state.cx[i])))
        cy = mpf(repr(float(state.cy[i])))
        deg = mpf(repr(float(np.degrees(state.th[i]))))
        ang = deg * pi / 180
        ca, sa = cos(ang), sin(ang)
        corners = [
            (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)
            for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half))
        ]
        squares.append(UnitSquare(corners=corners))
    return Packing(
        s=mpf(repr(float(state.s))),
        squares=squares,
        source="state",
        entities={},
        warnings=[],
    )


def save_schadt_format(state, n: int, snap: Path, out_dir: Path | None = None):
    """Save a configuration in the text format of Schadt's repository.

    The same format is read by his own ``check.py`` - a check independent of us,
    at 300 digits. His container is centred at the origin, so the coordinates are
    shifted by -s/2.

    The published side is not "polished plus a margin by eye" but computed
    exactly: the smallest side of an axis-aligned square containing exactly the
    decimal coordinates that go into the file, plus one unit of the last digit.
    """
    import numpy as np
    from mpmath import mpf

    # Schadt's checker keeps the container as [-S/2, S/2]^2, so we compute
    # exactly what he computes: the largest absolute corner coordinate among
    # those very decimals that go into the file.
    shift = state.s / 2.0
    shifted = state.copy()
    shifted.cx = state.cx - shift
    shifted.cy = state.cy - shift
    packing = packing_from_state_exact(shifted)
    half = max(
        max(abs(x), abs(y)) for square in packing.squares for x, y in square.corners
    )
    side = 2 * half * (1 + mpf(10) ** -30) + mpf(10) ** -30

    rows = [
        (repr(state.cx[i] - shift), repr(state.cy[i] - shift), repr(float(np.degrees(state.th[i]))))
        for i in range(state.n)
    ]
    path = schadt.write(out_dir or snap / "polished", n, rows, side, digits=34)
    return path, side


def packing_from_file(path: Path):
    """A packing from the written file - the exported decimals are what gets checked."""
    return schadt.to_packing(path)


def save_schadt_format_mp(state, n: int, out_dir: Path, digits: int = 34):
    """The same, but from the mpmath state after the refinement stage.

    There is one difference from the float version, and it is essential: the side
    is computed from the very decimal strings that go into the file, not from the
    values in memory. Coordinates are printed with `digits` digits, read back,
    and the extent is taken from them; one unit of the last digit is added on top
    so that rounding on printing cannot push a corner outside.
    """
    from mpmath import mp, mpf, pi

    half_side = state.s / 2
    rows = [
        (
            mp.nstr(state.cx[i] - half_side, digits),
            mp.nstr(state.cy[i] - half_side, digits),
            mp.nstr(state.th[i] * 180 / pi, digits),
        )
        for i in range(state.n)
    ]
    pad = mpf(10) ** (-digits + 2)
    side = 2 * schadt.reach_of(rows) * (1 + pad) + pad
    path = schadt.write(out_dir, n, rows, side, digits=digits)
    return path, side


def run_one(
    entry,
    snap: Path,
    *,
    iters: int,
    trust0: float,
    verbose: bool,
    refine_iters: int = 0,
    out_dir: Path | None = None,
) -> dict:
    packing = svgpack.load(snap / "svg" / entry.svg)
    state = polish.state_from_packing(packing)
    s_start = state.s
    start_violation = polish.worst_violation(state)

    trust = trust0
    accepted = 0
    rejected = 0
    best = state.copy()
    t0 = time.time()

    for _ in range(iters):
        safety = 4.0 * trust * trust
        candidate, active, _ = polish.slp_step(
            best, trust=trust, contact_margin=1e-4, safety=safety
        )
        if candidate is None:
            trust *= 0.5
            rejected += 1
            if trust < 1e-14:
                break
            continue
        violation = polish.worst_violation(candidate)
        gain = best.s - candidate.s
        if violation <= VIOLATION_BUDGET and gain > 0:
            best = candidate
            accepted += 1
            if gain < trust * 1e-3:
                trust *= 0.5  # the step stopped paying off, shrink the region
            if trust < 1e-14:
                break
        else:
            trust *= 0.5
            rejected += 1
            if trust < 1e-14:
                break
        if verbose:
            print(
                f"    n={entry.n} trust={trust:.2e} s={best.s:.15f} "
                f"active={active} viol={violation:.2e}"
            )

    # -- Repair: separate pairs that overlap in exact arithmetic --------------
    best, repaired = repair(best)

    refine_steps = ""
    if refine_iters:
        # -- Arbitrary-precision refinement stage -----------------------------
        # float64 stalls at 1e-14 not because the optimum was found but because
        # a step stops being distinguishable from noise. Beyond that, mpmath.
        mp_state, log = refine.refine(
            refine.state_from_float(best), iters=refine_iters, verbose=verbose
        )
        _, s_export = save_schadt_format_mp(mp_state, entry.n, out_dir)
        refine_steps = str(len(log))
        # It is not memory that is checked but the file: we re-read exactly the
        # decimals that were exported.
        result = verify.check(
            packing_from_file(out_dir / f"squares-{entry.n}.txt"),
            tol=mpf(0),
            expected_n=entry.n,
        )
    else:
        _, s_export = save_schadt_format(best, entry.n, snap, out_dir=out_dir)
        result = verify.check(
            packing_from_state_exact(best), tol=mpf(0), expected_n=entry.n
        )
    gain = s_start - float(s_export)

    return {
        "n": entry.n,
        "svg": entry.svg,
        "s_registry": f"{s_start:.15f}",
        "s_polished": f"{float(s_export):.15f}",
        "gain": f"{gain:.3e}",
        "significant": int(mpf(gain) > SIGNIFICANT),
        # Containment is guaranteed by the published side itself (it is computed
        # from the same decimals), so the verdict here is about overlap.
        "verified": int(result.max_overlap == 0),
        "repaired": int(repaired),
        "max_overlap": mp.nstr(result.max_overlap, 4),
        "s_export": mp.nstr(s_export, 25),
        "start_violation": f"{start_violation:.3e}",
        "accepted": accepted,
        "rejected": rejected,
        "refine_steps": refine_steps,
        "seconds": f"{time.time() - t0:.1f}",
        "problem": "; ".join(result.problems),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--n", nargs="*", type=int, help="which n to polish")
    ap.add_argument("--all-flagged", action="store_true", help="all 32 flagged entries")
    ap.add_argument(
        "--all-unflagged",
        action="store_true",
        help="every entry without the flag - a control by scale",
    )
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--trust", type=float, default=1e-3)
    ap.add_argument(
        "--refine",
        nargs="?",
        type=int,
        const=30,
        default=0,
        help="mpmath refinement stage after float64, number of iterations",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    snap = snapshot_arg(args.snapshot)
    html = (snap / "squares_in_squares.html").read_text(encoding="utf-8", errors="replace")
    entries = table.parse_table(html)
    if args.all_flagged:
        entries = table.not_yet_optimized(entries)
    elif args.all_unflagged:
        # Entries WITHOUT the flag. This is not a search for improvements but a
        # control by scale: most of them have an exact value published, and a
        # gain there would more likely mean an error on our side. Any plus must
        # pass the foreign verifier before it counts as a find.
        flagged = {e.n for e in table.not_yet_optimized(entries)}
        entries = [e for e in entries if e.n not in flagged]
    elif args.n:
        wanted = set(args.n)
        entries = [e for e in entries if e.n in wanted]
    else:
        raise SystemExit("pass --n, --all-flagged or --all-unflagged")

    # Results are written to `polished/` only on a full run: a one-off run over
    # an arbitrary n must not slip extra packings into that directory -
    # `sqinsq make-svg --all` would collect them as if they belonged there.
    if args.all_flagged:
        out_dir = snap / "polished"
    elif args.all_unflagged:
        out_dir = snap / "polished-unflagged"
    else:
        out_dir = snap / "polished-adhoc"

    rows = []
    print(f"{'n':>5} {'registry s':>20} {'polished s':>20} {'gain':>11} {'check':>7}")
    for entry in entries:
        row = run_one(
            entry,
            snap,
            iters=args.iters,
            trust0=args.trust,
            verbose=args.verbose,
            refine_iters=args.refine,
            out_dir=out_dir,
        )
        rows.append(row)
        mark = "OK" if row["verified"] else "FAIL"
        star = " *" if row["significant"] else ""
        print(
            f"{row['n']:>5} {row['s_registry']:>20} {row['s_polished']:>20} "
            f"{row['gain']:>11} {mark:>7}{star}"
        )
        if row["problem"]:
            print(f"      {row['problem'][:140]}")

    # The report name depends on what was run: a control run over solved entries
    # once overwrote the report on all 32, and restoring it took another
    # half-hour run.
    if args.all_flagged:
        out = snap / "polish.csv"
    elif args.all_unflagged:
        out = snap / "polish-unflagged.csv"
    else:
        out = snap / ("polish-" + "-".join(str(e.n) for e in entries[:6]) + ".csv")
    # Collect first, write second: mode "w" truncates the file on opening, and a
    # failure on empty `rows` would destroy the previous report (this is exactly
    # how `pick.csv` was lost).
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    out.write_text(buffer.getvalue(), encoding="utf-8")
    print()
    print(f"report: {out}")
    hits = [r for r in rows if r["significant"] and r["verified"]]
    print(f"improvements above 1e-6 confirmed by exact geometry: {len(hits)}")
    for row in hits:
        print(f"  n={row['n']}  {row['s_registry']} -> {row['s_polished']}  ({row['gain']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
