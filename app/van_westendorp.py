"""Van Westendorp Price Sensitivity Meter (PSM) analysis.

Each respondent gives four prices for a product:

* **too cheap**      — so low they'd doubt its quality
* **cheap**          — a bargain / good value
* **expensive**      — starting to feel expensive, but still considerable
* **too expensive**  — so high they would not buy

From these we build four cumulative curves over a price grid and read off the
classic intersection points:

* **OPP** – Optimal Price Point: "too cheap" × "too expensive"
* **IPP** – Indifference Price Point: "cheap" × "expensive"
* **PMC** – Point of Marginal Cheapness (range lower bound): "too cheap" × "expensive"
* **PME** – Point of Marginal Expensiveness (range upper bound): "too expensive" × "cheap"

The **range of acceptable prices** lies between PMC and PME.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PriceResponse:
    too_cheap: float
    cheap: float
    expensive: float
    too_expensive: float


@dataclass
class PricePoint:
    name: str
    label: str
    price: float | None


@dataclass
class VanWestendorpResults:
    num_responses: int = 0
    currency: str = "$"
    opp: float | None = None
    ipp: float | None = None
    pmc: float | None = None  # range lower bound
    pme: float | None = None  # range upper bound
    grid: list[float] = field(default_factory=list)
    too_cheap: list[float] = field(default_factory=list)
    cheap: list[float] = field(default_factory=list)
    expensive: list[float] = field(default_factory=list)
    too_expensive: list[float] = field(default_factory=list)

    @property
    def acceptable_range(self) -> tuple[float | None, float | None]:
        return (self.pmc, self.pme)

    @property
    def points(self) -> list[PricePoint]:
        return [
            PricePoint("OPP", "Optimal Price Point", self.opp),
            PricePoint("IPP", "Indifference Price Point", self.ipp),
            PricePoint("PMC", "Point of Marginal Cheapness (range low)", self.pmc),
            PricePoint("PME", "Point of Marginal Expensiveness (range high)", self.pme),
        ]


def validate_response(
    too_cheap: float, cheap: float, expensive: float, too_expensive: float
) -> str | None:
    """Return an error message if the four prices aren't strictly increasing."""
    values = [too_cheap, cheap, expensive, too_expensive]
    if any(v < 0 for v in values):
        return "Prices cannot be negative."
    if not (too_cheap < cheap < expensive < too_expensive):
        return (
            "Prices must increase: too cheap < cheap < expensive < too expensive."
        )
    return None


def _intersect(
    grid: list[float], a: list[float], b: list[float]
) -> float | None:
    """Price where curves a and b cross, via linear interpolation."""
    diff = [ai - bi for ai, bi in zip(a, b)]
    for i in range(1, len(grid)):
        prev, cur = diff[i - 1], diff[i]
        if prev == 0:
            return grid[i - 1]
        if prev * cur < 0:
            t = prev / (prev - cur)
            return grid[i - 1] + t * (grid[i] - grid[i - 1])
    if diff and diff[-1] == 0:
        return grid[-1]
    return None


def analyze(
    responses: list[PriceResponse], currency: str = "$"
) -> VanWestendorpResults:
    if not responses:
        raise ValueError("No responses to analyze yet.")

    n = len(responses)
    grid = sorted(
        {
            v
            for r in responses
            for v in (r.too_cheap, r.cheap, r.expensive, r.too_expensive)
        }
    )

    def pct(predicate) -> list[float]:
        return [
            100.0 * sum(1 for r in responses if predicate(r, p)) / n for p in grid
        ]

    # "Too cheap" / "cheap" are downward curves (more agreement at low prices);
    # "expensive" / "too expensive" rise as price increases.
    too_cheap = pct(lambda r, p: r.too_cheap >= p)
    cheap = pct(lambda r, p: r.cheap >= p)
    expensive = pct(lambda r, p: r.expensive <= p)
    too_expensive = pct(lambda r, p: r.too_expensive <= p)

    return VanWestendorpResults(
        num_responses=n,
        currency=currency,
        opp=_intersect(grid, too_cheap, too_expensive),
        ipp=_intersect(grid, cheap, expensive),
        pmc=_intersect(grid, too_cheap, expensive),
        pme=_intersect(grid, too_expensive, cheap),
        grid=grid,
        too_cheap=too_cheap,
        cheap=cheap,
        expensive=expensive,
        too_expensive=too_expensive,
    )
