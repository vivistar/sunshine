"""Choice-Based Conjoint (CBC) design generation.

We use a *randomized* design: for each choice task we draw a set of distinct
concepts, where each concept assigns one randomly chosen level to every
attribute. Random designs are the workhorse of CBC studies and, with enough
respondents and tasks, yield near level-balanced data suitable for aggregate
multinomial-logit estimation.

The functions here operate on plain Python structures so they can be unit
tested without a database. `build_design_rows` adapts the output onto the ORM.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field


@dataclass
class ConceptSpec:
    """A single alternative: attribute name -> level value."""

    levels: dict[str, str]
    is_none: bool = False


@dataclass
class TaskSpec:
    concepts: list[ConceptSpec] = field(default_factory=list)


def _total_combinations(attributes: list[tuple[str, list[str]]]) -> int:
    total = 1
    for _, levels in attributes:
        total *= max(len(levels), 1)
    return total


def generate_design(
    attributes: list[tuple[str, list[str]]],
    num_tasks: int,
    alternatives_per_task: int,
    include_none: bool = True,
    seed: int | None = None,
) -> list[TaskSpec]:
    """Generate a randomized CBC design.

    Args:
        attributes: ordered list of (attribute_name, [level values]).
        num_tasks: number of choice tasks to present.
        alternatives_per_task: real concepts shown per task (excludes "none").
        include_none: append a "None of these" option to each task.
        seed: optional RNG seed for reproducible designs.

    Returns:
        A list of TaskSpec, each holding its concepts.
    """
    if not attributes:
        raise ValueError("At least one attribute is required.")
    for name, levels in attributes:
        if len(levels) < 2:
            raise ValueError(
                f"Attribute {name!r} needs at least 2 levels (has {len(levels)})."
            )
    if num_tasks < 1:
        raise ValueError("num_tasks must be >= 1.")
    if alternatives_per_task < 2:
        raise ValueError("alternatives_per_task must be >= 2.")

    rng = random.Random(seed)

    # Cap the number of distinct concepts per task by what the design space
    # can actually support, so we never loop forever looking for unique draws.
    max_unique = _total_combinations(attributes)
    per_task = min(alternatives_per_task, max_unique)

    tasks: list[TaskSpec] = []
    for _ in range(num_tasks):
        seen: set[tuple[str, ...]] = set()
        concepts: list[ConceptSpec] = []
        # Bound attempts to avoid pathological loops on tiny design spaces.
        attempts = 0
        while len(concepts) < per_task and attempts < per_task * 50:
            attempts += 1
            chosen = {name: rng.choice(levels) for name, levels in attributes}
            key = tuple(chosen[name] for name, _ in attributes)
            if key in seen:
                continue
            seen.add(key)
            concepts.append(ConceptSpec(levels=chosen))
        if include_none:
            concepts.append(ConceptSpec(levels={}, is_none=True))
        tasks.append(TaskSpec(concepts=concepts))
    return tasks


def full_factorial(
    attributes: list[tuple[str, list[str]]]
) -> list[dict[str, str]]:
    """Enumerate every possible concept (the full-factorial profile set).

    Useful for share-of-preference simulation and for validating designs on
    small attribute spaces. Grows multiplicatively, so use with care.
    """
    names = [name for name, _ in attributes]
    level_lists = [levels for _, levels in attributes]
    return [
        dict(zip(names, combo)) for combo in itertools.product(*level_lists)
    ]
