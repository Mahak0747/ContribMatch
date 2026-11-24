"""ORM models. Importing this package registers every table on Base.metadata."""
from app.models.issue import CachedIssue
from app.models.profile import Profile
from app.models.recommendation import RecommendationItem, RecommendationRun

__all__ = ["CachedIssue", "Profile", "RecommendationItem", "RecommendationRun"]
