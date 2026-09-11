"""A dated snapshot of the squares_in_squares registry page.

A snapshot is not a convenience but evidence of novelty: it records what s(n)
was and which flags were set on a particular date. Comparing an old snapshot
with a fresh one is how you check whether somebody else's wave of improvements
is passing over the chosen n right now.

Politeness to the server: the registry answers 429 to a request without a
User-Agent and to requests that come too fast. We pause between them, and back
off with growing delays on 429.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://kingbird.myphotos.cc/packing/"
INDEX_PAGE = "squares_in_squares.html"

# The registry answers 429 to the default python-urllib User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DELAY_SEC = 0.7
MAX_RETRIES = 5


class FetchError(RuntimeError):
    pass


def fetch_bytes(url: str, *, timeout: int = 60) -> bytes:
    """GET with a User-Agent and back-off on 429/5xx."""
    delay = 2.0
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise FetchError(f"{url}: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            last = exc
        if attempt < MAX_RETRIES - 1:
            time.sleep(delay)
            delay *= 2
    raise FetchError(f"{url}: could not download in {MAX_RETRIES} attempts: {last}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class SnapshotResult:
    directory: Path
    index_bytes: int
    svg_downloaded: int
    svg_skipped: int
    svg_failed: list[str]


def snapshot(
    out_root: Path,
    *,
    date: str | None = None,
    svg_names: list[str] | None = None,
    refetch: bool = False,
) -> SnapshotResult:
    """Download the index page and every SVG into ``out_root/snapshot-<date>``.

    ``svg_names``: if None, the list is taken from the page itself (parse_table).
    Files already downloaded are not fetched again unless ``refetch`` is set.
    """
    from . import table as table_mod

    fetched_at = datetime.now(timezone.utc)
    day = date or fetched_at.strftime("%Y-%m-%d")
    out_dir = out_root / f"snapshot-{day}"
    svg_dir = out_dir / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)

    index_path = out_dir / INDEX_PAGE
    if refetch or not index_path.exists():
        index_data = fetch_bytes(BASE_URL + INDEX_PAGE)
        index_path.write_bytes(index_data)
        time.sleep(DELAY_SEC)
    else:
        index_data = index_path.read_bytes()

    html = index_data.decode("utf-8", errors="replace")
    entries = table_mod.parse_table(html)
    names = svg_names if svg_names is not None else [e.svg for e in entries]

    downloaded = 0
    skipped = 0
    failed: list[str] = []
    files_meta: dict[str, dict] = {}

    for name in names:
        target = svg_dir / name
        if target.exists() and not refetch:
            skipped += 1
        else:
            try:
                data = fetch_bytes(BASE_URL + name)
            except FetchError as exc:
                failed.append(f"{name}: {exc}")
                continue
            target.write_bytes(data)
            downloaded += 1
            time.sleep(DELAY_SEC)
        files_meta[name] = {
            "bytes": target.stat().st_size,
            "sha256": sha256(target.read_bytes()),
        }

    meta = {
        "source": BASE_URL + INDEX_PAGE,
        "fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
        "snapshot_date": day,
        "index": {"bytes": len(index_data), "sha256": sha256(index_data)},
        "entries": len(entries),
        "svg": files_meta,
        "failed": failed,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return SnapshotResult(
        directory=out_dir,
        index_bytes=len(index_data),
        svg_downloaded=downloaded,
        svg_skipped=skipped,
        svg_failed=failed,
    )
