"""MaxDiff (best-worst scaling) design generation and counting analysis.

Design: respondents see a series of small *sets*, each a subset of the items,
and pick the **best** and **worst** item in each. We generate a count-balanced
design so every item appears a similar number of times and no item repeats
within a set.

Analysis (counting model): for each item we tally how often it was shown, picked
best, and picked worst. The standard **best-minus-worst score** is

    score = (best_count - worst_count) / appearances        (range -1 .. +1)

Items are reported sorted best-first. (A multinomial/rank-ordered logit model is
a natural future extension; counting is the widely used, transparent baseline.)
"""

from __future__ import annotations

import random
from dataclasses import dataclass


def suggested_num_sets(n_items: int, items_per_set: int) -> int:
    """A reasonable default: enough sets for each item to appear ~3 times."""
    if n_items <= 0 or items_per_set <= 0:
        return 0
    import math

    return max(1, math.ceil(3 * n_items / items_per_set))


def generate_design(
    n_items: int,
    items_per_set: int,
    num_sets: int,
    seed: int | None = None,
) -> list[list[int]]:
    """Return ``num_sets`` sets of distinct item indices (0..n_items-1).

    Greedy count balancing: each set takes the least-used items so far (random
    tie-break), keeping appearances even and items within a set distinct.
    """
    if items_per_set < 2:
        raise ValueError("A MaxDiff set needs at least 2 items.")
    if items_per_set > n_items:
        raise ValueError("Items per set cannot exceed the number of items.")
    if num_sets < 1:
        raise ValueError("Need at least one set.")

    rng = random.Random(seed)
    counts = [0] * n_items
    sets: list[list[int]] = []
    for _ in range(num_sets):
        order = sorted(range(n_items), key=lambda i: (counts[i], rng.random()))
        chosen = order[:items_per_set]
        for i in chosen:
            counts[i] += 1
        rng.shuffle(chosen)
        sets.append(chosen)
    return sets


@dataclass
class MaxDiffItemResult:
    item_id: int
    text: str
    appearances: int
    best: int
    worst: int
    score: float      # (best - worst) / appearances
    best_pct: float   # best / appearances * 100
    worst_pct: float  # worst / appearances * 100


@dataclass
class MaxDiffResults:
    num_responses: int
    items: list[MaxDiffItemResult]  # sorted best-first


@dataclass
class Observation:
    shown: list[int]  # item ids shown in the set
    best: int         # item id picked best
    worst: int        # item id picked worst


def summarize(
    items: list[tuple[int, str]],
    observations: list[Observation],
    num_responses: int,
) -> MaxDiffResults:
    """Counting analysis over best/worst picks. Raises if there are none."""
    if not observations:
        raise ValueError("No responses yet.")

    appearances: dict[int, int] = {item_id: 0 for item_id, _ in items}
    best: dict[int, int] = {item_id: 0 for item_id, _ in items}
    worst: dict[int, int] = {item_id: 0 for item_id, _ in items}

    for obs in observations:
        for item_id in obs.shown:
            if item_id in appearances:
                appearances[item_id] += 1
        if obs.best in best:
            best[obs.best] += 1
        if obs.worst in worst:
            worst[obs.worst] += 1

    results: list[MaxDiffItemResult] = []
    for item_id, text in items:
        apps = appearances[item_id]
        b, w = best[item_id], worst[item_id]
        score = ((b - w) / apps) if apps else 0.0
        results.append(
            MaxDiffItemResult(
                item_id=item_id,
                text=text,
                appearances=apps,
                best=b,
                worst=w,
                score=score,
                best_pct=(100.0 * b / apps) if apps else 0.0,
                worst_pct=(100.0 * w / apps) if apps else 0.0,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return MaxDiffResults(num_responses=num_responses, items=results)
