from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow
from app.models.issue import CachedIssue
from app.models.profile import Profile


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    issues_analyzed: Mapped[int] = mapped_column(Integer)
    top_k: Mapped[int] = mapped_column(Integer)
    search_queries: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    stale_data: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str] = mapped_column(String(200))
    weights: Mapped[dict] = mapped_column(JSON, default=dict)

    profile: Mapped[Profile] = relationship(lazy="joined")
    items: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="run", order_by="RecommendationItem.rank", cascade="all, delete-orphan")


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id"), index=True)
    issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cached_issues.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    overall: Mapped[float] = mapped_column(Float)
    semantic_similarity: Mapped[float] = mapped_column(Float)
    skill_compatibility: Mapped[float] = mapped_column(Float)
    experience_compatibility: Mapped[float] = mapped_column(Float)
    repository_activity: Mapped[float] = mapped_column(Float)
    beginner_friendliness: Mapped[float] = mapped_column(Float)
    cosine_similarity: Mapped[float] = mapped_column(Float)
    matching_skills: Mapped[list] = mapped_column(JSON, default=list)
    relevant_labels: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    potential_skills_to_learn: Mapped[list] = mapped_column(JSON, default=list)
    difficulty_signals: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[RecommendationRun] = relationship(back_populates="items")
    issue: Mapped[CachedIssue] = relationship(lazy="joined")
