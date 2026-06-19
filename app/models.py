"""ORM models for surveys, conjoint designs, participants, and responses.

The schema is normalized so the analysis layer can faithfully reconstruct the
choice design that each respondent saw:

    Survey ─┬─ Attribute ── Level
            ├─ Task ── Concept ── ConceptLevel ─→ (Attribute, Level)
            └─ Participant ── Response ─→ (Task, chosen Concept)
"""

from __future__ import annotations

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_token() -> str:
    return secrets.token_urlsafe(24)


class SurveyType(str, enum.Enum):
    conjoint = "conjoint"              # Choice-Based Conjoint
    van_westendorp = "van_westendorp"  # Price Sensitivity Meter
    rating = "rating"                  # Ranking / Rating (matrix)


class RatingMode(str, enum.Enum):
    rate = "rate"  # rate each item on a shared scale (matrix grid)
    rank = "rank"  # order the items from best (1) to worst (N)


class SurveyStatus(str, enum.Enum):
    draft = "draft"        # being built; design not generated yet
    active = "active"      # design generated; accepting responses
    closed = "closed"      # no longer accepting responses


class ParticipantStatus(str, enum.Enum):
    pending = "pending"      # added but not yet invited
    invited = "invited"      # invitation email sent
    completed = "completed"  # finished the survey


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    survey_type: Mapped[SurveyType] = mapped_column(
        Enum(SurveyType), default=SurveyType.conjoint, nullable=False
    )
    status: Mapped[SurveyStatus] = mapped_column(
        Enum(SurveyStatus), default=SurveyStatus.draft, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), default="$")

    # Conjoint design parameters
    num_tasks: Mapped[int] = mapped_column(Integer, default=8)
    alternatives_per_task: Mapped[int] = mapped_column(Integer, default=3)
    include_none: Mapped[bool] = mapped_column(Boolean, default=True)
    # Attribute treated as price for willingness-to-pay (optional).
    price_attribute_id: Mapped[int | None] = mapped_column(
        ForeignKey("attributes.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    attributes: Mapped[list["Attribute"]] = relationship(
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="Attribute.position",
        foreign_keys="Attribute.survey_id",
    )
    price_attribute: Mapped["Attribute | None"] = relationship(
        foreign_keys=[price_attribute_id], post_update=True
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="Task.position",
    )
    items: Mapped[list["Item"]] = relationship(
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="Item.position",
    )
    rating_config: Mapped["RatingConfig | None"] = relationship(
        back_populates="survey",
        cascade="all, delete-orphan",
        uselist=False,
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="survey", cascade="all, delete-orphan"
    )


class Attribute(Base):
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    survey: Mapped[Survey] = relationship(
        back_populates="attributes", foreign_keys=[survey_id]
    )
    levels: Mapped[list["Level"]] = relationship(
        back_populates="attribute",
        cascade="all, delete-orphan",
        order_by="Level.position",
    )


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    attribute_id: Mapped[int] = mapped_column(
        ForeignKey("attributes.id", ondelete="CASCADE")
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    attribute: Mapped[Attribute] = relationship(back_populates="levels")


class Task(Base):
    """A single choice task (one screen) presented to a respondent."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    survey: Mapped[Survey] = relationship(back_populates="tasks")
    concepts: Mapped[list["Concept"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="Concept.position",
    )


class Concept(Base):
    """One alternative within a task (a bundle of attribute levels)."""

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_none: Mapped[bool] = mapped_column(Boolean, default=False)

    task: Mapped[Task] = relationship(back_populates="concepts")
    concept_levels: Mapped[list["ConceptLevel"]] = relationship(
        back_populates="concept", cascade="all, delete-orphan"
    )

    def as_dict(self) -> dict[str, str]:
        """Map attribute name -> chosen level value for this concept."""
        return {
            cl.attribute.name: cl.level.value for cl in self.concept_levels
        }


class ConceptLevel(Base):
    __tablename__ = "concept_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE")
    )
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"))
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id"))

    concept: Mapped[Concept] = relationship(back_populates="concept_levels")
    attribute: Mapped[Attribute] = relationship()
    level: Mapped[Level] = relationship()


class RatingConfig(Base):
    """Per-survey settings for a Ranking / Rating survey (kept off the surveys
    table so the schema stays additive — new table only — for existing DBs)."""

    __tablename__ = "rating_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), unique=True
    )
    mode: Mapped[RatingMode] = mapped_column(
        Enum(RatingMode), default=RatingMode.rate, nullable=False
    )
    scale_points: Mapped[int] = mapped_column(Integer, default=5)
    min_label: Mapped[str] = mapped_column(String(80), default="")
    max_label: Mapped[str] = mapped_column(String(80), default="")

    survey: Mapped[Survey] = relationship(back_populates="rating_config")


class Item(Base):
    """A statement/option respondents rate or rank in a Ranking/Rating survey."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    survey: Mapped[Survey] = relationship(back_populates="items")
    responses: Mapped[list["ItemResponse"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ItemResponse(Base):
    """One respondent's rating (scale value) or rank for a single item."""

    __tablename__ = "item_responses"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "item_id", name="uq_item_response_participant_item"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    participant: Mapped["Participant"] = relationship(back_populates="item_responses")
    item: Mapped[Item] = relationship(back_populates="responses")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("survey_id", "email", name="uq_participant_survey_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), default=_new_token, unique=True, index=True
    )
    status: Mapped[ParticipantStatus] = mapped_column(
        Enum(ParticipantStatus), default=ParticipantStatus.pending, nullable=False
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    survey: Mapped[Survey] = relationship(back_populates="participants")
    responses: Mapped[list["Response"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
    item_responses: Mapped[list["ItemResponse"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
    price_perception: Mapped["PricePerception | None"] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "task_id", name="uq_response_participant_task"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    chosen_concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    participant: Mapped[Participant] = relationship(back_populates="responses")
    task: Mapped[Task] = relationship()
    chosen_concept: Mapped[Concept] = relationship()


class PricePerception(Base):
    """A respondent's four Van Westendorp price points (in survey currency)."""

    __tablename__ = "price_perceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), unique=True
    )
    too_cheap: Mapped[float] = mapped_column(Float, nullable=False)
    cheap: Mapped[float] = mapped_column(Float, nullable=False)
    expensive: Mapped[float] = mapped_column(Float, nullable=False)
    too_expensive: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    participant: Mapped[Participant] = relationship(
        back_populates="price_perception"
    )
