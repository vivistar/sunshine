import pytest

from app.design import full_factorial, generate_design

ATTRS = [
    ("Price", ["$10", "$20", "$30"]),
    ("Brand", ["Acme", "Globex"]),
    ("Size", ["S", "M", "L"]),
]


def test_generates_requested_number_of_tasks():
    tasks = generate_design(ATTRS, num_tasks=8, alternatives_per_task=3,
                            include_none=False, seed=1)
    assert len(tasks) == 8
    for task in tasks:
        assert len(task.concepts) == 3


def test_none_option_appended():
    tasks = generate_design(ATTRS, num_tasks=4, alternatives_per_task=2,
                            include_none=True, seed=1)
    for task in tasks:
        # 2 real concepts + 1 none
        assert len(task.concepts) == 3
        assert task.concepts[-1].is_none
        assert task.concepts[-1].levels == {}


def test_each_concept_has_one_level_per_attribute():
    tasks = generate_design(ATTRS, num_tasks=5, alternatives_per_task=3,
                            include_none=False, seed=7)
    for task in tasks:
        for concept in task.concepts:
            assert set(concept.levels.keys()) == {"Price", "Brand", "Size"}
            for attr, levels in ATTRS:
                assert concept.levels[attr] in levels


def test_concepts_unique_within_task():
    tasks = generate_design(ATTRS, num_tasks=10, alternatives_per_task=3,
                            include_none=False, seed=3)
    for task in tasks:
        keys = [tuple(sorted(c.levels.items())) for c in task.concepts]
        assert len(keys) == len(set(keys))


def test_seed_is_reproducible():
    a = generate_design(ATTRS, 6, 3, include_none=True, seed=42)
    b = generate_design(ATTRS, 6, 3, include_none=True, seed=42)
    assert [[c.levels for c in t.concepts] for t in a] == \
           [[c.levels for c in t.concepts] for t in b]


def test_caps_alternatives_to_design_space():
    # 2 attributes x 2 levels = 4 possible concepts; request more than exist.
    small = [("A", ["a1", "a2"]), ("B", ["b1", "b2"])]
    tasks = generate_design(small, num_tasks=3, alternatives_per_task=6,
                            include_none=False, seed=1)
    for task in tasks:
        assert len(task.concepts) <= 4


@pytest.mark.parametrize("bad_attrs", [
    [],
    [("OnlyOne", ["single"])],
])
def test_invalid_attributes_raise(bad_attrs):
    with pytest.raises(ValueError):
        generate_design(bad_attrs, 4, 2)


def test_full_factorial_size():
    profiles = full_factorial(ATTRS)
    assert len(profiles) == 3 * 2 * 3
