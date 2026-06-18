"""Aggregate Choice-Based Conjoint analysis via multinomial logit (MNL).

Given the choice tasks respondents completed and the alternative each picked,
we estimate population-level *part-worth utilities* by maximum likelihood under
the conditional/multinomial logit model:

    P(choose j in task t) = exp(x_j · β) / Σ_k exp(x_k · β)

Attribute levels are dummy coded with the first level of each attribute as the
reference (utility fixed at 0). An optional alternative-specific constant
captures the "None of these" option. We report part-worth utilities with
standard errors (from the inverse observed-information matrix) and derive
relative attribute importance from the utility range of each attribute.

This is the standard aggregate CBC estimator. Individual-level estimation
(hierarchical Bayes) is a natural future extension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from scipy import optimize
from scipy.stats import norm

from .design import ConceptSpec

_NONE_KEY = "__none__"
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_price(value: str) -> float | None:
    """Extract a numeric price from a level label like '$12/mo' or '1,200'."""
    match = _NUMBER_RE.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


@dataclass
class Observation:
    """One completed choice task: the alternatives shown and the pick."""

    alternatives: list[ConceptSpec]
    chosen_index: int


@dataclass
class Coefficient:
    attribute: str
    level: str
    utility: float
    std_error: float
    is_reference: bool = False
    t_stat: float | None = None
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < 0.05


@dataclass
class AttributeImportance:
    attribute: str
    importance: float  # percent, 0-100


@dataclass
class WTPEntry:
    """Willingness to pay for a level, in the survey's currency units."""

    attribute: str
    level: str
    wtp: float
    is_reference: bool = False


@dataclass
class ConjointResults:
    coefficients: list[Coefficient] = field(default_factory=list)
    importances: list[AttributeImportance] = field(default_factory=list)
    none_utility: float | None = None
    none_std_error: float | None = None
    log_likelihood: float = 0.0
    null_log_likelihood: float = 0.0
    rho_squared: float = 0.0
    num_observations: int = 0
    converged: bool = False
    # Willingness-to-pay (populated when a numeric price attribute is set).
    wtp: list[WTPEntry] = field(default_factory=list)
    price_attribute: str | None = None
    price_slope: float | None = None  # utility per currency unit (negative)
    currency: str = "$"


class Encoder:
    """Dummy-codes concepts into design vectors for MNL estimation."""

    def __init__(
        self,
        attributes: list[tuple[str, list[str]]],
        include_none: bool = False,
    ) -> None:
        self.attributes = attributes
        self.include_none = include_none

        # Column layout: optional None ASC first, then (attr, level) for every
        # non-reference level. The reference level is each attribute's first.
        self.columns: list[tuple[str, str]] = []
        if include_none:
            self.columns.append((_NONE_KEY, "None of these"))
        self.references: dict[str, str] = {}
        for name, levels in attributes:
            self.references[name] = levels[0]
            for level in levels[1:]:
                self.columns.append((name, level))
        self._index = {col: i for i, col in enumerate(self.columns)}

    @property
    def n_params(self) -> int:
        return len(self.columns)

    def encode(self, concept: ConceptSpec) -> np.ndarray:
        vec = np.zeros(self.n_params)
        if concept.is_none:
            if self.include_none:
                vec[self._index[(_NONE_KEY, "None of these")]] = 1.0
            return vec
        for attr, level in concept.levels.items():
            col = (attr, level)
            if col in self._index:  # non-reference level
                vec[self._index[col]] = 1.0
        return vec

    def encode_task(self, alternatives: list[ConceptSpec]) -> np.ndarray:
        return np.vstack([self.encode(c) for c in alternatives])


def _neg_log_likelihood(
    beta: np.ndarray, design: list[tuple[np.ndarray, int]]
) -> tuple[float, np.ndarray]:
    """Negative log-likelihood and its gradient for the MNL model."""
    nll = 0.0
    grad = np.zeros_like(beta)
    for x, chosen in design:
        v = x @ beta
        v -= v.max()  # softmax is shift-invariant; this avoids overflow
        ev = np.exp(v)
        probs = ev / ev.sum()
        nll -= np.log(probs[chosen] + 1e-300)
        grad += x.T @ probs - x[chosen]
    return nll, grad


def _observed_information(
    beta: np.ndarray, design: list[tuple[np.ndarray, int]]
) -> np.ndarray:
    """Hessian of the negative log-likelihood (the observed information)."""
    p = beta.size
    info = np.zeros((p, p))
    for x, _ in design:
        v = x @ beta
        v -= v.max()
        ev = np.exp(v)
        probs = ev / ev.sum()
        xbar = x.T @ probs
        info += x.T @ (probs[:, None] * x) - np.outer(xbar, xbar)
    return info


def _coef_stats(
    util: float, se: float
) -> tuple[float | None, float | None, float | None, float | None]:
    """t-statistic, two-sided p-value, and 95% CI for a coefficient."""
    if not se or not np.isfinite(se):
        return None, None, None, None
    t = util / se
    p = 2.0 * (1.0 - norm.cdf(abs(t)))
    return float(t), float(p), float(util - 1.96 * se), float(util + 1.96 * se)


def analyze(
    attributes: list[tuple[str, list[str]]],
    observations: list[Observation],
    include_none: bool = False,
    price_attribute: str | None = None,
    currency: str = "$",
) -> ConjointResults:
    """Estimate part-worth utilities and attribute importance from choices."""
    if not attributes:
        raise ValueError("No attributes to analyze.")
    if not observations:
        raise ValueError("No responses to analyze yet.")

    encoder = Encoder(attributes, include_none=include_none)
    design: list[tuple[np.ndarray, int]] = [
        (encoder.encode_task(obs.alternatives), obs.chosen_index)
        for obs in observations
    ]

    null_ll = -sum(np.log(len(x)) for x, _ in design)

    beta0 = np.zeros(encoder.n_params)
    result = optimize.minimize(
        _neg_log_likelihood,
        beta0,
        args=(design,),
        method="BFGS",
        jac=True,
        options={"gtol": 1e-6, "maxiter": 500},
    )
    beta = result.x
    log_likelihood = -float(result.fun)

    # Standard errors from the inverse observed-information matrix.
    info = _observed_information(beta, design)
    try:
        cov = np.linalg.inv(info)
        std_errors = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    except np.linalg.LinAlgError:
        std_errors = np.full(encoder.n_params, np.nan)

    # Assemble coefficients, inserting the (fixed-at-0) reference levels.
    coefficients: list[Coefficient] = []
    none_utility: float | None = None
    none_std_error: float | None = None
    col_to_value: dict[tuple[str, str], tuple[float, float]] = {}
    for i, (attr, level) in enumerate(encoder.columns):
        col_to_value[(attr, level)] = (float(beta[i]), float(std_errors[i]))
        if attr == _NONE_KEY:
            none_utility, none_std_error = col_to_value[(attr, level)]

    importances: list[AttributeImportance] = []
    ranges: dict[str, float] = {}
    util_by_level: dict[tuple[str, str], float] = {}
    for name, levels in attributes:
        utilities = []
        for level in levels:
            if level == encoder.references[name]:
                util, se = 0.0, 0.0
                is_ref = True
            else:
                util, se = col_to_value[(name, level)]
                is_ref = False
            t, p, ci_low, ci_high = (
                (None, None, None, None) if is_ref else _coef_stats(util, se)
            )
            coefficients.append(
                Coefficient(
                    attribute=name,
                    level=level,
                    utility=util,
                    std_error=se,
                    is_reference=is_ref,
                    t_stat=t,
                    p_value=p,
                    ci_low=ci_low,
                    ci_high=ci_high,
                )
            )
            utilities.append(util)
            util_by_level[(name, level)] = util
        ranges[name] = max(utilities) - min(utilities)

    total_range = sum(ranges.values())
    for name, _ in attributes:
        pct = (ranges[name] / total_range * 100.0) if total_range > 0 else 0.0
        importances.append(AttributeImportance(attribute=name, importance=pct))

    rho_squared = (
        1.0 - (log_likelihood / null_ll) if null_ll != 0 else 0.0
    )

    wtp, price_slope = _willingness_to_pay(
        attributes, util_by_level, price_attribute
    )

    return ConjointResults(
        coefficients=coefficients,
        importances=importances,
        none_utility=none_utility,
        none_std_error=none_std_error,
        log_likelihood=log_likelihood,
        null_log_likelihood=null_ll,
        rho_squared=rho_squared,
        num_observations=len(observations),
        converged=bool(result.success),
        wtp=wtp,
        price_attribute=price_attribute if price_slope is not None else None,
        price_slope=price_slope,
        currency=currency,
    )


def _willingness_to_pay(
    attributes: list[tuple[str, list[str]]],
    util_by_level: dict[tuple[str, str], float],
    price_attribute: str | None,
) -> tuple[list[WTPEntry], float | None]:
    """Convert part-worths into money units using the price attribute slope.

    The marginal utility of money is the slope of utility vs. price across the
    price attribute's (numeric) levels. WTP for any other level is then its
    part-worth divided by that slope — the price change that offsets it.
    """
    if not price_attribute:
        return [], None

    price_levels = next(
        (lvls for name, lvls in attributes if name == price_attribute), None
    )
    if not price_levels:
        return [], None

    points = [
        (parse_price(level), util_by_level.get((price_attribute, level), 0.0))
        for level in price_levels
    ]
    points = [(x, u) for x, u in points if x is not None]
    if len({x for x, _ in points}) < 2:
        return [], None  # need at least two distinct numeric prices

    xs = np.array([x for x, _ in points])
    us = np.array([u for _, u in points])
    slope = float(np.polyfit(xs, us, 1)[0])
    if slope == 0 or not np.isfinite(slope):
        return [], None

    wtp: list[WTPEntry] = []
    for name, levels in attributes:
        if name == price_attribute:
            continue
        for level in levels:
            util = util_by_level.get((name, level), 0.0)
            wtp.append(
                WTPEntry(
                    attribute=name,
                    level=level,
                    wtp=util / -slope,
                    is_reference=(util == 0.0 and level == levels[0]),
                )
            )
    return wtp, slope


def predict_shares(
    results: ConjointResults,
    profiles: list[dict[str, str]],
) -> list[float]:
    """Share-of-preference simulation for a set of competing profiles.

    Uses the estimated part-worths to compute each profile's logit share in a
    hypothetical market made up of exactly the supplied profiles.
    """
    util_lookup = {
        (c.attribute, c.level): c.utility for c in results.coefficients
    }
    totals = []
    for profile in profiles:
        total = sum(util_lookup.get((attr, lvl), 0.0) for attr, lvl in profile.items())
        totals.append(total)
    arr = np.array(totals)
    arr -= arr.max()
    ev = np.exp(arr)
    shares = ev / ev.sum()
    return [float(s) for s in shares]
