"""End-to-end flow through the web app with the FastAPI TestClient."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.main import app
from app.models import Participant, ParticipantStatus, Survey

client = TestClient(app)


def _create_survey_with_design() -> int:
    init_db()
    # Create survey
    client.post("/surveys", data={"name": "Coffee plan", "description": "demo"})
    with SessionLocal() as db:
        survey = db.scalar(select(Survey).where(Survey.name == "Coffee plan"))
        sid = survey.id

    # Attributes
    client.post(f"/surveys/{sid}/attributes",
                data={"name": "Price", "levels": "$8\n$12\n$16"})
    client.post(f"/surveys/{sid}/attributes",
                data={"name": "Roast", "levels": "Light, Dark"})
    # Design settings + generate
    client.post(f"/surveys/{sid}/settings",
                data={"num_tasks": "5", "alternatives_per_task": "2",
                      "include_none": "true"})
    client.post(f"/surveys/{sid}/generate")
    return sid


def test_full_flow_create_take_and_analyze():
    sid = _create_survey_with_design()

    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        assert survey.status.value == "active"
        assert len(survey.tasks) == 5
        for task in survey.tasks:
            # 2 real concepts + a none option
            assert len(task.concepts) == 3

    # Add a participant
    client.post(f"/surveys/{sid}/participants", data={"emails": "alice@example.com"})

    with SessionLocal() as db:
        participant = db.scalar(
            select(Participant).where(Participant.email == "alice@example.com")
        )
        token = participant.token

    # Send invitations (console mode -> should mark invited)
    client.post(f"/surveys/{sid}/invite")
    with SessionLocal() as db:
        participant = db.scalar(select(Participant).where(Participant.token == token))
        assert participant.status == ParticipantStatus.invited

    # Respondent loads the survey
    page = client.get(f"/survey/{token}")
    assert page.status_code == 200
    assert "Coffee plan" in page.text

    # Build a submission: pick the first concept of each task
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        form = {}
        for task in survey.tasks:
            first_concept = task.concepts[0]
            form[f"task_{task.id}"] = str(first_concept.id)

    submit = client.post(f"/survey/{token}", data=form)
    assert submit.status_code == 200  # redirected to the done page
    assert "Thank you" in submit.text

    with SessionLocal() as db:
        participant = db.scalar(select(Participant).where(Participant.token == token))
        assert participant.status == ParticipantStatus.completed
        assert len(participant.responses) == 5

    # Results page renders with an analysis
    results = client.get(f"/surveys/{sid}/results")
    assert results.status_code == 200
    assert "Attribute importance" in results.text


def test_incomplete_submission_is_rejected():
    sid = _create_survey_with_design()
    client.post(f"/surveys/{sid}/participants", data={"emails": "bob@example.com"})
    with SessionLocal() as db:
        token = db.scalar(
            select(Participant).where(Participant.email == "bob@example.com")
        ).token

    # Submit nothing -> should be rejected with a prompt to answer all tasks.
    resp = client.post(f"/survey/{token}", data={})
    assert resp.status_code == 400
    assert "make a selection" in resp.text

    with SessionLocal() as db:
        participant = db.scalar(select(Participant).where(Participant.token == token))
        assert participant.status != ParticipantStatus.completed


def test_invalid_token_shows_not_found():
    init_db()
    resp = client.get("/survey/does-not-exist")
    assert resp.status_code == 404
    assert "Link not found" in resp.text
