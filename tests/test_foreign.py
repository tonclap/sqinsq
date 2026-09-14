"""The machinery around other people's verifiers.

Nothing here runs a foreign verifier: those are downloaded on demand and absent
in a fresh clone, and a test that quietly skips itself when they are missing is
worse than no test (`_knowledge/testing_standard.md` §7.1). What is tested is the
part that decides what their output MEANS, and the mutation used to prove they
are capable of rejecting anything at all - both of which are ours, and both of
which fail silently if wrong.
"""

from __future__ import annotations

import pytest
from mpmath import mpf

from sqinsq import foreign, schadt, verify


def test_invalid_is_not_read_as_valid():
    """The substring trap: "INVALID" contains "VALID"."""
    assert foreign.verdict_of("Container: OK\nOverlaps: NONE\nVALID\n") == foreign.VALID
    assert foreign.verdict_of("OVERLAP: Squares 1, 2\nINVALID\n") == foreign.INVALID


def test_no_verdict_is_not_a_rejection():
    """A run that produced nothing is `unreadable`, never `invalid`.

    The difference is the whole point of recording verdicts: a crashed run and a
    rejected packing look alike in a summary and mean opposite things.
    """
    assert foreign.verdict_of("") == foreign.UNREADABLE
    assert foreign.verdict_of("Traceback (most recent call last):\n") == foreign.UNREADABLE


def test_mutation_really_produces_an_overlap(tmp_path):
    """The negative control has to be a packing that is genuinely inadmissible.

    Checked with our own verifier, at zero tolerance: if the mutation did not
    actually break the packing, every foreign verifier would pass the control by
    being correct, and the control would prove nothing.
    """
    good = tmp_path / "squares-3.txt"
    rows = [
        ("0.0", "0.0", "0"),
        ("2.0", "0.0", "0"),
        ("0.0", "2.0", "0"),
    ]
    schadt.write(tmp_path, 3, rows, mpf(5))

    assert verify.check(schadt.to_packing(good), tol=mpf(0)).ok

    broken = tmp_path / "broken.txt"
    broken.write_text(foreign.overlapping_copy(good.read_text(encoding="utf-8")), encoding="utf-8")

    result = verify.check(schadt.to_packing(broken), tol=mpf(0))
    assert not result.ok
    assert result.max_overlap > 0


def test_mutation_refuses_a_packing_it_cannot_break():
    """One square cannot be placed on top of another one that is not there."""
    with pytest.raises(ValueError):
        foreign.overlapping_copy("Final s: 1.0\n\nSquare 1: x=0.0, y=0.0, deg=0\n")
