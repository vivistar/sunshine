"""Tests for the Van Westendorp Price Sensitivity Meter analysis."""

import math

import pytest

from app.van_westendorp import PriceResponse, analyze, validate_response


def _symmetric_responses():
    """Responses symmetric around a center price of 20 -> OPP and IPP == 20.

    Respondents differ by a symmetric price "shift" wide enough that the
    too-cheap and too-expensive distributions overlap, so the curve crossings
    are well defined (and, by symmetry, land on the center).
    """
    center = 20.0
    responses = []
    for shift in range(-10, 11):     # -10 .. +10, symmetric about 0
        responses.append(
            PriceResponse(
                too_cheap=center - 4 + shift,
                cheap=center - 2 + shift,
                expensive=center + 2 + shift,
                too_expensive=center + 4 + shift,
            )
        )
    return center, responses


def test_intersection_points_for_symmetric_data():
    center, responses = _symmetric_responses()
    res = analyze(responses, currency="$")

    assert res.num_responses == 21
    # By symmetry, the optimal and indifference prices sit at the center.
    assert math.isclose(res.opp, center, abs_tol=0.5)
    assert math.isclose(res.ipp, center, abs_tol=0.5)
    # Acceptable range brackets the center symmetrically.
    assert res.pmc < center < res.pme
    assert math.isclose(center - res.pmc, res.pme - center, abs_tol=0.5)


def test_acceptable_range_is_ordered_and_in_bounds():
    _, responses = _symmetric_responses()
    res = analyze(responses)
    lo, hi = res.acceptable_range
    assert lo is not None and hi is not None and lo < hi
    assert res.grid[0] <= lo <= hi <= res.grid[-1]


def test_curves_are_monotonic_in_the_right_direction():
    _, responses = _symmetric_responses()
    res = analyze(responses)
    # "too cheap" / "cheap" decline with price; "expensive" / "too expensive" rise.
    assert res.too_cheap[0] >= res.too_cheap[-1]
    assert res.cheap[0] >= res.cheap[-1]
    assert res.expensive[0] <= res.expensive[-1]
    assert res.too_expensive[0] <= res.too_expensive[-1]


def test_points_helper_lists_all_four():
    _, responses = _symmetric_responses()
    res = analyze(responses)
    names = {p.name for p in res.points}
    assert names == {"OPP", "IPP", "PMC", "PME"}


def test_validate_response():
    assert validate_response(5, 8, 12, 15) is None
    # Out of order
    assert validate_response(8, 5, 12, 15) is not None
    # Negative
    assert validate_response(-1, 8, 12, 15) is not None
    # Equal (not strictly increasing)
    assert validate_response(5, 5, 12, 15) is not None


def test_empty_raises():
    with pytest.raises(ValueError):
        analyze([])
