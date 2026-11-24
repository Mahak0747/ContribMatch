from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.ml.engine import RecommendationEngine
from app.services.github_client import GitHubClient
from app.services.recommendation_service import RecommendationService


def get_github_client(request: Request) -> GitHubClient:
    return request.app.state.github


def get_engine(request: Request) -> RecommendationEngine:
    return request.app.state.engine


def get_recommendation_service(
    db: Session = Depends(get_db),
    github: GitHubClient = Depends(get_github_client),
    engine: RecommendationEngine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
) -> RecommendationService:
    return RecommendationService(db, github, engine, settings)
