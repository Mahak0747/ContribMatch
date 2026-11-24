from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.ml.profile import DeveloperProfile
from app.ml.types import Recommendation
from app.schemas.issues import IssueSearchParams


class RecommendationRequest(BaseModel):
    """Provide EITHER `profile_id` (saved via POST /api/profile) OR an inline `profile`."""
    profile_id: int | None = Field(None, ge=1)
    profile: DeveloperProfile | None = None
    top_k: int = Field(10, ge=1, le=20, description="Number of recommendations to return (default 10)")
    labels: list[str] | None = Field(None, description="Override the issue labels used for discovery")

    @field_validator("labels")
    @classmethod
    def _labels(cls, v):
        return IssueSearchParams(labels=v).labels if v is not None else None

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.profile_id is None) == (self.profile is None):
            raise ValueError("provide exactly one of 'profile_id' or 'profile'")
        return self


class RecommendationRunOut(BaseModel):
    id: int
    profile_id: int
    created_at: datetime
    issues_analyzed: int = Field(description="Distinct GitHub issues scored for this run")
    top_k: int
    model: str = Field(description="Pretrained embedding model used")
    weights: dict[str, float]
    search_queries: list[str] = Field(description="GitHub search queries that were executed")
    warnings: list[str]
    stale_data: bool = Field(description="True if some GitHub data came from an expired cache")
    recommendations: list[Recommendation]


class HistoryEntry(BaseModel):
    id: int
    profile_id: int
    created_at: datetime
    experience_level: str
    skills: list[str]
    domains: list[str]
    issues_analyzed: int
    recommendation_count: int
    top_score: float | None


class HistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[HistoryEntry]
