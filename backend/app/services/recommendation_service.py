"""Orchestrates: profile -> GitHub discovery -> ML ranking -> explanations -> SQLite.

Routes only call this class; the ML package knows nothing about HTTP or the database.
"""
from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.types import utcnow
from app.core.exceptions import (
    AppError, BadRequestError, ExternalServiceError, GatewayTimeoutError, NotFoundError,
    RateLimitError, ServiceUnavailableError, UnprocessableError,
)
from app.ml.embedder import EmbeddingModelError
from app.ml.engine import InvalidProfileError, RecommendationEngine
from app.ml.profile import DeveloperProfile
from app.ml.types import Recommendation, ScoreBreakdown
from app.models import CachedIssue, Profile, RecommendationItem, RecommendationRun
from app.schemas.issues import Issue
from app.schemas.recommendations import HistoryEntry, HistoryResponse, RecommendationRequest, RecommendationRunOut
from app.services import profile_service
from app.services.github_client import GitHubClient
from app.services.search_plan import build_search_plan

logger = logging.getLogger(__name__)

_UPSTREAM_ERRORS = (RateLimitError, ServiceUnavailableError, GatewayTimeoutError, ExternalServiceError)


def history_statement(limit: int, offset: int):
    """Runs with their recommendation count and best score, newest first.

    The per-run aggregates come from a subquery that is joined in. The outer query has no GROUP BY because
    the ORM also eager-loads each run's profile: PostgreSQL rejects a GROUP BY that leaves those joined
    profile columns ungrouped (SQLite silently allows it), so aggregating in the outer query is not portable.
    """
    agg = (select(RecommendationItem.run_id.label("run_id"),
                  func.count(RecommendationItem.id).label("n"),
                  func.max(RecommendationItem.overall).label("top"))
           .group_by(RecommendationItem.run_id).subquery())
    return (select(RecommendationRun, agg.c.n, agg.c.top)
            .outerjoin(agg, agg.c.run_id == RecommendationRun.id)
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .limit(limit).offset(offset))


class RecommendationService:
    def __init__(self, db: Session, github: GitHubClient, engine: RecommendationEngine, settings: Settings):
        self.db, self.github, self.engine, self.settings = db, github, engine, settings

    # ------------------------------------------------------------------ create
    async def create(self, req: RecommendationRequest) -> RecommendationRunOut:
        row, profile = await run_in_threadpool(self._resolve_profile, req)
        plans = build_search_plan(profile, req.labels, self.settings.candidates_per_query, self.settings.max_search_queries)

        issues, queries, warnings, stale = await self._discover(plans)
        run = await run_in_threadpool(self._rank_and_store, row, profile, issues, req.top_k, queries, warnings, stale)
        return self._run_out(run)

    def _resolve_profile(self, req: RecommendationRequest) -> tuple[Profile, DeveloperProfile]:
        if req.profile_id is not None:
            row = profile_service.get_profile(self.db, req.profile_id)
            return row, profile_service.to_ml_profile(row)
        row, _ = profile_service.create_or_get_profile(self.db, req.profile)
        return row, req.profile

    async def _discover(self, plans) -> tuple[list[Issue], list[str], list[str], bool]:
        """Run the planned searches sequentially (kind to GitHub's search limit). A failure only aborts the
        request if nothing at all could be fetched; otherwise the request continues with a warning."""
        merged: dict[int, Issue] = {}
        queries, warnings, stale = [], [], False
        first_error: AppError | None = None
        for plan in plans:
            try:
                resp = await self.github.search_issues(plan)
            except _UPSTREAM_ERRORS as exc:
                first_error = first_error or exc
                warnings.append(f"A GitHub search failed: {exc.message}")
                if isinstance(exc, RateLimitError):
                    break                        # do not hammer a rate-limited API
                continue
            except BadRequestError as exc:
                warnings.append(f"A GitHub search was rejected: {exc.message}")
                continue
            queries.append(resp.query)
            warnings.extend(w for w in resp.warnings if w not in warnings)
            stale = stale or resp.stale
            for issue in resp.issues:
                merged.setdefault(issue.id, issue)
        if not merged and first_error is not None:
            raise first_error
        if not merged:
            warnings.append("No open GitHub issues matched the search; try broader skills, languages or labels.")
        return list(merged.values()), queries, warnings, stale

    def _rank_and_store(self, row: Profile, profile: DeveloperProfile, issues: list[Issue], top_k: int,
                        queries: list[str], warnings: list[str], stale: bool) -> RecommendationRun:
        try:
            recs = self.engine.rank(profile, issues, top_k=top_k)
        except InvalidProfileError as exc:
            raise UnprocessableError(str(exc)) from exc
        except EmbeddingModelError as exc:
            logger.error("Embedding model unavailable: %s", exc)
            raise ServiceUnavailableError(
                "The recommendation model is unavailable. The embedding model must be downloaded on first "
                "use, which needs internet access.") from exc
        # Two requests can analyse the same GitHub issue at once. With several connections (PostgreSQL) the
        # loser of that race hits a unique-key error on cached_issues; one retry sees the winner's row and
        # updates it instead.
        for attempt in (1, 2):
            try:
                for i in issues:                             # cache every analysed issue (latest copy wins)
                    self.db.merge(CachedIssue(**i.model_dump(), fetched_at=utcnow()))
                run = RecommendationRun(
                    profile_id=row.id, issues_analyzed=len(issues), top_k=top_k, search_queries=queries,
                    warnings=warnings, stale_data=stale, model_name=self.engine.embedder.model_name,
                    weights=dict(self.engine.weights))
                run.items = [RecommendationItem(
                    issue_id=r.issue.id, rank=r.rank, overall=r.scores.overall,
                    semantic_similarity=r.scores.semantic_similarity, skill_compatibility=r.scores.skill_compatibility,
                    experience_compatibility=r.scores.experience_compatibility,
                    repository_activity=r.scores.repository_activity, beginner_friendliness=r.scores.beginner_friendliness,
                    cosine_similarity=r.cosine_similarity, matching_skills=r.matching_skills,
                    relevant_labels=r.relevant_labels, explanation=r.explanation,
                    potential_skills_to_learn=r.potential_skills_to_learn, difficulty_signals=r.difficulty_signals,
                ) for r in recs]
                self.db.add(run)
                self.db.commit()
                break
            except IntegrityError:
                self.db.rollback()
                if attempt == 2:
                    raise
                logger.warning("Concurrent insert while caching issues; retrying once")
            except Exception:
                self.db.rollback()
                raise
        self.db.refresh(run)
        return self._load_run(run.id)

    # -------------------------------------------------------------------- read
    def _load_run(self, run_id: int) -> RecommendationRun:
        run = self.db.get(RecommendationRun, run_id)
        if run is None:
            raise NotFoundError(f"Recommendation {run_id} not found")
        return run

    def get(self, run_id: int) -> RecommendationRunOut:
        return self._run_out(self._load_run(run_id))

    @staticmethod
    def _run_out(run: RecommendationRun) -> RecommendationRunOut:
        recs = [Recommendation(
            rank=it.rank, issue=Issue.model_validate(it.issue, from_attributes=True),
            scores=ScoreBreakdown(
                overall=it.overall, semantic_similarity=it.semantic_similarity,
                skill_compatibility=it.skill_compatibility, experience_compatibility=it.experience_compatibility,
                repository_activity=it.repository_activity, beginner_friendliness=it.beginner_friendliness),
            cosine_similarity=it.cosine_similarity, matching_skills=it.matching_skills,
            relevant_labels=it.relevant_labels, explanation=it.explanation,
            potential_skills_to_learn=it.potential_skills_to_learn, difficulty_signals=it.difficulty_signals,
        ) for it in run.items]
        return RecommendationRunOut(
            id=run.id, profile_id=run.profile_id, created_at=run.created_at, issues_analyzed=run.issues_analyzed,
            top_k=run.top_k, model=run.model_name, weights=run.weights, search_queries=run.search_queries,
            warnings=run.warnings, stale_data=run.stale_data, recommendations=recs)

    def history(self, limit: int, offset: int) -> HistoryResponse:
        total = self.db.scalar(select(func.count(RecommendationRun.id))) or 0
        items = [HistoryEntry(
            id=run.id, profile_id=run.profile_id, created_at=run.created_at,
            experience_level=run.profile.experience_level, skills=run.profile.skills, domains=run.profile.domains,
            issues_analyzed=run.issues_analyzed, recommendation_count=count or 0, top_score=top)
            for run, count, top in self.db.execute(history_statement(limit, offset)).unique().all()]
        return HistoryResponse(total=total, limit=limit, offset=offset, items=items)
