"""Populate a demo survey with simulated responses.

Run from the repo root:

    python -m scripts.seed_demo

Then start the app (``uvicorn app.main:app``) and open the printed results URL.
"""

from __future__ import annotations

import random

import numpy as np

from app.config import settings
from app.database import SessionLocal, init_db
from app.design import ConceptSpec
from app.models import (
    Attribute,
    Level,
    Participant,
    ParticipantStatus,
    PricePerception,
    Response,
    Survey,
    SurveyStatus,
    SurveyType,
)
from app.services import generate_and_store_design

# Attribute -> ordered levels for the demo study.
ATTRIBUTES = {
    "Price": ["$8/mo", "$12/mo", "$16/mo"],
    "Roast": ["Light", "Medium", "Dark"],
    "Delivery": ["Weekly", "Biweekly", "Monthly"],
    "Origin": ["Single-origin", "Blend"],
}

# "True" preferences used to simulate respondent choices (reference = first level).
TRUE = {
    ("Price", "$8/mo"): 0.0, ("Price", "$12/mo"): -0.7, ("Price", "$16/mo"): -1.5,
    ("Roast", "Light"): 0.0, ("Roast", "Medium"): 0.4, ("Roast", "Dark"): 0.2,
    ("Delivery", "Weekly"): 0.0, ("Delivery", "Biweekly"): 0.1,
    ("Delivery", "Monthly"): -0.3,
    ("Origin", "Single-origin"): 0.0, ("Origin", "Blend"): -0.4,
}
TRUE_NONE = -1.2


def _utility(concept: ConceptSpec) -> float:
    if concept.is_none:
        return TRUE_NONE
    return sum(TRUE[(a, lvl)] for a, lvl in concept.levels.items())


def seed(num_participants: int = 60, seed: int = 7) -> None:
    init_db()
    rng = random.Random(seed)

    with SessionLocal() as db:
        # Start clean if a prior demo exists.
        existing = db.query(Survey).filter(Survey.name == "Coffee subscription (demo)").all()
        for s in existing:
            db.delete(s)
        db.commit()

        survey = Survey(
            name="Coffee subscription (demo)",
            description="Auto-generated demo study with simulated responses.",
            num_tasks=10,
            alternatives_per_task=3,
            include_none=True,
            currency="$",
        )
        db.add(survey)
        db.flush()
        price_attr_id = None
        for a_pos, (attr_name, levels) in enumerate(ATTRIBUTES.items()):
            attribute = Attribute(survey_id=survey.id, name=attr_name, position=a_pos)
            db.add(attribute)
            db.flush()
            if attr_name == "Price":
                price_attr_id = attribute.id
            for l_pos, value in enumerate(levels):
                db.add(Level(attribute_id=attribute.id, value=value, position=l_pos))
        # Designate Price as the price attribute so willingness-to-pay renders.
        survey.price_attribute_id = price_attr_id
        db.commit()

        generate_and_store_design(db, survey, seed=seed)
        db.refresh(survey)

        for i in range(num_participants):
            participant = Participant(
                survey_id=survey.id,
                email=f"participant{i + 1}@example.com",
                status=ParticipantStatus.completed,
            )
            db.add(participant)
            db.flush()
            for task in survey.tasks:
                concepts = sorted(task.concepts, key=lambda c: c.position)
                specs = [
                    ConceptSpec(levels=c.as_dict(), is_none=c.is_none) for c in concepts
                ]
                utils = np.array([_utility(s) for s in specs])
                utils -= utils.max()
                probs = np.exp(utils) / np.exp(utils).sum()
                chosen = rng.choices(range(len(concepts)), weights=probs)[0]
                db.add(
                    Response(
                        participant_id=participant.id,
                        task_id=task.id,
                        chosen_concept_id=concepts[chosen].id,
                    )
                )
        survey.status = SurveyStatus.active
        db.commit()

        print(f"Seeded conjoint survey id={survey.id} with {num_participants} responses.")
        print(f"  Results: {settings.base_url}/surveys/{survey.id}/results")

        # --- Van Westendorp demo -------------------------------------------
        vw = Survey(
            name="Widget price sensitivity (demo)",
            description="A nifty widget — auto-generated price-perception demo.",
            survey_type=SurveyType.van_westendorp,
            status=SurveyStatus.active,
            currency="$",
        )
        db.add(vw)
        db.flush()
        for i in range(num_participants):
            # Centered around ~$20 with respondent-level variation.
            center = rng.gauss(20, 4)
            participant = Participant(
                survey_id=vw.id,
                email=f"vw{i + 1}@example.com",
                status=ParticipantStatus.completed,
            )
            db.add(participant)
            db.flush()
            db.add(
                PricePerception(
                    participant_id=participant.id,
                    too_cheap=max(1.0, center - rng.uniform(6, 9)),
                    cheap=max(1.5, center - rng.uniform(2, 5)),
                    expensive=center + rng.uniform(2, 5),
                    too_expensive=center + rng.uniform(6, 9),
                )
            )
        db.commit()
        print(f"Seeded Van Westendorp survey id={vw.id} with {num_participants} responses.")
        print(f"  Results: {settings.base_url}/surveys/{vw.id}/results")


if __name__ == "__main__":
    seed()
