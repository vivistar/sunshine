"""Respondent-facing survey: take the choice tasks via a unique link."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import van_westendorp
from ..database import get_db
from ..models import (
    Participant,
    ParticipantStatus,
    RatingMode,
    SurveyStatus,
    SurveyType,
)
from ..services import (
    record_completion,
    record_item_responses,
    record_price_perception,
)
from ..templating import templates

router = APIRouter()


def _get_participant(db: Session, token: str) -> Participant | None:
    return db.scalar(select(Participant).where(Participant.token == token))


@router.get("/survey/{token}")
def take_survey(token: str, request: Request, db: Session = Depends(get_db)):
    participant = _get_participant(db, token)
    if participant is None:
        return templates.TemplateResponse(
            request, "survey/closed.html", {"reason": "invalid"}, status_code=404
        )

    survey = participant.survey
    if participant.status == ParticipantStatus.completed:
        return templates.TemplateResponse(
            request, "survey/done.html", {"survey": survey}
        )
    if survey.status != SurveyStatus.active:
        return templates.TemplateResponse(
            request, "survey/closed.html", {"reason": "closed", "survey": survey}
        )

    if survey.survey_type == SurveyType.van_westendorp:
        return templates.TemplateResponse(
            request,
            "survey/van_westendorp.html",
            {"survey": survey, "participant": participant},
        )

    if survey.survey_type == SurveyType.rating:
        cfg = survey.rating_config
        return templates.TemplateResponse(
            request,
            "survey/rating.html",
            {
                "survey": survey,
                "participant": participant,
                "items": survey.items,
                "config": cfg,
                "mode": cfg.mode if cfg else RatingMode.rate,
                "scale_points": cfg.scale_points if cfg else 5,
                "RatingMode": RatingMode,
            },
        )

    # Build display data: each task with its concepts and per-attribute rows.
    attributes = [a.name for a in survey.attributes]
    tasks = []
    for task in survey.tasks:
        concepts = []
        for concept in task.concepts:
            concepts.append(
                {
                    "id": concept.id,
                    "is_none": concept.is_none,
                    "levels": concept.as_dict(),
                }
            )
        tasks.append({"id": task.id, "position": task.position + 1, "concepts": concepts})

    return templates.TemplateResponse(
        request,
        "survey/take.html",
        {
            "survey": survey,
            "participant": participant,
            "attributes": attributes,
            "tasks": tasks,
        },
    )


@router.post("/survey/{token}")
async def submit_survey(token: str, request: Request, db: Session = Depends(get_db)):
    participant = _get_participant(db, token)
    if participant is None:
        return templates.TemplateResponse(
            request, "survey/closed.html", {"reason": "invalid"}, status_code=404
        )
    survey = participant.survey
    if survey.status != SurveyStatus.active:
        return templates.TemplateResponse(
            request, "survey/closed.html", {"reason": "closed", "survey": survey}
        )

    form = await request.form()

    if survey.survey_type == SurveyType.van_westendorp:
        return _submit_van_westendorp(request, db, participant, survey, form)

    if survey.survey_type == SurveyType.rating:
        return _submit_rating(request, db, participant, survey, form)

    # Valid concept ids per task, to guard against tampered submissions.
    valid_by_task = {
        task.id: {c.id for c in task.concepts} for task in survey.tasks
    }

    choices: dict[int, int] = {}
    missing = []
    for task in survey.tasks:
        raw = form.get(f"task_{task.id}")
        if raw is None:
            missing.append(task.position + 1)
            continue
        try:
            concept_id = int(raw)
        except (TypeError, ValueError):
            missing.append(task.position + 1)
            continue
        if concept_id not in valid_by_task[task.id]:
            missing.append(task.position + 1)
            continue
        choices[task.id] = concept_id

    if missing:
        # Re-render with an error rather than silently dropping responses.
        attributes = [a.name for a in survey.attributes]
        tasks = [
            {
                "id": t.id,
                "position": t.position + 1,
                "concepts": [
                    {"id": c.id, "is_none": c.is_none, "levels": c.as_dict()}
                    for c in t.concepts
                ],
            }
            for t in survey.tasks
        ]
        return templates.TemplateResponse(
            request,
            "survey/take.html",
            {
                "survey": survey,
                "participant": participant,
                "attributes": attributes,
                "tasks": tasks,
                "error": f"Please make a selection for task(s): "
                f"{', '.join(map(str, missing))}.",
                "selected": {f"task_{tid}": cid for tid, cid in choices.items()},
            },
            status_code=400,
        )

    record_completion(db, participant, choices)
    return RedirectResponse(f"/survey/{token}", status_code=303)


def _submit_van_westendorp(request, db, participant, survey, form):
    """Validate and store a Van Westendorp price-perception response."""
    fields = ("too_cheap", "cheap", "expensive", "too_expensive")
    values: dict[str, float] = {}
    error = None
    for name in fields:
        raw = form.get(name)
        try:
            values[name] = float(str(raw).replace(",", "").strip())
        except (TypeError, ValueError):
            error = "Please enter a price for all four questions."
            break

    if error is None:
        error = van_westendorp.validate_response(
            values["too_cheap"], values["cheap"],
            values["expensive"], values["too_expensive"],
        )

    if error is not None:
        return templates.TemplateResponse(
            request,
            "survey/van_westendorp.html",
            {
                "survey": survey,
                "participant": participant,
                "error": error,
                "values": {k: form.get(k) for k in fields},
            },
            status_code=400,
        )

    record_price_perception(
        db, participant,
        too_cheap=values["too_cheap"], cheap=values["cheap"],
        expensive=values["expensive"], too_expensive=values["too_expensive"],
    )
    return RedirectResponse(f"/survey/{participant.token}", status_code=303)


def _submit_rating(request, db, participant, survey, form):
    """Validate and store a Ranking/Rating response (one value per item)."""
    cfg = survey.rating_config
    mode = cfg.mode if cfg else RatingMode.rate
    items = survey.items
    values: dict[int, int] = {}
    error = None

    if mode == RatingMode.rank:
        n = len(items)
        seen: set[int] = set()
        for item in items:
            try:
                v = int(form.get(f"item_{item.id}"))
            except (TypeError, ValueError):
                error = "Please assign a rank to every item."
                break
            if v < 1 or v > n or v in seen:
                error = f"Give each item a unique rank from 1 to {n}."
                break
            seen.add(v)
            values[item.id] = v
    else:
        points = cfg.scale_points if cfg else 5
        for item in items:
            try:
                v = int(form.get(f"item_{item.id}"))
            except (TypeError, ValueError):
                error = "Please rate every item."
                break
            if v < 1 or v > points:
                error = f"Ratings must be between 1 and {points}."
                break
            values[item.id] = v

    if error is not None:
        return templates.TemplateResponse(
            request,
            "survey/rating.html",
            {
                "survey": survey,
                "participant": participant,
                "items": items,
                "config": cfg,
                "mode": mode,
                "scale_points": cfg.scale_points if cfg else 5,
                "RatingMode": RatingMode,
                "error": error,
                "selected": values,
            },
            status_code=400,
        )

    record_item_responses(db, participant, values)
    return RedirectResponse(f"/survey/{participant.token}", status_code=303)
