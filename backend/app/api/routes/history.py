from fastapi import APIRouter, Depends, Query

from app.api.deps import get_recommendation_service
from app.schemas.recommendations import HistoryResponse
from app.services.recommendation_service import RecommendationService

router = APIRouter(tags=["history"])


@router.get("/history", response_model=HistoryResponse)
def history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            svc: RecommendationService = Depends(get_recommendation_service)):
    """Recommendation runs, newest first."""
    return svc.history(limit, offset)
