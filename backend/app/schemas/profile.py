from datetime import datetime

from pydantic import BaseModel

from app.ml.profile import DeveloperProfile, ExperienceLevel

# Request body for POST /api/profile is exactly the ML profile model.
ProfileCreate = DeveloperProfile


class ProfileOut(BaseModel):
    id: int
    skills: list[str]
    learning_interests: list[str]
    experience_level: ExperienceLevel
    domains: list[str]
    preferred_languages: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
