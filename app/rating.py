"""Summaries for Ranking / Rating surveys.

Two modes:

- ``rate`` — each respondent rates every item on a shared 1..scale_points scale
  (the "matrix" grid). Higher is better.
- ``rank`` — each respondent orders the items, 1 (best) .. N (worst). Lower is
  better.

For each item we report the response count, mean, the distribution across the
columns, and a "top choice" share (top-box for rate; ranked #1 for rank). Items
are returned sorted best-first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import RatingMode


@dataclass
class ItemSummary:
    item_id: int
    text: str
    n: int
    mean: float
    distribution: list[int]  # counts aligned to columns, left -> right
    top_choice_pct: float    # % of respondents giving this item the best response


@dataclass
class RatingSummary:
    mode: RatingMode
    columns: list[str]        # column headers (scale points, or rank positions)
    num_responses: int        # respondents with at least one answer
    items: list[ItemSummary]  # sorted best-first
    min_label: str
    max_label: str


def summarize(
    items: list[tuple[int, str]],
    responses: list[dict[int, int]],
    mode: RatingMode,
    scale_points: int,
    min_label: str = "",
    max_label: str = "",
) -> RatingSummary:
    """Aggregate per-item statistics.

    ``items`` is ordered ``[(item_id, text), ...]``. ``responses`` is one dict
    per respondent mapping ``item_id -> value`` (rate: 1..scale_points; rank:
    1..N where 1 is best). Raises ``ValueError`` when there are no responses.
    """
    non_empty = [r for r in responses if r]
    if not non_empty:
        raise ValueError("No responses yet.")

    if mode == RatingMode.rank:
        n_cols = len(items)
        best_value = 1            # rank 1 is best
        sort_descending = False   # lower mean rank first
    else:
        n_cols = max(2, scale_points)
        best_value = n_cols       # top box is best
        sort_descending = True    # higher mean first

    columns = [str(i + 1) for i in range(n_cols)]

    summaries: list[ItemSummary] = []
    for item_id, text in items:
        values = [r[item_id] for r in non_empty if item_id in r]
        n = len(values)
        dist = [0] * n_cols
        for v in values:
            if 1 <= v <= n_cols:
                dist[v - 1] += 1
        mean = (sum(values) / n) if n else 0.0
        top = (100.0 * sum(1 for v in values if v == best_value) / n) if n else 0.0
        summaries.append(ItemSummary(item_id, text, n, mean, dist, top))

    summaries.sort(key=lambda s: s.mean, reverse=sort_descending)
    return RatingSummary(
        mode=mode,
        columns=columns,
        num_responses=len(non_empty),
        items=summaries,
        min_label=min_label,
        max_label=max_label,
    )
