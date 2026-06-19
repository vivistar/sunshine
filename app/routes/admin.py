"""Researcher-facing admin UI: build surveys, invite participants, view results."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analysis, audit, services
from ..config import settings
from ..database import get_db
from ..email_utils import invitation_email, send_email
from ..models import (
    Attribute,
    Item,
    Level,
    MaxDiffConfig,
    Participant,
    ParticipantStatus,
    RatingConfig,
    RatingMode,
    Survey,
    SurveyStatus,
    SurveyType,
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


def _parse_int(value: str | None) -> int | None:
    if value is None or not str(value).strip().isdigit():
        return None
    return int(value)


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    surveys = db.scalars(select(Survey).order_by(Survey.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {
            "surveys": surveys,
            "email_enabled": settings.email_enabled,
            "SurveyType": SurveyType,
        },
    )


@router.post("/surveys")
def create_survey(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    survey_type: str = Form("conjoint"),
    currency: str = Form("$"),
    db: Session = Depends(get_db),
):
    stype = {
        "van_westendorp": SurveyType.van_westendorp,
        "rating": SurveyType.rating,
        "maxdiff": SurveyType.maxdiff,
    }.get(survey_type, SurveyType.conjoint)
    survey = Survey(
        name=name.strip(),
        description=description.strip(),
        survey_type=stype,
        currency=currency.strip() or "$",
    )
    # Van Westendorp needs no design step, so it can collect responses at once.
    if stype == SurveyType.van_westendorp:
        survey.status = SurveyStatus.active
    db.add(survey)
    db.flush()
    # Type-specific settings live in companion config rows (additive schema).
    if stype == SurveyType.rating:
        db.add(RatingConfig(survey_id=survey.id))
    elif stype == SurveyType.maxdiff:
        db.add(MaxDiffConfig(survey_id=survey.id))
    db.commit()
    audit.record(
        "survey_created", request, id=survey.id, name=survey.name, type=stype.value
    )
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
    if survey.survey_type == SurveyType.maxdiff:
        k = survey.maxdiff_config.items_per_set if survey.maxdiff_config else 4
        can_generate = len(survey.items) >= max(3, k)
    return templates.TemplateResponse(
        request,
        "admin/survey.html",
        {
            "survey": survey,
            "completed": completed,
            "can_generate": can_generate,
            "email_enabled": settings.email_enabled,
            "SurveyStatus": SurveyStatus,
            "SurveyType": SurveyType,
            "RatingMode": RatingMode,
            "ParticipantStatus": ParticipantStatus,
        },
    )


@router.post("/surveys/{survey_id}/settings")
def update_settings(
    survey_id: int,
    currency: str = Form("$"),
    num_tasks: str | None = Form(None),
    alternatives_per_task: str | None = Form(None),
    include_none: bool = Form(False),
    price_attribute_id: str | None = Form(None),
    rating_mode: str = Form("rate"),
    scale_points: str | None = Form(None),
    min_label: str = Form(""),
    max_label: str = Form(""),
    items_per_set: str | None = Form(None),
    num_sets: str | None = Form(None),
    db: Session = Depends(get_db),
):
    survey = _get_survey(db, survey_id)
    survey.currency = currency.strip() or "$"
    if survey.survey_type == SurveyType.conjoint:
        if (nt := _parse_int(num_tasks)) is not None:
            survey.num_tasks = max(1, nt)
        if (alt := _parse_int(alternatives_per_task)) is not None:
            survey.alternatives_per_task = max(2, alt)
        survey.include_none = include_none
        pid = _parse_int(price_attribute_id)
        # Only accept an attribute id that belongs to this survey.
        survey.price_attribute_id = (
            pid if pid in {a.id for a in survey.attributes} else None
        )
    elif survey.survey_type == SurveyType.rating:
        cfg = survey.rating_config
        if cfg is None:
            cfg = RatingConfig(survey_id=survey.id)
            db.add(cfg)
        cfg.mode = RatingMode.rank if rating_mode == "rank" else RatingMode.rate
        if (sp := _parse_int(scale_points)) is not None:
            cfg.scale_points = min(11, max(2, sp))
        cfg.min_label = min_label.strip()[:80]
        cfg.max_label = max_label.strip()[:80]
    elif survey.survey_type == SurveyType.maxdiff:
        cfg = survey.maxdiff_config
        if cfg is None:
            cfg = MaxDiffConfig(survey_id=survey.id)
            db.add(cfg)
        if (ips := _parse_int(items_per_set)) is not None:
            cfg.items_per_set = max(2, ips)
        if (ns := _parse_int(num_sets)) is not None:
            cfg.num_sets = max(0, ns)  # 0 = auto
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
    if survey.survey_type != SurveyType.conjoint:
        raise HTTPException(status_code=400, detail="Attributes apply to conjoint surveys.")
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
        if survey.price_attribute_id == attribute.id:
            survey.price_attribute_id = None
        db.delete(attribute)
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/items")
def add_items(survey_id: int, items: str = Form(...), db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if survey.survey_type not in (SurveyType.rating, SurveyType.maxdiff):
        raise HTTPException(
            status_code=400, detail="Items apply to ranking/rating and MaxDiff surveys."
        )
    existing = {it.text.lower() for it in survey.items}
    position = len(survey.items)
    for text in _parse_lines(items):
        if text.lower() in existing:
            continue
        db.add(Item(survey_id=survey.id, text=text, position=position))
        existing.add(text.lower())
        position += 1
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/items/{item_id}/delete")
def delete_item(survey_id: int, item_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    item = db.get(Item, item_id)
    if item and item.survey_id == survey.id:
        db.delete(item)
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/activate")
def activate_survey(survey_id: int, db: Session = Depends(get_db)):
    """Activate a ranking/rating survey once it has at least two items."""
    survey = _get_survey(db, survey_id)
    if survey.survey_type == SurveyType.rating and len(survey.items) >= 2:
        survey.status = SurveyStatus.active
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/generate")
def generate_design(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if survey.survey_type == SurveyType.conjoint:
        if not survey.attributes:
            raise HTTPException(status_code=400, detail="Add attributes first.")
        services.generate_and_store_design(db, survey)
    elif survey.survey_type == SurveyType.maxdiff:
        cfg = survey.maxdiff_config
        k = cfg.items_per_set if cfg else 4
        if len(survey.items) < k:
            raise HTTPException(
                status_code=400,
                detail="Add at least as many items as items-per-set first.",
            )
        services.generate_and_store_maxdiff(db, survey)
    else:
        raise HTTPException(status_code=400, detail="This survey has no design step.")
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/participants")
def add_participants(
    survey_id: int, emails: str = Form(...), db: Session = Depends(get_db)
):
    survey = _get_survey(db, survey_id)
    existing = {p.email.lower() for p in survey.participants}
    for email in _parse_lines(emails):
        if not _EMAIL_RE.match(email) or email.lower() in existing:
            continue
        db.add(Participant(survey_id=survey.id, email=email))
        existing.add(email.lower())
    db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/invite")
def send_invitations(survey_id: int, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)
    if survey.status != SurveyStatus.active:
        raise HTTPException(
            status_code=400, detail="The survey must be active before inviting."
        )
    for participant in survey.participants:
        if participant.status == ParticipantStatus.completed:
            continue
        link = f"{settings.effective_base_url}/survey/{participant.token}"
        subject, html, text = invitation_email(survey.name, link)
        if send_email(participant.email, subject, html, text):
            participant.status = ParticipantStatus.invited
            participant.invited_at = datetime.now(timezone.utc)
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
    # Conjoint needs a generated design; rating needs items; VW is always ready.
    ready = (
        survey.survey_type == SurveyType.van_westendorp
        or bool(survey.tasks)
        or (survey.survey_type == SurveyType.rating and len(survey.items) >= 2)
        or (survey.survey_type == SurveyType.maxdiff and bool(survey.maxdiff_sets))
    )
    if ready:
        survey.status = SurveyStatus.active
        db.commit()
    return RedirectResponse(f"/surveys/{survey_id}", status_code=303)


@router.post("/surveys/{survey_id}/delete")
def delete_survey(survey_id: int, request: Request, db: Session = Depends(get_db)):
    """Permanently delete a survey and everything under it.

    Relationships on Survey cascade (all, delete-orphan), so the design,
    participants, and all collected responses go with it. Recorded to the audit
    log since this is destructive and irreversible.
    """
    survey = _get_survey(db, survey_id)
    name = survey.name
    db.delete(survey)
    db.commit()
    audit.record("survey_deleted", request, id=survey_id, name=name)
    return RedirectResponse("/", status_code=303)


@router.get("/surveys/{survey_id}/results")
def results(survey_id: int, request: Request, db: Session = Depends(get_db)):
    survey = _get_survey(db, survey_id)

    if survey.survey_type == SurveyType.van_westendorp:
        error = None
        vw = None
        try:
            vw = services.run_van_westendorp(survey)
        except ValueError as exc:
            error = str(exc)
        return templates.TemplateResponse(
            request,
            "admin/results_vw.html",
            {"survey": survey, "results": vw, "error": error},
        )

    if survey.survey_type == SurveyType.rating:
        error = None
        summary = None
        try:
            summary = services.run_rating_summary(survey)
        except ValueError as exc:
            error = str(exc)
        return templates.TemplateResponse(
            request,
            "admin/results_rating.html",
            {"survey": survey, "results": summary, "error": error,
             "RatingMode": RatingMode},
        )

    if survey.survey_type == SurveyType.maxdiff:
        error = None
        summary = None
        try:
            summary = services.run_maxdiff_summary(survey)
        except ValueError as exc:
            error = str(exc)
        return templates.TemplateResponse(
            request,
            "admin/results_maxdiff.html",
            {"survey": survey, "results": summary, "error": error},
        )

    error = None
    analysis_results = None
    try:
        analysis_results = services.run_analysis(survey)
    except ValueError as exc:
        error = str(exc)

    grouped: dict[str, list] = {}
    wtp_grouped: dict[str, list] = {}
    if analysis_results:
        for coef in analysis_results.coefficients:
            grouped.setdefault(coef.attribute, []).append(coef)
        for entry in analysis_results.wtp:
            wtp_grouped.setdefault(entry.attribute, []).append(entry)

    return templates.TemplateResponse(
        request,
        "admin/results.html",
        {
            "survey": survey,
            "results": analysis_results,
            "grouped": grouped,
            "wtp_grouped": wtp_grouped,
            "error": error,
        },
    )


@router.api_route("/surveys/{survey_id}/simulator", methods=["GET", "POST"])
async def simulator(survey_id: int, request: Request, db: Session = Depends(get_db)):
    """Share-of-preference market simulator for competing profiles."""
    survey = _get_survey(db, survey_id)
    if survey.survey_type != SurveyType.conjoint:
        raise HTTPException(status_code=400, detail="Simulator is for conjoint surveys.")

    error = None
    results_obj = None
    try:
        results_obj = services.run_analysis(survey)
    except ValueError as exc:
        error = str(exc)

    attributes = [(a.name, [lvl.value for lvl in a.levels]) for a in survey.attributes]
    n_products = 3
    profiles: list[dict[str, str]] = []
    shares: list[float] | None = None

    if request.method == "POST" and results_obj:
        form = await request.form()
        n_products = _parse_int(form.get("n_products")) or 3
        for p in range(n_products):
            profile = {}
            for attr_name, levels in attributes:
                chosen = form.get(f"p{p}_{attr_name}")
                profile[attr_name] = chosen if chosen in levels else levels[0]
            profiles.append(profile)
        shares = analysis.predict_shares(results_obj, profiles)

    if not profiles:
        # Default: first level for every attribute, in each product column.
        profiles = [
            {name: levels[0] for name, levels in attributes}
            for _ in range(n_products)
        ]

    return templates.TemplateResponse(
        request,
        "admin/simulator.html",
        {
            "survey": survey,
            "attributes": attributes,
            "profiles": profiles,
            "shares": shares,
            "n_products": n_products,
            "error": error,
        },
    )
