import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import ensure_initialized
from app.ml.embedder import get_embedder
from app.ml.engine import RecommendationEngine
from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        ensure_initialized()
    except Exception as exc:  # e.g. a sleeping/unreachable cloud database: start anyway, retry per request
        logger.error("Database not ready at startup (%s); the API will retry on the first request that needs it",
                     type(exc).__name__)
    app.state.github = GitHubClient.from_settings(settings)
    logger.info("GitHub client ready (authenticated=%s)", app.state.github.authenticated)
    embedder = get_embedder()
    app.state.engine = RecommendationEngine(embedder)
    if settings.preload_model:
        try:
            await run_in_threadpool(embedder.preload)
            logger.info("Embedding model preloaded")
        except Exception as exc:  # the API still starts; requests will report 503
            logger.error("Could not preload embedding model: %s", exc)
    try:
        yield
    finally:
        await app.state.github.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": settings.app_name, "version": settings.app_version, "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
