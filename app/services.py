"""Service helpers bridging the ORM models and the conjoint engine."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import analysis, design, van_westendorp
from .models import (
    Concept,
    ConceptLevel,
    Participant,
    ParticipantStatus,
    PricePerception,
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
