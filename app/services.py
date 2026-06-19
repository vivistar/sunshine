"""Service helpers bridging the ORM models and the conjoint engine."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import analysis, design, maxdiff, rating, van_westendorp
from .models import (
    Concept,
    ConceptLevel,
    ItemResponse,
    MaxDiffResponse,
    MaxDiffSet,
    MaxDiffSetItem,
    Participant,
    ParticipantStatus,
    PricePerception,
    RatingMode,
    Response,
    Survey,
    SurveyStatus,
    Task,
)


def attribute_level_lists(survey: Survey) -> list[tuple[str, list[str]]]:
    """Ordered [(attribute_name, [level values])] for the survey."""
    return [
        (attr.name, [lvl.value for lvl in attr.levels])
        for attr in survey.attributes
    ]


def generate_and_store_design(
    db: Session, survey: Survey, seed: int | None = None
) -> None:
    """(Re)generate the choice design and persist tasks/concepts.

    Any previously generated tasks (and their responses) are removed, so this
    should only be done while a survey has no responses worth keeping.
    """
    attrs = attribute_level_lists(survey)

    # Map (attr name, level value) -> ORM ids for building ConceptLevel rows.
    attr_by_name = {a.name: a for a in survey.attributes}
    level_id: dict[tuple[str, str], int] = {}
    for attr in survey.attributes:
        for lvl in attr.levels:
            level_id[(attr.name, lvl.value)] = lvl.id

    # Clear existing design.
    for task in list(survey.tasks):
        db.delete(task)
    db.flush()

    task_specs = design.generate_design(
        attrs,
        num_tasks=survey.num_tasks,
        alternatives_per_task=survey.alternatives_per_task,
        include_none=survey.include_none,
        seed=seed,
    )

    for t_pos, task_spec in enumerate(task_specs):
        task = Task(survey_id=survey.id, position=t_pos)
        db.add(task)
        db.flush()
        for c_pos, concept_spec in enumerate(task_spec.concepts):
            concept = Concept(
                task_id=task.id, position=c_pos, is_none=concept_spec.is_none
            )
            db.add(concept)
            db.flush()
            for attr_name, level_value in concept_spec.levels.items():
                db.add(
                    ConceptLevel(
                        concept_id=concept.id,
                        attribute_id=attr_by_name[attr_name].id,
                        level_id=level_id[(attr_name, level_value)],
                    )
                )

    survey.status = SurveyStatus.active
    db.commit()


def gather_observations(survey: Survey) -> list[analysis.Observation]:
    """Build MNL observations from every completed response in the survey."""
    observations: list[analysis.Observation] = []
    for participant in survey.participants:
        for response in participant.responses:
            task = response.task
            concepts = sorted(task.concepts, key=lambda c: c.position)
            alternatives = [
                design.ConceptSpec(levels=c.as_dict(), is_none=c.is_none)
                for c in concepts
            ]
            chosen_index = next(
                (i for i, c in enumerate(concepts) if c.id == response.chosen_concept_id),
                None,
            )
            if chosen_index is None:
                continue
            observations.append(
                analysis.Observation(
                    alternatives=alternatives, chosen_index=chosen_index
                )
            )
    return observations


def run_analysis(survey: Survey) -> analysis.ConjointResults:
    attrs = attribute_level_lists(survey)
    observations = gather_observations(survey)
    price_attribute = None
    if survey.price_attribute_id is not None and survey.price_attribute:
        price_attribute = survey.price_attribute.name
    return analysis.analyze(
        attrs,
        observations,
        include_none=survey.include_none,
        price_attribute=price_attribute,
        currency=survey.currency,
    )


def record_completion(
    db: Session, participant: Participant, choices: dict[int, int]
) -> None:
    """Persist a participant's choices (task_id -> chosen_concept_id)."""
    # Replace any prior (partial) responses for idempotency.
    for resp in list(participant.responses):
        db.delete(resp)
    db.flush()
    for task_id, concept_id in choices.items():
        db.add(
            Response(
                participant_id=participant.id,
                task_id=task_id,
                chosen_concept_id=concept_id,
            )
        )
    participant.status = ParticipantStatus.completed
    participant.completed_at = datetime.now(timezone.utc)
    db.commit()


# --- Ranking / Rating -------------------------------------------------------

def gather_item_responses(survey: Survey) -> list[dict[int, int]]:
    """One {item_id: value} dict per participant that answered."""
    out: list[dict[int, int]] = []
    for participant in survey.participants:
        if participant.item_responses:
            out.append({ir.item_id: ir.value for ir in participant.item_responses})
    return out


def run_rating_summary(survey: Survey) -> rating.RatingSummary:
    cfg = survey.rating_config
    items = [(it.id, it.text) for it in survey.items]
    if not items:
        raise ValueError("Add items first.")
    return rating.summarize(
        items,
        gather_item_responses(survey),
        mode=cfg.mode if cfg else RatingMode.rate,
        scale_points=cfg.scale_points if cfg else 5,
        min_label=cfg.min_label if cfg else "",
        max_label=cfg.max_label if cfg else "",
    )


def record_item_responses(
    db: Session, participant: Participant, values: dict[int, int]
) -> None:
    """Persist a participant's item ratings/ranks (item_id -> value)."""
    for ir in list(participant.item_responses):
        db.delete(ir)
    db.flush()
    for item_id, value in values.items():
        db.add(
            ItemResponse(participant_id=participant.id, item_id=item_id, value=value)
        )
    participant.status = ParticipantStatus.completed
    participant.completed_at = datetime.now(timezone.utc)
    db.commit()


# --- MaxDiff ----------------------------------------------------------------

def generate_and_store_maxdiff(
    db: Session, survey: Survey, seed: int | None = None
) -> None:
    """(Re)generate the MaxDiff design and persist sets. Clears prior sets."""
    cfg = survey.maxdiff_config
    items = list(survey.items)
    n = len(items)
    k = cfg.items_per_set if cfg else 4
    num_sets = (cfg.num_sets if cfg and cfg.num_sets else 0) or \
        maxdiff.suggested_num_sets(n, k)

    design_sets = maxdiff.generate_design(n, k, num_sets, seed=seed)

    for mset in list(survey.maxdiff_sets):
        db.delete(mset)
    db.flush()

    for s_pos, item_indices in enumerate(design_sets):
        mset = MaxDiffSet(survey_id=survey.id, position=s_pos)
        db.add(mset)
        db.flush()
        for i_pos, idx in enumerate(item_indices):
            db.add(
                MaxDiffSetItem(set_id=mset.id, item_id=items[idx].id, position=i_pos)
            )

    survey.status = SurveyStatus.active
    db.commit()


def gather_maxdiff_observations(survey: Survey) -> list[maxdiff.Observation]:
    set_items = {
        mset.id: [si.item_id for si in mset.set_items] for mset in survey.maxdiff_sets
    }
    out: list[maxdiff.Observation] = []
    for participant in survey.participants:
        for resp in participant.maxdiff_responses:
            shown = set_items.get(resp.set_id, [])
            out.append(
                maxdiff.Observation(
                    shown=shown, best=resp.best_item_id, worst=resp.worst_item_id
                )
            )
    return out


def run_maxdiff_summary(survey: Survey) -> maxdiff.MaxDiffResults:
    items = [(it.id, it.text) for it in survey.items]
    if not items:
        raise ValueError("Add items first.")
    num_responses = sum(
        1 for p in survey.participants if p.maxdiff_responses
    )
    return maxdiff.summarize(items, gather_maxdiff_observations(survey), num_responses)


def record_maxdiff_responses(
    db: Session, participant: Participant, picks: dict[int, tuple[int, int]]
) -> None:
    """Persist best/worst picks per set (set_id -> (best_item_id, worst_item_id))."""
    for resp in list(participant.maxdiff_responses):
        db.delete(resp)
    db.flush()
    for set_id, (best_id, worst_id) in picks.items():
        db.add(
            MaxDiffResponse(
                participant_id=participant.id,
                set_id=set_id,
                best_item_id=best_id,
                worst_item_id=worst_id,
            )
        )
    participant.status = ParticipantStatus.completed
    participant.completed_at = datetime.now(timezone.utc)
    db.commit()


# --- Van Westendorp ---------------------------------------------------------

def gather_price_responses(survey: Survey) -> list[van_westendorp.PriceResponse]:
    out: list[van_westendorp.PriceResponse] = []
    for participant in survey.participants:
        pp = participant.price_perception
        if pp is not None:
            out.append(
                van_westendorp.PriceResponse(
                    too_cheap=pp.too_cheap,
                    cheap=pp.cheap,
                    expensive=pp.expensive,
                    too_expensive=pp.too_expensive,
                )
            )
    return out


def run_van_westendorp(survey: Survey) -> van_westendorp.VanWestendorpResults:
    return van_westendorp.analyze(
        gather_price_responses(survey), currency=survey.currency
    )


def record_price_perception(
    db: Session,
    participant: Participant,
    too_cheap: float,
    cheap: float,
    expensive: float,
    too_expensive: float,
) -> None:
    """Persist a participant's four Van Westendorp price points."""
    if participant.price_perception is not None:
        db.delete(participant.price_perception)
        db.flush()
    db.add(
        PricePerception(
            participant_id=participant.id,
            too_cheap=too_cheap,
            cheap=cheap,
            expensive=expensive,
            too_expensive=too_expensive,
        )
    )
    participant.status = ParticipantStatus.completed
    participant.completed_at = datetime.now(timezone.utc)
    db.commit()
