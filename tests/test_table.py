"""Reading the registry page, and the one mistake this project kept making.

"Not yet analytically optimized" is the note that says an entry is still open
for improvement. It sits *inside* the caption, next to the attribution — and
every HTML-to-text conversion tried here dropped it, which is how two
independent readings of the page both reported 15 flagged entries when it
has 32. The count is not cosmetic: it decides which
entries are worth working on and what may be claimed about them.

Commented-out boxes matter for the same reason: the page keeps superseded
packings in HTML comments, and counting them is counting entries that no longer
exist.
"""

from __future__ import annotations

from sqinsq import table

BOX = """<div class="box">
<font size="+3">{label}<br></font>
<embed src="square-{n}.svg" width="200" height="200">
<div align="center"><font size="+1">$s = {s}$<br>{attribution}</font></div>
</div></div>"""


def page(*boxes: str) -> str:
    return "<html><body>" + "\n".join(boxes) + "</body></html>"


def test_flag_inside_the_caption_is_found():
    """The whole point: the note lives next to the attribution, not on its own line."""
    html = page(
        BOX.format(
            label="29",
            n=29,
            s="5.9338",
            attribution="Found by Thomas Schadt in December 2025. Not yet analytically optimized.",
        )
    )

    (entry,) = table.parse_table(html)

    assert entry.n == 29
    assert entry.not_yet_optimized is True


def test_entry_without_the_flag_is_not_flagged():
    """The negative control — without it the test above passes on a parser that says yes to everything."""
    html = page(
        BOX.format(
            label="4",
            n=4,
            s="2",
            attribution="Trivially optimal.",
        )
    )

    (entry,) = table.parse_table(html)

    assert entry.not_yet_optimized is False


def test_flagged_entries_are_selected_by_name():
    """`not_yet_optimized()` is what the pipeline actually calls to pick targets."""
    html = page(
        BOX.format(label="4", n=4, s="2", attribution="Trivially optimal."),
        BOX.format(
            label="29",
            n=29,
            s="5.9338",
            attribution="Found by Thomas Schadt. Not yet analytically optimized.",
        ),
    )

    flagged = table.not_yet_optimized(table.parse_table(html))

    assert [entry.n for entry in flagged] == [29]


def test_commented_out_boxes_are_ignored():
    """Superseded packings live in HTML comments — counting them counts ghosts."""
    live = BOX.format(label="4", n=4, s="2", attribution="Trivially optimal.")
    dead = BOX.format(
        label="29",
        n=29,
        s="5.9339",
        attribution="Superseded. Not yet analytically optimized.",
    )

    entries = table.parse_table(page(live, f"<!--\n{dead}\n-->"))

    assert [entry.n for entry in entries] == [4]


def test_multi_n_label_is_expanded():
    """One box can cover several n ("2, 3"); the largest is the one drawn."""
    html = page(BOX.format(label="2, 3", n=3, s="2", attribution="Trivially optimal."))

    (entry,) = table.parse_table(html)

    assert entry.ns == [2, 3]
    assert entry.n == 3
