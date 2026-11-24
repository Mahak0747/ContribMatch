from datetime import datetime

from sqlalchemy import JSON, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class CachedIssue(Base):
    """Latest known copy of a GitHub issue (primary key = GitHub's issue id). Column names match
    `app.schemas.issues.Issue` so it can be validated straight from the ORM object."""
    __tablename__ = "cached_issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(20))
    labels: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    repo_full_name: Mapped[str] = mapped_column(String(300), index=True)
    repo_url: Mapped[str] = mapped_column(String(500))
    repo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_language: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    repo_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repo_pushed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
