"""Researcher-facing admin UI: build surveys, invite participants, view results."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..config import settings
from ..database import get_db
from ..email_utils import invitation_email, send_email
from ..models import (
    Attribute,
    Level,
    Participant,
    ParticipantStatus,
    Survey,
    SurveyStatus,
)
from ..templating import templates

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_survey(db: Session, survey_id: int) -> Survey:
    survey = db.get(Survey, survey_id)
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")
    return survey


def _parse_lines(raw: str) -> list[str]:
    """Split a textarea / comma list into trimmed, non-empty, de-duped items."""
    parts = re.split(r"[\n,]+", raw or "")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        item = p.strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    surveys = db.scalars(select(Survey).order_by(Survey.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {"surveys": surveys, "email_enabled": settings.email_enabled},
    )


@router.post("/surveys")
def create_survey(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    survey = Survey(name=name.strip(), description=description.strip())
    db.add(survey)
    db.commit()
    return RedirectResponse(f"/surveys/{survey.id}", status_code=303)


@router.get("/surveys/{survey_id}")
def manage_survey(survey_id: int, request: Request, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    completed = sum(
        1 for p in survey.participants if p.status == ParticipantStatus.completed
    )
    can_generate = len(survey.attributes) >= 1 and all(
        len(a.levels) >= 2 for a in survey.attributes
    )
    return templates.TemplateResponse(
        request,
        "admin/survey.html",
        {
            "survey": survey,
            "completed": completed,
            "can_generate": can_generate,
            "email_enabled": settings.email_enabled,
            "SurveyStatus": SurveyStatus,
            "ParticipantStatus": ParticipantStatus,
        },
    )


@router.post("/surveys/{survey_id}/settings")
def update_settings(
    survey_id: int,
    num_tasks: int = Form(...),
    alternatives_per_task: int = Form(...),
    include_none: bool = Form(False),
    db: Session = Depends(get_db),
):
    survey = _get_survey(db, survey_id)
    survey.num_tasks = max(1, num_tasks)
    survey.alternatives_per_task = max(2, alternatives_per_task)
    survey.include_none = include_none
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/attributes")
def add_attribute(
    survey_id: int,
    name: str = Form(...),
    levels: str = Form(...),
    db: Session = Depends(get_db),
):
    survey = _get_survey(db, survey_id)
    level_values = _parse_lines(levels)
    if not name.strip() or len(level_values) < 2:
        raise HTTPException(
            status_code=400, detail="An attribute needs a name and 2+ levels."
        )
    position = len(survey.attributes)
    attribute = Attribute(survey_id=survey.id, name=name.strip(), position=position)
    db.add(attribute)
    db.flush()
    for i, value in enumerate(level_values):
        db.add(Level(attribute_id=attribute.id, value=value, position=i))
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/attributes/{attribute_id}/delete")
def delete_attribute(
    survey_id: int, attribute_id: int, db: Session = Depends(get_db)
):
    survey = _get_survey(db, survey_id)
    attribute = db.get(Attribute, attribute_id)
    if attribute and attribute.survey_id == survey.id:
        db.delete(attribute)
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/generate")
def generate_design(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if not survey.attributes:
        raise HTTPException(status_code=400, detail="Add attributes first.")
    services.generate_and_store_design(db, survey)
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/participants")
def add_participants(
    survey_id: int, emails: str = Form(...), db: Session = Depends(get_db)
):
    survey = _get_survey(db, survey_id)
    existing = {p.email.lower() for p in survey.participants}
    added = 0
    for email in _parse_lines(emails):
        if not _EMAIL_RE.match(email) or email.lower() in existing:
            continue
        db.add(Participant(survey_id=survey.id, email=email))
        existing.add(email.lower())
        added += 1
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/invite")
def send_invitations(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if survey.status != SurveyStatus.active:
        raise HTTPException(
            status_code=400, detail="Generate the design before inviting."
        )
    sent = 0
    for participant in survey.participants:
        if participant.status == ParticipantStatus.completed:
            continue
        link = f"{settings.base_url}/survey/{participant.token}"
        subject, html, text = invitation_email(survey.name, link)
        if send_email(participant.email, subject, html, text):
            participant.status = ParticipantStatus.invited
            participant.invited_at = datetime.now(timezone.utc)
            sent += 1
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/close")
def close_survey(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    survey.status = SurveyStatus.closed
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/reopen")
def reopen_survey(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if survey.tasks:
        survey.status = SurveyStatus.active
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.get("/surveys/{survey_id}/results")
def results(survey_id: int, request: Request, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    error = None
    analysis_results = None
    try:
        analysis_results = services.run_analysis(survey)
    except ValueError as exc:
        error = str(exc)

    # Group coefficients by attribute for display.
    grouped: dict[str, list] = {}
    if analysis_results:
        for coef in analysis_results.coefficients:
            grouped.setdefault(coef.attribute, []).append(coef)

    return templates.TemplateResponse(
        request,
        "admin/results.html",
        {
            "survey": survey,
            "results": analysis_results,
            "grouped": grouped,
            "error": error,
        },
    )
