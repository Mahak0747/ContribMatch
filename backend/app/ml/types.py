from pydantic import BaseModel, Field

from app.schemas.issues import Issue

Score = Field(ge=0, le=100)


class ScoreBreakdown(BaseModel):
    overall: float = Score
    semantic_similarity: float = Score
    skill_compatibility: float = Score
    experience_compatibility: float = Score
    repository_activity: float = Score
    beginner_friendliness: float = Score


class Recommendation(BaseModel):
    rank: int
    issue: Issue
    scores: ScoreBreakdown
    cosine_similarity: float = Field(description="Raw cosine similarity before 0-100 calibration")
    matching_skills: list[str]
    relevant_labels: list[str]
    explanation: str
    potential_skills_to_learn: list[str]
    difficulty_signals: list[str] = Field(description="Evidence behind the difficulty estimate (may be empty)")
