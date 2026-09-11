"""Where the data lives, and which snapshot a command should work on.

This used to be `scripts/_common.py`, whose job was to put the repository root
on `sys.path` so that loose scripts could import the library. Inside the package
that job disappears, and what remains is the harder question it never had to
answer: **where is `data/` when the package is installed and there is no
repository next to it.**

Resolution order, first hit wins:

1. ``SQINSQ_DATA`` in the environment - an explicit answer beats any guess;
2. ``./data`` under the current directory - the working answer for someone who
   cloned the repository, and for anyone who wants several data roots side by
   side;
3. ``<package>/../data`` - the source checkout, so that running from a
   subdirectory still finds the snapshots.

Nothing is created implicitly: a command that needs a snapshot and finds none
says so, and says which of these paths it looked at.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

# The source checkout this package was imported from. Meaningful when running
# from a clone (build tooling relies on it); inside an installed wheel it points
# at site-packages and is not used for anything.
REPO_ROOT = Path(__file__).resolve().parents[1]


def data_root() -> Path:
    """The directory holding snapshots, external files and derived results."""
    explicit = os.environ.get("SQINSQ_DATA")
    if explicit:
        return Path(explicit).resolve()
    local = Path.cwd() / "data"
    if local.is_dir():
        return local
    return REPO_ROOT / "data"


def describe_data_root() -> str:
    """Where the data root came from - printed when something is not found."""
    if os.environ.get("SQINSQ_DATA"):
        return f"{data_root()} (from SQINSQ_DATA)"
    if (Path.cwd() / "data").is_dir():
        return f"{data_root()} (./data under the current directory)"
    return f"{data_root()} (the source checkout)"


def lf_sha256(data: bytes | Path) -> str:
    """sha256 of the content with line endings normalised to LF.

    LF and not the raw bytes: a working copy on Windows can be CRLF, git stores
    LF, and a manifest over raw bytes would disagree with itself on the first
    clone. One implementation for the whole project - every manifest and every
    third-party pin must hash identically, otherwise checking one says nothing
    about the other.
    """
    raw = data if isinstance(data, bytes) else Path(data).read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def external_file(name: str) -> Path:
    """A third-party file from ``data/external``. Missing means a fresh clone.

    Third-party files are not stored in the repository (see
    ``data/external/EXTERNAL.md``), so on a fresh clone they are absent by
    definition. Without this check the caller dies with a raw
    ``FileNotFoundError`` from ``importlib``, which says nothing about the cause.
    """
    path = data_root() / "external" / name
    if not path.exists():
        raise SystemExit(
            f"third-party file {path} is missing: it is not stored in this repository.\n"
            f"data root: {describe_data_root()}\n"
            "Download it from the pinned commit: sqinsq fetch-external"
        )
    return path


def latest_snapshot() -> Path:
    """Newest registry snapshot. No snapshots is not an error, just wrong order."""
    candidates = sorted(data_root().glob("snapshot-*"))
    if not candidates:
        raise SystemExit(
            f"no snapshots in {describe_data_root()}: run `sqinsq snapshot` first"
        )
    return candidates[-1]


def snapshot_arg(value: str | None, *needed: str) -> Path:
    """The snapshot from ``--snapshot``, or one chosen automatically.

    ``needed`` lists the directories of derived data the caller requires. Given -
    the snapshot is searched by them (``work_snapshot``); omitted - the newest is
    taken. The difference matters: a command reading the registry wants the
    newest snapshot, a command reading derived results wants the one they are in.
    """
    if value:
        return Path(value)
    return work_snapshot(*needed) if needed else latest_snapshot()


def work_snapshot(*needed: str) -> Path:
    """The newest snapshot that actually HAS the required derived directories.

    A registry snapshot and a working snapshot are different things, and that is
    not obvious at once. Taking a snapshot creates a new directory holding
    nothing but SVGs, and "the newest" stops being the one with derived results
    in it that very second. Commands would then either fail on an empty list or,
    worse, report success having checked nothing.

    So the snapshot is chosen by the presence of data, not by date: "the one
    holding what I am checking". Nothing found is a refusal with a clear message,
    not an empty run.
    """
    candidates = sorted(data_root().glob("snapshot-*"), reverse=True)
    if not candidates:
        raise SystemExit(
            f"no snapshots in {describe_data_root()}: run `sqinsq snapshot` first"
        )
    for snap in candidates:
        if all((snap / name).is_dir() for name in needed):
            return snap
    raise SystemExit(
        f"no snapshot contains the directories {', '.join(needed)}; "
        f"newest snapshot: {candidates[0].name}"
    )
