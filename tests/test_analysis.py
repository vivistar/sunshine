"""Validate the MNL estimator by recovering known part-worth utilities."""

import math
import random

import numpy as np

from app.analysis import Observation, analyze, predict_shares
from app.design import ConceptSpec, generate_design

ATTRS = [
    ("Price", ["$10", "$20", "$30"]),
    ("Brand", ["Acme", "Globex"]),
    ("Size", ["S", "M", "L"]),
]

# True part-worths (reference level = first level of each attribute = 0).
TRUE = {
    ("Price", "$10"): 0.0, ("Price", "$20"): -0.8, ("Price", "$30"): -1.6,
    ("Brand", "Acme"): 0.0, ("Brand", "Globex"): 0.5,
    ("Size", "S"): 0.0, ("Size", "M"): 0.3, ("Size", "L"): 0.7,
}
TRUE_NONE = -1.5


def _utility(concept: ConceptSpec) -> float:
    if concept.is_none:
        return TRUE_NONE
    return sum(TRUE[(a, lvl)] for a, lvl in concept.levels.items())


def _simulate(num_respondents=400, num_tasks=10, seed=2024):
    rng = random.Random(seed)
    observations = []
    for r in range(num_respondents):
        design = generate_design(
            ATTRS, num_tasks=num_tasks, alternatives_per_task=3,
            include_none=True, seed=seed + r,
        )
        for task in design:
            utils = np.array([_utility(c) for c in task.concepts])
            utils -= utils.max()
            probs = np.exp(utils) / np.exp(utils).sum()
            chosen = rng.choices(range(len(task.concepts)), weights=probs)[0]
            observations.append(
                Observation(alternatives=task.concepts, chosen_index=chosen)
            )
    return observations


def test_recovers_true_preferences():
    obs = _simulate()
    results = analyze(ATTRS, obs, include_none=True)

    assert results.converged
    assert results.num_observations == 4000
    assert 0.0 < results.rho_squared < 1.0

    util = {(c.attribute, c.level): c.utility for c in results.coefficients}

    # Ordering: price utility should strictly decrease as price increases.
    assert util[("Price", "$10")] > util[("Price", "$20")] > util[("Price", "$30")]
    # Size preference should increase S < M < L.
    assert util[("Size", "S")] < util[("Size", "M")] < util[("Size", "L")]
    # Globex preferred over Acme.
    assert util[("Brand", "Globex")] > 0

    # With this much data, estimates should land near the truth.
    for (attr, lvl), true_val in TRUE.items():
        assert math.isclose(util[(attr, lvl)], true_val, abs_tol=0.25), (
            attr, lvl, util[(attr, lvl)], true_val
        )

    # The "none" constant should be negative and roughly recovered.
    assert results.none_utility is not None
    assert results.none_utility < 0


def test_importance_sums_to_100():
    obs = _simulate(num_respondents=150)
    results = analyze(ATTRS, obs, include_none=True)
    total = sum(i.importance for i in results.importances)
    assert math.isclose(total, 100.0, abs_tol=1e-6)
    # Price has the widest utility range, so it should be the top driver.
    top = max(results.importances, key=lambda i: i.importance)
    assert top.attribute == "Price"


def test_reference_levels_have_zero_utility():
    obs = _simulate(num_respondents=80)
    results = analyze(ATTRS, obs, include_none=True)
    for c in results.coefficients:
        if c.is_reference:
            assert c.utility == 0.0


def test_predict_shares_prefers_better_profile():
    obs = _simulate(num_respondents=200)
    results = analyze(ATTRS, obs, include_none=True)
    cheap_good = {"Price": "$10", "Brand": "Globex", "Size": "L"}
    pricey_bad = {"Price": "$30", "Brand": "Acme", "Size": "S"}
    shares = predict_shares(results, [cheap_good, pricey_bad])
    assert math.isclose(sum(shares), 1.0)
    assert shares[0] > shares[1]


def test_empty_observations_raise():
    import pytest
    with pytest.raises(ValueError):
        analyze(ATTRS, [], include_none=True)


def test_significance_stats_present():
    obs = _simulate(num_respondents=300)
    results = analyze(ATTRS, obs, include_none=True)
    for c in results.coefficients:
        if c.is_reference:
            assert c.t_stat is None and c.p_value is None
        else:
            assert c.t_stat is not None
            assert 0.0 <= c.p_value <= 1.0
            assert c.ci_low < c.utility < c.ci_high
    # The strong price effect should be statistically significant.
    expensive = next(
        c for c in results.coefficients if (c.attribute, c.level) == ("Price", "$30")
    )
    assert expensive.significant


def test_willingness_to_pay():
    obs = _simulate(num_respondents=400)
    results = analyze(ATTRS, obs, include_none=True,
                      price_attribute="Price", currency="$")

    # Price scale was recovered, slope is negative (more price -> less utility).
    assert results.price_attribute == "Price"
    assert results.price_slope is not None and results.price_slope < 0

    wtp = {(e.attribute, e.level): e.wtp for e in results.wtp}
    # Price itself is excluded from WTP entries.
    assert not any(attr == "Price" for attr, _ in wtp)
    # A preferred level (Globex, true utility +0.5) commands positive WTP;
    # the larger size is worth more than the smaller.
    assert wtp[("Brand", "Globex")] > 0
    assert wtp[("Size", "L")] > wtp[("Size", "S")]


def test_no_wtp_without_numeric_price():
    obs = _simulate(num_respondents=100)
    # "Brand" levels are not numeric -> no slope, no WTP.
    results = analyze(ATTRS, obs, include_none=True, price_attribute="Brand")
    assert results.wtp == []
    assert results.price_slope is None
    assert results.price_attribute is None
