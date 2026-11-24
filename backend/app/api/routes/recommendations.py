from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import get_recommendation_service
from app.schemas.recommendations import RecommendationRequest, RecommendationRunOut
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationRunOut, status_code=201)
async def create_recommendations(
    body: RecommendationRequest, response: Response,
    svc: RecommendationService = Depends(get_recommendation_service),
):
    """Fetch real GitHub issues for the profile, rank them and return the top `top_k` (default 10)."""
    run = await svc.create(body)
    response.headers["Location"] = f"/api/recommendations/{run.id}"
    return run


@router.get("/{run_id}", response_model=RecommendationRunOut)
def get_recommendations(run_id: int = Path(ge=1), svc: RecommendationService = Depends(get_recommendation_service)):
    return svc.get(run_id)
