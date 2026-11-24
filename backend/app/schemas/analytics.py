from pydantic import BaseModel


class CountItem(BaseModel):
    label: str
    count: int


class Totals(BaseModel):
    profiles: int
    recommendation_runs: int
    recommendations_generated: int
    issues_analyzed: int
    unique_issues_recommended: int
    cached_issues: int


class AverageScores(BaseModel):
    overall: float
    semantic_similarity: float
    skill_compatibility: float
    experience_compatibility: float
    repository_activity: float
    beginner_friendliness: float


class AnalyticsResponse(BaseModel):
    """Everything here is aggregated from the SQLite history; nothing is precomputed or hard-coded."""
    totals: Totals
    average_scores: AverageScores | None
    score_distribution: list[CountItem]               # overall score buckets
    skill_compatibility_distribution: list[CountItem]
    matching_skill_count_distribution: list[CountItem]
    top_matching_skills: list[CountItem]
    requested_domains: list[CountItem]                # domains requested across runs (from profiles)
    recommended_language_distribution: list[CountItem]
    top_labels: list[CountItem]
    experience_level_distribution: list[CountItem]
