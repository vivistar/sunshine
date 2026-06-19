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
    Item,
    ItemResponse,
    Level,
    MaxDiffConfig,
    MaxDiffResponse,
    Participant,
    ParticipantStatus,
    PricePerception,
    RatingConfig,
    RatingMode,
    Response,
    Survey,
    SurveyStatus,
    SurveyType,
)
from app.services import generate_and_store_design, generate_and_store_maxdiff

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
        print(f"  Results: {settings.effective_base_url}/surveys/{survey.id}/results")

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
        print(f"  Results: {settings.effective_base_url}/surveys/{vw.id}/results")

        # --- Ranking / Rating demo -----------------------------------------
        rating_items = [
            "Faster customer support",
            "Lower monthly price",
            "More integrations",
            "Better mobile app",
            "Advanced analytics",
        ]
        appeal = [4.4, 4.6, 3.5, 3.9, 3.2]  # simulated mean rating per item (1-5)
        rt = Survey(
            name="Feature priorities (demo)",
            description="Which improvements matter most? Rate each from 1 to 5.",
            survey_type=SurveyType.rating,
            status=SurveyStatus.active,
            currency="$",
        )
        db.add(rt)
        db.flush()
        db.add(RatingConfig(
            survey_id=rt.id, mode=RatingMode.rate, scale_points=5,
            min_label="Not important", max_label="Very important",
        ))
        items = []
        for pos, text in enumerate(rating_items):
            item = Item(survey_id=rt.id, text=text, position=pos)
            db.add(item)
            db.flush()
            items.append(item)
        for i in range(num_participants):
            participant = Participant(
                survey_id=rt.id,
                email=f"rate{i + 1}@example.com",
                status=ParticipantStatus.completed,
            )
            db.add(participant)
            db.flush()
            for item, mu in zip(items, appeal):
                value = max(1, min(5, round(rng.gauss(mu, 0.9))))
                db.add(ItemResponse(
                    participant_id=participant.id, item_id=item.id, value=value
                ))
        db.commit()
        print(f"Seeded Ranking/Rating survey id={rt.id} with {num_participants} responses.")
        print(f"  Results: {settings.effective_base_url}/surveys/{rt.id}/results")

        # --- MaxDiff demo ---------------------------------------------------
        md_items = [
            ("Lower price", 2.0),
            ("Fast customer support", 1.6),
            ("Better mobile app", 0.9),
            ("More integrations", 0.4),
            ("Advanced analytics", -0.2),
            ("Single sign-on", -0.6),
            ("Custom branding", -1.2),
        ]
        md = Survey(
            name="Feature trade-offs (demo)",
            description="Pick the best and worst feature in each set.",
            survey_type=SurveyType.maxdiff,
            currency="$",
        )
        db.add(md)
        db.flush()
        db.add(MaxDiffConfig(survey_id=md.id, items_per_set=4, num_sets=0))
        util_by_item: dict[int, float] = {}
        for pos, (text, util) in enumerate(md_items):
            item = Item(survey_id=md.id, text=text, position=pos)
            db.add(item)
            db.flush()
            util_by_item[item.id] = util
        db.commit()
        db.refresh(md)
        generate_and_store_maxdiff(db, md, seed=seed)
        db.refresh(md)

        for i in range(num_participants):
            participant = Participant(
                survey_id=md.id,
                email=f"md{i + 1}@example.com",
                status=ParticipantStatus.completed,
            )
            db.add(participant)
            db.flush()
            for mset in md.maxdiff_sets:
                ids = [si.item_id for si in mset.set_items]
                noisy = {iid: util_by_item[iid] + rng.gauss(0, 0.8) for iid in ids}
                db.add(MaxDiffResponse(
                    participant_id=participant.id,
                    set_id=mset.id,
                    best_item_id=max(noisy, key=noisy.get),
                    worst_item_id=min(noisy, key=noisy.get),
                ))
        db.commit()
        print(f"Seeded MaxDiff survey id={md.id} with {num_participants} responses.")
        print(f"  Results: {settings.effective_base_url}/surveys/{md.id}/results")


if __name__ == "__main__":
    seed()
