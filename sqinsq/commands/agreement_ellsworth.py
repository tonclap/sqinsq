"""Compare our SVG reading with the author's own parser - geometry, not verdicts.

`sqinsq agreement` compares our reading of Thomas Schadt's COORDINATE format
with his loader. This is the other half: the author of the site, David
Ellsworth, published `parse_svg_packing.py`, which turns the SVGs of his site
into that coordinate format. Both tools read the same file, so a discrepancy is
a difference of reading, not of arithmetic.

It exists because he doubted, in writing, that we can read the whole set:
"my guess is that it's likely that it can't handle all of the SVG files on my
website". The table entries are not the whole set - the comparison page
(`squares_in_squares__compared.html`) carries the older and alternative
packings, with names our snapshots never touched (`square-19b0.svg`,
`square-55_r8_start_G&R_end.svg`, `square-17_sym.svg`).

His frame is not ours: the container is centred on the origin and the y axis
points up, so his (x, y) is our (x + s/2, s/2 - y). Comparing without that flip
looks like a one-unit disagreement on a single square, and normalising by the
bounding box of the content does not repair it - in a packing that does not
touch every wall, the content box is not the container.

    sqinsq agreement-ellsworth --tools ../packing_squares_in_squares__tools
    sqinsq agreement-ellsworth --tools DIR --limit 20      # a sample, not the set
"""

from __future__ import annotations

import argparse
import html
import math
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from sqinsq import svgpack
from sqinsq.fetch import fetch_bytes
from sqinsq.paths import data_root

COMPARED_URL = "https://kingbird.myphotos.cc/packing/squares_in_squares__compared.html"
BASE_URL = "https://kingbird.myphotos.cc/packing/"
PARSER_NAME = "parse_svg_packing.py"
# Below our own float conversion, which is what the comparison is done in.
TOLERANCE = 1e-9


def cache_dir() -> Path:
    return data_root() / "external" / "site-svgs"


def download_set(pause: float = 0.5) -> list[Path]:
    """Every SVG the comparison page references, cached on disk.

    One reference, `square-55_r6_start.svg`, is a broken link on the site: it
    answers 404. That is his defect, not a parsing failure, so it is reported
    and skipped rather than counted against either tool.
    """
    out = cache_dir()
    out.mkdir(parents=True, exist_ok=True)
    page = fetch_bytes(COMPARED_URL).decode("utf-8", "replace")
    refs = sorted(
        {
            html.unescape(ref)
            for ref in re.findall(r'(?:href|src|data)\s*=\s*["\']([^"\']+\.svg)["\']', page, re.I)
        }
    )
    missing = []
    for ref in refs:
        name = ref.rsplit("/", 1)[-1]
        if (out / name).exists():
            continue
        try:
            (out / name).write_bytes(fetch_bytes(BASE_URL + ref))
        except Exception as exc:  # noqa: BLE001 - the reason is printed, not handled
            missing.append((ref, str(exc)[:60]))
        time.sleep(pause)
    for ref, why in missing:
        print(f"  not downloadable: {ref} ({why})")
    return sorted(out.glob("*.svg"))


def read_his(text: str):
    """His output: a declared side, then `Square k: x=..., y=..., deg=...`."""
    side = re.search(r"Final s:\s*([-\d.eE]+)", text)
    if not side:
        return None, []
    squares = re.findall(r"x=([-\d.eE]+),\s*y=([-\d.eE]+),\s*deg=([-\d.eE]+)", text)
    return float(side.group(1)), [(float(x), float(y), float(d)) for x, y, d in squares]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", required=True, help="checkout of packing_squares_in_squares__tools")
    ap.add_argument("--limit", type=int, help="cross-check a random sample of this size")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    parser = Path(args.tools).expanduser().resolve() / PARSER_NAME
    if not parser.exists():
        raise SystemExit(f"{PARSER_NAME} not found in {args.tools}")

    files = download_set()
    if args.limit and args.limit < len(files):
        files = sorted(random.Random(args.seed).sample(files, args.limit))
    print(f"SVGs to compare: {len(files)} (cache: {cache_dir()})")

    scratch = data_root() / "external" / "site-svgs-parsed"
    scratch.mkdir(parents=True, exist_ok=True)

    same = 0
    problems: list[str] = []
    for path in files:
        dump = scratch / (path.stem + ".txt")
        if not dump.exists():
            run = subprocess.run(
                [sys.executable, str(parser), str(path), "0", str(dump)],
                capture_output=True,
                text=True,
                timeout=900,
            )
            if run.returncode != 0 or not dump.exists():
                problems.append(f"{path.name}: HIS parser failed: {(run.stderr or run.stdout)[-70:].strip()}")
                continue

        his_side, his_squares = read_his(dump.read_text())
        if his_side is None:
            problems.append(f"{path.name}: his output has no side")
            continue
        try:
            ours = svgpack.load(path)
        except Exception as exc:  # noqa: BLE001 - the failure itself is the finding
            problems.append(f"{path.name}: OUR parser failed: {exc}")
            continue

        if len(his_squares) != len(ours.squares):
            problems.append(f"{path.name}: he read {len(his_squares)} squares, we read {ours.n}")
            continue
        if abs(his_side - float(ours.s)) > TOLERANCE:
            problems.append(f"{path.name}: side {his_side} against our {float(ours.s)}")
            continue

        half = his_side / 2
        theirs = sorted((x + half, half - y) for x, y, _ in his_squares)
        mine = sorted((float(q.center[0]), float(q.center[1])) for q in ours.squares)
        gap = max((math.hypot(a - c, b - d) for (a, b), (c, d) in zip(theirs, mine)), default=0.0)
        if gap > TOLERANCE:
            problems.append(f"{path.name}: centres differ by {gap:.3g}")
        else:
            same += 1

    print(f"identical geometry: {same} of {len(files)}")
    if problems:
        print(f"disagreements: {len(problems)}")
        for line in problems[:40]:
            print(f"  {line}")
        return 1
    print("both parsers read every file the same way")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
