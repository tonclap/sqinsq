"""Parser for the registry table: one entry is one ``<div class="box">``.

Every entry carries: a label (one n or several), the SVG file name, the
expression for s in LaTeX, a decimal approximation, a polynomial root (when
published), the attribution text and the flags - above all the note
"Not yet analytically optimized".

Important: commented-out ``<!-- ... -->`` blocks on the page contain old entries.
They must be cut before parsing, or superseded packings enter the selection.
"""

from __future__ import annotations

import csv
import html as html_mod
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

BOX_RE = re.compile(r'<div class="box">.*?</div></div>', re.S)
LABEL_RE = re.compile(r'<font size="\+3">(.*?)<br>', re.S)
EMBED_RE = re.compile(r'<embed src="([^"]+\.svg)"')
HREF_RE = re.compile(r'<a href="([^"]+\.svg)"')
CENTER_RE = re.compile(r'<div align="center"><font size="\+1">(.*?)</font></div>', re.S)
NN_RE = re.compile(r"\\Nn\{([0-9.]+)\}")
FRAMES_RE = re.compile(r'<span class="frames">\$(.*?)\$</span>', re.S)
POLY_DEG_RE = re.compile(r"\{\}\^\{(\d+)\}")
TAG_RE = re.compile(r"<[^>]+>")

NOT_OPTIMIZED = "Not yet analytically optimized"


@dataclass
class Entry:
    """A single registry entry."""

    label: str  # the label as printed on the page: "29" or "2, 3"
    ns: list[int]  # every n this entry covers
    n: int  # the one that is drawn (the largest)
    svg: str  # file name of the picture
    s_latex: str  # the expression for s as it appears on the page
    s_decimal: str | None  # decimal approximation from the page (as a string!)
    poly: str | None  # polynomial equation for s, when published
    poly_degree: int | None
    not_yet_optimized: bool
    attribution: str
    flags: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        d = asdict(self)
        d["ns"] = " ".join(str(x) for x in self.ns)
        d["flags"] = "; ".join(self.flags)
        return d


def _text(fragment: str) -> str:
    """An HTML fragment to flat text (tags to spaces, entities expanded)."""
    txt = re.sub(r"<br\s*/?>", " ", fragment)
    txt = TAG_RE.sub(" ", txt)
    txt = html_mod.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def strip_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _parse_s(center: str) -> tuple[str, str | None, str | None, int | None]:
    """Pulls the expression for s, its decimal form and the polynomial out of a caption."""
    poly = None
    m = FRAMES_RE.search(center)
    if m:
        poly = re.sub(r"\s+", " ", m.group(1)).strip()

    # The main expression runs to the first </span> (if there is a toggle) or to the end of $...$
    head = center.split("</span>")[0] if "<span" in center else center
    m = re.search(r"\$s\s*=\s*(.*?)\$", head, re.S)
    s_latex = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    decimal = None
    m = NN_RE.search(s_latex)
    if m:
        decimal = m.group(1)
    elif re.fullmatch(r"[0-9]+(\.[0-9]+)?", s_latex):
        decimal = s_latex

    degree = None
    m = POLY_DEG_RE.search(s_latex)
    if m:
        degree = int(m.group(1))

    return s_latex, decimal, poly, degree


def parse_table(html: str) -> list[Entry]:
    """Parse a registry page into a list of entries."""
    entries: list[Entry] = []
    for box in BOX_RE.findall(strip_comments(html)):
        m = LABEL_RE.search(box)
        if not m:
            continue
        label = _text(m.group(1))
        ns = [int(x) for x in re.findall(r"\d+", label)]
        if not ns:
            continue

        m = EMBED_RE.search(box) or HREF_RE.search(box)
        svg = m.group(1) if m else ""

        m = CENTER_RE.search(box)
        center = m.group(1) if m else ""
        s_latex, decimal, poly, degree = _parse_s(center)

        attribution = _text(re.sub(r"\$.*?\$", "", center, flags=re.S))
        attribution = re.sub(r"\s+", " ", attribution).strip()

        flags = []
        if "rigid" in attribution.lower():
            flags.append("rigid")
        if "semi-primitive" in attribution.lower():
            flags.append("semi-primitive")
        if "Göbel" in attribution or "Gobel" in attribution:
            flags.append("göbel")

        entries.append(
            Entry(
                label=label,
                ns=ns,
                n=max(ns),
                svg=svg,
                s_latex=s_latex,
                s_decimal=decimal,
                poly=poly,
                poly_degree=degree,
                not_yet_optimized=NOT_OPTIMIZED in attribution,
                attribution=attribution,
                flags=flags,
            )
        )
    return entries


def write_csv(entries: list[Entry], path: Path) -> None:
    rows = [e.as_row() for e in entries]
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def not_yet_optimized(entries: list[Entry]) -> list[Entry]:
    return [e for e in entries if e.not_yet_optimized]
