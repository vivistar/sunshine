"""Unit tests for Ranking / Rating summaries."""

import pytest

from app.models import RatingMode
from app.rating import summarize


def test_rate_summary_orders_by_mean_descending():
    items = [(1, "A"), (2, "B"), (3, "C")]
    responses = [
        {1: 5, 2: 3, 3: 1},
        {1: 4, 2: 3, 3: 2},
        {1: 5, 2: 2, 3: 1},
    ]
    s = summarize(items, responses, mode=RatingMode.rate, scale_points=5)

    assert s.num_responses == 3
    assert s.columns == ["1", "2", "3", "4", "5"]
    assert [i.item_id for i in s.items] == [1, 2, 3]  # A best, C worst

    a = s.items[0]
    assert abs(a.mean - 14 / 3) < 1e-9
    assert a.distribution == [0, 0, 0, 1, 2]   # one 4, two 5s
    assert abs(a.top_choice_pct - 2 / 3 * 100) < 1e-9  # top box (5) twice


def test_rank_summary_orders_by_mean_ascending():
    items = [(1, "A"), (2, "B"), (3, "C")]
    responses = [
        {1: 1, 2: 2, 3: 3},
        {1: 2, 2: 1, 3: 3},
        {1: 1, 2: 3, 3: 2},
    ]
    s = summarize(items, responses, mode=RatingMode.rank, scale_points=0)

    assert s.columns == ["1", "2", "3"]      # rank positions
    assert s.items[0].item_id == 1           # lowest mean rank wins
    a = s.items[0]
    assert abs(a.mean - 4 / 3) < 1e-9
    assert a.distribution == [2, 1, 0]       # ranked 1 twice, 2 once
    assert abs(a.top_choice_pct - 2 / 3 * 100) < 1e-9  # ranked #1 twice


def test_no_responses_raises():
    with pytest.raises(ValueError):
        summarize([(1, "A")], [], mode=RatingMode.rate, scale_points=5)
