from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import compute_analytics

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(db: Session = Depends(get_db)):
    return compute_analytics(db)
