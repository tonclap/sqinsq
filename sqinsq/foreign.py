"""Foreign verifiers: other people's code, run against our numbers.

Our verifier and our polisher were written by the same head, so an internal
check cannot reveal an error they share. The answer is to run every packing
through implementations written by other people - and there are now two of them,
by different authors, with different arithmetic:

* `schadt`    - `check.py` by Thomas Schadt: `Decimal` at 300 digits, epsilon
  `1e-100`, its own Taylor series for sine and cosine, its own separating-axis
  test. Reads `squares.txt` from its own working directory.
* `ellsworth` - `check_packing.py` by David Ellsworth, the author of the
  registry this project submits to. Also `Decimal`, but the epsilon is derived
  from the file itself (the digit count of `Final s:`, so ~1e-31 for our 34-digit
  files) unless given on the command line. Takes the file as an argument.

Both read the same text coordinate format, which is why adding the second one
cost a wrapper rather than a converter.

**A pass is only worth as much as the failure it could have produced.** A
verifier that answers "VALID" to everything - because the file did not parse the
way it expected, because a path was wrong, because a newer version changed its
output wording - passes 37 out of 37 exactly as convincingly as a working one.
So every run starts with `negative_control`: the same packing with one square
moved on top of another, which the verifier is required to reject. It it does
not, the run is aborted and no verdict from it is recorded.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqinsq.paths import external_file

VALID = "valid"
INVALID = "invalid"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Verifier:
    key: str
    local_name: str
    author: str
    # How it wants to be called. "cwd": reads `squares.txt` from its own
    # directory, so it gets a scratch copy of both. "argv": takes the path.
    style: str


VERIFIERS = {
    "schadt": Verifier("schadt", "schadt_check.py", "Thomas Schadt", "cwd"),
    "ellsworth": Verifier("ellsworth", "ellsworth_check.py", "David Ellsworth", "argv"),
}


def verdict_of(output: str) -> str:
    """Read the verdict out of a run.

    `"VALID" in output` is a trap that costs nothing to avoid and everything to
    hit: "INVALID" contains "VALID". Both verifiers print one or the other on a
    line of its own, and anything else means the run did not produce a verdict at
    all - which is not the same as a rejection and must not be recorded as one.
    """
    if "INVALID" in output:
        return INVALID
    if "VALID" in output:
        return VALID
    return UNREADABLE


def run(verifier: Verifier, coords: Path, timeout: int = 1800) -> tuple[str, str]:
    """Run one foreign verifier on one coordinate file. Returns (verdict, output)."""
    checker = external_file(verifier.local_name)
    coords = Path(coords)

    if verifier.style == "argv":
        proc = subprocess.run(
            [sys.executable, str(checker), str(coords)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return verdict_of(proc.stdout), proc.stdout

    # "cwd": the checker reads `squares.txt` from beside itself. Our packings are
    # not written into `data/external/` - that directory holds other people's
    # files, and our runs would start looking like edits of them.
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        shutil.copyfile(checker, workdir / checker.name)
        shutil.copyfile(coords, workdir / "squares.txt")
        proc = subprocess.run(
            [sys.executable, checker.name],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return verdict_of(proc.stdout), proc.stdout


def overlapping_copy(text: str) -> str:
    """The same packing with square 2 moved exactly on top of square 1.

    A mutation with no arithmetic in it: two unit squares at identical centres
    and identical angles overlap completely, at any precision, under any
    convention about the frame. Nudging a coordinate by a small amount would be
    a weaker control - whether it overlaps at all depends on the packing, and a
    negative control that might legitimately pass is not a control.
    """
    lines = text.splitlines()
    squares = [i for i, line in enumerate(lines) if line.startswith("Square ")]
    if len(squares) < 2:
        raise ValueError("a packing of fewer than two squares cannot be given an overlap")
    first, second = squares[0], squares[1]
    body = lines[first].split(":", 1)[1]
    lines[second] = lines[second].split(":", 1)[0] + ":" + body
    return "\n".join(lines) + "\n"


def negative_control(verifier: Verifier, coords: Path, timeout: int = 1800) -> tuple[bool, str]:
    """Check that this verifier is capable of saying no. Returns (ok, verdict)."""
    text = Path(coords).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / Path(coords).name
        broken.write_text(overlapping_copy(text), encoding="utf-8", newline="\n")
        verdict, _ = run(verifier, broken, timeout=timeout)
    return verdict == INVALID, verdict
