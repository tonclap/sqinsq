"""The verifier is the only thing standing between a bug and a false claim.

Every number this project has ever published was cleared by
`sqinsq.verify`. If it says "valid" when squares overlap by 1e-30, the whole
pipeline becomes a machine for producing confident nonsense — which is why the
cases below are about the *boundary*, not about the happy path.

The container is the axis-aligned square [0, s] x [0, s]; unit squares may be
rotated arbitrarily. Touching is legal and load-bearing: dense packings are held
together by contacts, so a tolerance that rejects a zero gap would reject every
interesting configuration.
"""

from __future__ import annotations

import math

from mpmath import mpf

from sqinsq import verify
from sqinsq.svgemit import from_centers

SQRT2 = math.sqrt(2.0)


def test_single_square_fits_exactly():
    """One unit square in a container of side 1: valid, with nothing to spare."""
    packing = from_centers([(0.5, 0.5, 0)], 1)
    result = verify.check(packing)

    assert result.ok
    assert result.max_overlap == 0
    assert result.max_outside == 0
    assert result.n == 1


def test_two_squares_touching_is_valid():
    """A shared edge is a contact, not an overlap — the case dense packings live on."""
    packing = from_centers([(0.5, 0.5, 0), (1.5, 0.5, 0)], 2)
    result = verify.check(packing)

    assert result.ok
    assert result.max_overlap == 0


def test_coincident_squares_are_rejected():
    """Two squares in the same place: the loudest possible failure must be caught."""
    packing = from_centers([(0.5, 0.5, 0), (0.5, 0.5, 0)], 2)
    result = verify.check(packing)

    assert not result.ok
    assert result.max_overlap > 0
    assert result.worst_pair is not None


def _overlapping_by(epsilon):
    return from_centers(
        [(mpf("0.5"), mpf("0.5"), 0), (mpf("1.5") - mpf(epsilon), mpf("0.5"), 0)], 2
    )


def test_microscopic_overlap_is_measured_exactly():
    """An overlap of 1e-30 is far below floating-point noise and must still be seen.

    Measuring it is the point: a float-only verifier reports zero here, and a
    "record" that is really a rounding error gets published as a result.
    """
    result = verify.check(_overlapping_by("1e-30"))

    assert float(result.max_overlap) > 0
    assert abs(float(result.max_overlap) / 1e-30 - 1) < 1e-6
    assert result.worst_pair == (0, 1)


def test_result_path_runs_with_a_zero_overlap_budget():
    """The verdict depends on the tolerance, and the result path passes zero.

    `DEFAULT_TOL` is 1e-9, meant for reading registry packings whose published
    coordinates are rounded. Anything claimed as a result is checked with
    `tol=0` instead — every caller does that deliberately. This test pins the
    difference, so that dropping `tol=mpf(0)` from a caller during a cleanup
    fails here rather than silently in a published number.
    """
    packing = _overlapping_by("1e-30")

    assert verify.check(packing).ok is True
    assert verify.check(packing, tol=mpf(0)).ok is False


def test_square_outside_container_is_rejected():
    """Containment is checked independently of overlap: one square, still invalid."""
    packing = from_centers([(1.2, 0.5, 0)], 1)
    result = verify.check(packing)

    assert not result.ok
    assert result.max_outside > 0


def test_rotated_square_fills_its_diagonal_container():
    """A 45-degree square needs side sqrt(2). Rotation must not confuse containment."""
    packing = from_centers([(SQRT2 / 2, SQRT2 / 2, 45)], SQRT2)
    result = verify.check(packing)

    assert result.ok
    assert float(result.max_outside) < 1e-15


def test_expected_n_mismatch_is_reported():
    """The registry says how many squares an entry has; disagreeing with it is a problem."""
    packing = from_centers([(0.5, 0.5, 0)], 1)
    result = verify.check(packing, expected_n=2)

    assert not result.ok
    assert result.problems


def test_tight_side_measures_the_actual_extent():
    """Two touching squares span exactly 2, whatever side the packing claims."""
    packing = from_centers([(0.5, 0.5, 0), (1.5, 0.5, 0)], 10)
    assert abs(float(verify.tight_side(packing)) - 2.0) < 1e-25
