"""Developer profile used by the recommendation engine."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExperienceLevel = Literal["beginner", "intermediate", "advanced"]

MAX_ITEMS = 30
MAX_ITEM_LEN = 50


def _clean_list(v):
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        raise ValueError("must be a list of strings")
    out: list[str] = []
    seen: set[str] = set()
    for item in v:
        if not isinstance(item, str):
            raise ValueError("every item must be a string")
        item = " ".join(item.replace("\x00", "").split())   # NUL cannot be stored by PostgreSQL
        if not item:
            continue
        if len(item) > MAX_ITEM_LEN:
            raise ValueError(f"items must be at most {MAX_ITEM_LEN} characters")
        if item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    if len(out) > MAX_ITEMS:
        raise ValueError(f"at most {MAX_ITEMS} items are allowed")
    return out


class DeveloperProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[str] = Field(default_factory=list, description="Technical skills the developer has")
    learning_interests: list[str] = Field(default_factory=list, description="Skills the developer wants to learn")
    experience_level: ExperienceLevel = "beginner"
    domains: list[str] = Field(default_factory=list, description="Preferred domains, e.g. 'web development'")
    preferred_languages: list[str] = Field(default_factory=list)

    @field_validator("skills", "learning_interests", "domains", "preferred_languages", mode="before")
    @classmethod
    def _lists(cls, v):
        return _clean_list(v)

    @field_validator("experience_level", mode="before")
    @classmethod
    def _level(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @property
    def is_empty(self) -> bool:
        return not (self.skills or self.learning_interests or self.domains or self.preferred_languages)
