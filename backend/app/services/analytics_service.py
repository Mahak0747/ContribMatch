"""Aggregates real analytics from the SQLite history. Nothing is hard-coded or fabricated."""
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CachedIssue, Profile, RecommendationItem, RecommendationRun
from app.schemas.analytics import AnalyticsResponse, AverageScores, CountItem, Totals

BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100.0001)]


def _histogram(values: list[float]) -> list[CountItem]:
    out = []
    for lo, hi in BUCKETS:
        label = f"{lo}-{min(hi, 100):g}"
        out.append(CountItem(label=label, count=sum(1 for v in values if lo <= v < hi)))
    return out


def _top(counter: Counter, n: int = 10) -> list[CountItem]:
    return [CountItem(label=k, count=c) for k, c in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def compute_analytics(db: Session) -> AnalyticsResponse:
    scalar = lambda stmt: db.scalar(stmt) or 0
    totals = Totals(
        profiles=scalar(select(func.count(Profile.id))),
        recommendation_runs=scalar(select(func.count(RecommendationRun.id))),
        recommendations_generated=scalar(select(func.count(RecommendationItem.id))),
        issues_analyzed=scalar(select(func.sum(RecommendationRun.issues_analyzed))),
        unique_issues_recommended=scalar(select(func.count(func.distinct(RecommendationItem.issue_id)))),
        cached_issues=scalar(select(func.count(CachedIssue.id))),
    )

    rows = db.execute(select(
        RecommendationItem.overall, RecommendationItem.skill_compatibility, RecommendationItem.matching_skills,
        RecommendationItem.semantic_similarity, RecommendationItem.experience_compatibility,
        RecommendationItem.repository_activity, RecommendationItem.beginner_friendliness)).all()

    averages = None
    if rows:
        n = len(rows)
        mean = lambda i: round(sum(r[i] for r in rows) / n, 1)
        averages = AverageScores(overall=mean(0), skill_compatibility=mean(1), semantic_similarity=mean(3),
                                 experience_compatibility=mean(4), repository_activity=mean(5),
                                 beginner_friendliness=mean(6))

    match_counts = Counter(min(len(r[2] or []), 3) for r in rows)
    skill_counter: Counter = Counter()
    for r in rows:
        for s in r[2] or []:
            skill_counter[s] += 1

    domains: Counter = Counter()
    levels: Counter = Counter()
    for doms, level in db.execute(select(Profile.domains, Profile.experience_level)
                                  .join(RecommendationRun, RecommendationRun.profile_id == Profile.id)).all():
        levels[level] += 1
        for d in doms or []:
            domains[d.lower()] += 1

    languages: Counter = Counter()
    labels: Counter = Counter()
    for lang, labs in db.execute(select(CachedIssue.repo_language, CachedIssue.labels)
                                 .join(RecommendationItem, RecommendationItem.issue_id == CachedIssue.id)).all():
        languages[lang or "Unknown"] += 1
        for l in labs or []:
            labels[l.lower()] += 1

    return AnalyticsResponse(
        totals=totals, average_scores=averages,
        score_distribution=_histogram([r[0] for r in rows]),
        skill_compatibility_distribution=_histogram([r[1] for r in rows]),
        matching_skill_count_distribution=[
            CountItem(label=lab, count=match_counts.get(k, 0)) for k, lab in ((0, "0"), (1, "1"), (2, "2"), (3, "3+"))],
        top_matching_skills=_top(skill_counter), requested_domains=_top(domains),
        recommended_language_distribution=_top(languages), top_labels=_top(labels),
        experience_level_distribution=_top(levels),
    )
