from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.session import check_db, ensure_initialized
from app.schemas.health import HealthResponse, LiveResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    """Liveness only: the process is up. Does NOT touch the database, so frequent platform health checks
    do not keep a serverless database awake. Use this for the hosting platform's health check."""
    return LiveResponse(status="ok")


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Readiness: also checks the database (and creates the tables if startup could not)."""
    db_ok = check_db()
    if db_ok:
        try:
            ensure_initialized()
        except Exception:
            db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database="ok" if db_ok else "unavailable",
    )
