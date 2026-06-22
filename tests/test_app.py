"""End-to-end flow through the web app with the FastAPI TestClient."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.main import app
from app.models import (
    Participant,
    ParticipantStatus,
    RatingMode,
    Survey,
    SurveyStatus,
    SurveyType,
    Task,
)

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


def test_admin_login_flow_when_password_set(monkeypatch):
    init_db()
    monkeypatch.setattr(settings, "admin_user", "boss")
    monkeypatch.setattr(settings, "admin_password", "s3cret")

    c = TestClient(app)  # isolated cookie jar

    # Signed-out admin pages redirect to the login screen.
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")

    # The login screen is public and renders a form.
    login = c.get("/login")
    assert login.status_code == 200
    assert "Sign in" in login.text

    # Wrong credentials are rejected.
    assert c.post("/login", data={"username": "boss", "password": "no"}).status_code == 401

    # Correct credentials establish a session; admin pages then load.
    ok = c.post("/login", data={"username": "boss", "password": "s3cret"},
                follow_redirects=False)
    assert ok.status_code == 303
    assert c.get("/").status_code == 200

    # Logout clears the session and re-protects admin pages.
    c.get("/logout")
    assert c.get("/", follow_redirects=False).status_code == 303

    # Health check and respondent survey routes stay public.
    assert c.get("/healthz").status_code == 200
    assert c.get("/survey/nope").status_code == 404  # not a redirect to login


def test_delete_survey_removes_it_and_cascades(monkeypatch):
    sid = _create_survey_with_design()
    client.post(f"/surveys/{sid}/participants", data={"emails": "zoe@example.com"})

    from app import audit

    messages: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: messages.append(record.getMessage())
    audit.logger.addHandler(handler)
    try:
        r = client.post(f"/surveys/{sid}/delete", follow_redirects=False)
    finally:
        audit.logger.removeHandler(handler)

    # Deleting redirects back to the survey list.
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    # The survey and its dependent rows (tasks, participants) are gone.
    with SessionLocal() as db:
        assert db.get(Survey, sid) is None
        assert db.scalars(select(Task).where(Task.survey_id == sid)).first() is None
        assert (
            db.scalars(select(Participant).where(Participant.survey_id == sid)).first()
            is None
        )

    # The detail page now 404s, and the deletion was audited.
    assert client.get(f"/surveys/{sid}").status_code == 404
    assert any("survey_deleted" in m for m in messages)


def test_refuses_to_start_when_admin_unprotected(monkeypatch):
    # Empty password + no explicit opt-in => fail closed on startup (lifespan
    # runs only when the TestClient is used as a context manager).
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(settings, "allow_insecure_admin", False)
    with pytest.raises(RuntimeError, match="UNPROTECTED"):
        with TestClient(app):
            pass


def test_starts_open_when_insecure_admin_explicitly_allowed(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(settings, "allow_insecure_admin", True)
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200


def test_audit_logs_survey_creation_and_logins(monkeypatch):
    from app import audit

    messages: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: messages.append(record.getMessage())
    audit.logger.addHandler(handler)
    try:
        # Survey creation is recorded (auth disabled here, so the POST goes through).
        init_db()
        client.post("/surveys", data={"name": "Audited survey"})
        assert any(
            "survey_created" in m and "Audited survey" in m for m in messages
        )

        # Both a failed and a successful admin login are recorded.
        monkeypatch.setattr(settings, "admin_user", "boss")
        monkeypatch.setattr(settings, "admin_password", "pw")
        c = TestClient(app)
        c.post("/login", data={"username": "boss", "password": "wrong"})
        c.post("/login", data={"username": "boss", "password": "pw"})
        assert any("admin_login_failed" in m for m in messages)
        assert any("admin_login_success" in m for m in messages)
    finally:
        audit.logger.removeHandler(handler)


def test_effective_base_url_auto_detect():
    from app.config import Settings

    # Explicit BASE_URL wins (and a trailing slash is trimmed).
    s = Settings(base_url="https://custom.example/",
                 render_external_url="https://x.onrender.com")
    assert s.effective_base_url == "https://custom.example"

    # Falls back to RENDER_EXTERNAL_URL when BASE_URL is unset.
    s = Settings(base_url="", render_external_url="https://sunshine-zzrc.onrender.com")
    assert s.effective_base_url == "https://sunshine-zzrc.onrender.com"

    # Localhost default when neither is configured.
    s = Settings(base_url="", render_external_url="")
    assert s.effective_base_url == "http://localhost:8000"


def test_session_cookie_secure_follows_scheme():
    from app.config import Settings

    # HTTPS base URL -> Secure cookie; localhost http -> not Secure.
    assert Settings(base_url="https://x.example").session_cookie_secure is True
    assert Settings(base_url="http://localhost:8000").session_cookie_secure is False
    # Auto-detected from Render's HTTPS URL when BASE_URL is unset.
    assert Settings(
        base_url="", render_external_url="https://a.onrender.com"
    ).session_cookie_secure is True
    # Localhost default (no config) stays http -> not Secure.
    assert Settings(base_url="", render_external_url="").session_cookie_secure is False


def test_van_westendorp_full_flow():
    init_db()
    client.post("/surveys", data={
        "name": "Widget price", "description": "A nice widget.",
        "survey_type": "van_westendorp", "currency": "$",
    })
    with SessionLocal() as db:
        survey = db.scalar(select(Survey).where(Survey.name == "Widget price"))
        sid = survey.id
        # Van Westendorp surveys are active immediately (no design step).
        assert survey.survey_type == SurveyType.van_westendorp
        assert survey.status.value == "active"

    client.post(f"/surveys/{sid}/participants", data={"emails": "carol@example.com"})
    with SessionLocal() as db:
        token = db.scalar(
            select(Participant).where(Participant.email == "carol@example.com")
        ).token

    page = client.get(f"/survey/{token}")
    assert page.status_code == 200
    assert "too expensive" in page.text.lower()

    # Out-of-order prices are rejected.
    bad = client.post(f"/survey/{token}",
                      data={"too_cheap": "20", "cheap": "10",
                            "expensive": "15", "too_expensive": "25"})
    assert bad.status_code == 400

    # Valid increasing prices are accepted.
    ok = client.post(f"/survey/{token}",
                     data={"too_cheap": "5", "cheap": "10",
                           "expensive": "15", "too_expensive": "20"})
    assert ok.status_code == 200
    assert "Thank you" in ok.text

    with SessionLocal() as db:
        p = db.scalar(select(Participant).where(Participant.token == token))
        assert p.status == ParticipantStatus.completed
        assert p.price_perception is not None
        assert p.price_perception.too_expensive == 20.0

    results = client.get(f"/surveys/{sid}/results")
    assert results.status_code == 200
    assert "acceptable prices" in results.text.lower()


def test_rating_rate_flow():
    init_db()
    client.post("/surveys", data={
        "name": "Feature priorities", "description": "Rate these.",
        "survey_type": "rating",
    })
    with SessionLocal() as db:
        survey = db.scalar(select(Survey).where(Survey.name == "Feature priorities"))
        sid = survey.id
        assert survey.survey_type == SurveyType.rating
        assert survey.status == SurveyStatus.draft  # needs items + activation
        assert survey.rating_config is not None

    client.post(f"/surveys/{sid}/settings", data={
        "rating_mode": "rate", "scale_points": "5",
        "min_label": "Low", "max_label": "High", "currency": "$",
    })
    client.post(f"/surveys/{sid}/items", data={"items": "Speed\nPrice\nSupport"})
    client.post(f"/surveys/{sid}/activate")
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        assert survey.status == SurveyStatus.active
        assert len(survey.items) == 3
        item_ids = [it.id for it in survey.items]

    client.post(f"/surveys/{sid}/participants", data={"emails": "ed@example.com"})
    with SessionLocal() as db:
        token = db.scalar(
            select(Participant).where(Participant.email == "ed@example.com")
        ).token

    page = client.get(f"/survey/{token}")
    assert page.status_code == 200
    assert "Rate each item" in page.text

    # An incomplete matrix is rejected.
    bad = client.post(f"/survey/{token}", data={f"item_{item_ids[0]}": "5"})
    assert bad.status_code == 400

    form = {f"item_{iid}": str(v) for iid, v in zip(item_ids, [5, 3, 4])}
    ok = client.post(f"/survey/{token}", data=form)
    assert ok.status_code == 200
    assert "Thank you" in ok.text

    with SessionLocal() as db:
        p = db.scalar(select(Participant).where(Participant.token == token))
        assert p.status == ParticipantStatus.completed
        assert len(p.item_responses) == 3

    results = client.get(f"/surveys/{sid}/results")
    assert results.status_code == 200
    assert "Rating" in results.text


def test_rating_rank_flow():
    init_db()
    client.post("/surveys", data={"name": "Rank colors", "survey_type": "rating"})
    with SessionLocal() as db:
        sid = db.scalar(select(Survey).where(Survey.name == "Rank colors")).id

    client.post(f"/surveys/{sid}/settings",
                data={"rating_mode": "rank", "currency": "$"})
    client.post(f"/surveys/{sid}/items", data={"items": "Red, Green, Blue"})
    client.post(f"/surveys/{sid}/activate")
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        assert survey.rating_config.mode == RatingMode.rank
        item_ids = [it.id for it in survey.items]

    client.post(f"/surveys/{sid}/participants", data={"emails": "fi@example.com"})
    with SessionLocal() as db:
        token = db.scalar(
            select(Participant).where(Participant.email == "fi@example.com")
        ).token

    page = client.get(f"/survey/{token}")
    assert "Rank the items" in page.text

    # Duplicate ranks are rejected.
    dup = client.post(f"/survey/{token}", data={
        f"item_{item_ids[0]}": "1", f"item_{item_ids[1]}": "1",
        f"item_{item_ids[2]}": "2",
    })
    assert dup.status_code == 400

    ok = client.post(f"/survey/{token}", data={
        f"item_{item_ids[0]}": "2", f"item_{item_ids[1]}": "1",
        f"item_{item_ids[2]}": "3",
    })
    assert ok.status_code == 200
    assert "Thank you" in ok.text

    results = client.get(f"/surveys/{sid}/results")
    assert results.status_code == 200
    assert "Ranking" in results.text


def test_maxdiff_full_flow():
    init_db()
    client.post("/surveys", data={"name": "Feature MaxDiff", "survey_type": "maxdiff"})
    with SessionLocal() as db:
        survey = db.scalar(select(Survey).where(Survey.name == "Feature MaxDiff"))
        sid = survey.id
        assert survey.survey_type == SurveyType.maxdiff
        assert survey.maxdiff_config is not None

    client.post(f"/surveys/{sid}/settings",
                data={"items_per_set": "3", "num_sets": "5", "currency": "$"})
    client.post(f"/surveys/{sid}/items",
                data={"items": "Speed\nPrice\nSupport\nDesign\nAnalytics"})
    client.post(f"/surveys/{sid}/generate")
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        assert survey.status == SurveyStatus.active
        assert len(survey.maxdiff_sets) == 5
        assert all(len(s.set_items) == 3 for s in survey.maxdiff_sets)
        # Capture each set's membership for building a valid submission.
        sets = [(s.id, [si.item_id for si in s.set_items]) for s in survey.maxdiff_sets]

    client.post(f"/surveys/{sid}/participants", data={"emails": "gus@example.com"})
    with SessionLocal() as db:
        token = db.scalar(
            select(Participant).where(Participant.email == "gus@example.com")
        ).token

    page = client.get(f"/survey/{token}")
    assert page.status_code == 200
    assert "best" in page.text.lower() and "worst" in page.text.lower()

    # Best == worst in a set is rejected.
    bad_set_id, bad_members = sets[0]
    bad = {f"best_{sid_}": str(mem[0]) for sid_, mem in sets}
    bad.update({f"worst_{sid_}": str(mem[1]) for sid_, mem in sets})
    bad[f"worst_{bad_set_id}"] = str(bad_members[0])  # same as best -> invalid
    assert client.post(f"/survey/{token}", data=bad).status_code == 400

    # Valid picks: first item best, second worst in each set.
    good = {f"best_{sid_}": str(mem[0]) for sid_, mem in sets}
    good.update({f"worst_{sid_}": str(mem[1]) for sid_, mem in sets})
    ok = client.post(f"/survey/{token}", data=good)
    assert ok.status_code == 200
    assert "Thank you" in ok.text

    with SessionLocal() as db:
        p = db.scalar(select(Participant).where(Participant.token == token))
        assert p.status == ParticipantStatus.completed
        assert len(p.maxdiff_responses) == 5

    results = client.get(f"/surveys/{sid}/results")
    assert results.status_code == 200
    assert "MaxDiff results" in results.text


def test_market_simulator():
    sid = _create_survey_with_design()
    client.post(f"/surveys/{sid}/participants", data={"emails": "dave@example.com"})
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        token = survey.participants[0].token
        form = {f"task_{t.id}": str(t.concepts[0].id) for t in survey.tasks}
    client.post(f"/survey/{token}", data=form)

    # Simulator form loads.
    page = client.get(f"/surveys/{sid}/simulator")
    assert page.status_code == 200
    assert "Product 1" in page.text

    # Compute shares for two products.
    with SessionLocal() as db:
        survey = db.get(Survey, sid)
        attrs = [(a.name, [l.value for l in a.levels]) for a in survey.attributes]
    form = {"n_products": "2"}
    for p in range(2):
        for name, levels in attrs:
            form[f"p{p}_{name}"] = levels[0]
    resp = client.post(f"/surveys/{sid}/simulator", data=form)
    assert resp.status_code == 200
    assert "Predicted share" in resp.text
