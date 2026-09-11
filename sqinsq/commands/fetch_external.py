"""Fetch the third-party verifier this project cross-checks itself against.

Our verifier and our polisher were written by the same head. If they are wrong
in the same way, no internal check can reveal it — so every packing is also run
through an *independent* implementation: `check.py` by Thomas Schadt
(GitHub: BalthasarStrauss), which has its own Taylor series for sine and
cosine, its own separating-axis test and Decimal arithmetic at 300 digits.

That file is somebody else's work, so this repository does not carry a copy of
it. It is downloaded on demand from the upstream repository, pinned to an exact
commit, and checked against a recorded SHA-256 — reproducibility without
redistribution.

    sqinsq fetch-external            # download what is missing
    sqinsq fetch-external --check    # verify local copies, download nothing
    sqinsq fetch-external --force    # re-download even if present

Upstream is MIT-licensed (Copyright (c) 2025 Thomas Schadt), so vendoring would
also have been allowed; not vendoring is a deliberate choice, see
data/external/EXTERNAL.md.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request

from sqinsq.paths import data_root, lf_sha256


REPO = "BalthasarStrauss/Squares-packing_S-29-_New-Record"
# Pinned to a commit, not to a branch: `main` can move, and then the file that
# vouches for our numbers would silently stop being the file that vouched for
# them. Bump this deliberately, and re-run the cross-check when you do.
COMMIT = "71ea2ee9166fb7ffcefb6f9bea6124fab6ad95c3"
BASE = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}"

# SHA-256 of the LF-normalised content, not of the raw bytes. Upstream ships
# CRLF, this tree is LF (.gitattributes), and a hash over raw bytes would
# disagree with itself depending on which side of a clone you stand on.
FILES = {
    "schadt_check.py": (
        "check.py",
        "34ba952737fa03835778cfdc549258d7f8352338b8417d30a9bdc23475b19efa",
    ),
    "schadt_s29_squares.txt": (
        "squares.txt",
        "24d9a347bf6d9d3df295232323304be3d56a0c11929a5ad2fe302c959122b318",
    ),
}


def download(remote: str) -> bytes:
    url = f"{BASE}/{remote}"
    request = urllib.request.Request(url, headers={"User-Agent": "sqinsq"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only, never download")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    external = data_root() / "external"
    external.mkdir(parents=True, exist_ok=True)
    failures = 0

    for local_name, (remote_name, expected) in FILES.items():
        target = external / local_name

        if target.exists() and not args.force:
            actual = lf_sha256(target.read_bytes())
            if actual == expected:
                print(f"ok       {local_name} (sha256 matches the pin)")
            else:
                failures += 1
                print(f"MISMATCH {local_name}")
                print(f"         expected {expected}")
                print(f"         actual   {actual}")
                print("         local copy differs from the pinned upstream revision;")
                print("         re-run with --force to replace it, or bump COMMIT if upstream moved")
            continue

        if args.check:
            failures += 1
            print(f"MISSING  {local_name} — run without --check to download it")
            continue

        try:
            payload = download(remote_name)
        except (urllib.error.URLError, TimeoutError) as error:
            failures += 1
            print(f"FAILED   {local_name}: {error}")
            print(f"         fetch it by hand from https://github.com/{REPO}/blob/{COMMIT}/{remote_name}")
            print(f"         and save it as {target}")
            continue

        actual = lf_sha256(payload)
        if actual != expected:
            failures += 1
            print(f"MISMATCH {local_name}: upstream content is not what the pin expects")
            print(f"         expected {expected}")
            print(f"         actual   {actual}")
            print("         nothing was written — investigate before trusting any cross-check")
            continue

        # Written LF-normalised, matching what the pin is taken over and what
        # .gitattributes would produce anyway.
        target.write_bytes(payload.replace(b"\r\n", b"\n"))
        print(f"fetched  {local_name} ({len(payload)} bytes, sha256 matches the pin)")

    if failures:
        print(f"\n{failures} problem(s). The external cross-check cannot be trusted until they are fixed.")
        return 1

    print("\nAll external files present and pinned. Cross-check with:")
    print("    sqinsq crosscheck")
    return 0


if __name__ == "__main__":
    sys.exit(main())
