from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    learning_interests: Mapped[list] = mapped_column(JSON, default=list)
    experience_level: Mapped[str] = mapped_column(String(20))
    domains: Mapped[list] = mapped_column(JSON, default=list)
    preferred_languages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
