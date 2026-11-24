from fastapi import APIRouter

from app.api.routes import analytics, health, history, issues, profile, recommendations

api_router = APIRouter(prefix="/api")
for r in (health, issues, profile, recommendations, history, analytics):
    api_router.include_router(r.router)
