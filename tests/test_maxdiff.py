"""Unit tests for the MaxDiff design generator and counting analysis."""

import pytest

from app.maxdiff import Observation, generate_design, suggested_num_sets, summarize


def test_design_is_balanced_and_distinct():
    n_items, k, num_sets = 7, 4, 12
    sets = generate_design(n_items, k, num_sets, seed=1)

    assert len(sets) == num_sets
    for s in sets:
        assert len(s) == k
        assert len(set(s)) == k          # no repeats within a set
        assert all(0 <= i < n_items for i in s)

    # Appearances are balanced to within 1 across items.
    counts = [0] * n_items
    for s in sets:
        for i in s:
            counts[i] += 1
    assert max(counts) - min(counts) <= 1


def test_design_validates_inputs():
    with pytest.raises(ValueError):
        generate_design(3, 5, 6)        # items_per_set > n_items
    with pytest.raises(ValueError):
        generate_design(5, 1, 6)        # items_per_set < 2
    with pytest.raises(ValueError):
        generate_design(5, 3, 0)        # no sets


def test_suggested_num_sets():
    assert suggested_num_sets(8, 4) == 6   # ceil(3*8/4)
    assert suggested_num_sets(0, 4) == 0


def test_summary_scores_and_ordering():
    items = [(1, "A"), (2, "B"), (3, "C")]
    # A always best, C always worst across three sets that show all three.
    obs = [
        Observation(shown=[1, 2, 3], best=1, worst=3),
        Observation(shown=[1, 2, 3], best=1, worst=3),
        Observation(shown=[1, 2, 3], best=1, worst=2),
    ]
    res = summarize(items, obs, num_responses=3)

    assert res.num_responses == 3
    assert res.items[0].item_id == 1            # A best
    assert res.items[-1].item_id == 3           # C worst
    a = res.items[0]
    assert a.appearances == 3 and a.best == 3 and a.worst == 0
    assert abs(a.score - 1.0) < 1e-9            # (3 - 0) / 3


def test_summary_requires_responses():
    with pytest.raises(ValueError):
        summarize([(1, "A")], [], num_responses=0)
