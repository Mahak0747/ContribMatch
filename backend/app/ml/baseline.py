"""Keyword-matching baseline and a keyword-vs-semantic-vs-hybrid comparison table."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.ml.embedder import Embedder
from app.ml.engine import RecommendationEngine
from app.ml.profile import DeveloperProfile
from app.ml.terms import IssueView, match_strength, unique_canonical
from app.schemas.issues import Issue


def keyword_score(profile: DeveloperProfile, issue: Issue) -> float:
    """Baseline: % of ALL profile terms (skills, languages, domains, interests) literally present
    anywhere in the issue text. No embeddings, no weighting."""
    terms = unique_canonical([*profile.skills, *profile.preferred_languages, *profile.domains, *profile.learning_interests])
    if not terms:
        return 0.0
    v = IssueView.of(issue)
    return 100.0 * sum(1 for c, _ in terms if match_strength(c, v)) / len(terms)


def compare_rankings(profile: DeveloperProfile, issues: list[Issue], embedder: Embedder,
                     now: datetime | None = None) -> pd.DataFrame:
    """Score the SAME issues with keyword, semantic-only and hybrid methods. Ranks use 'min' ties."""
    engine = RecommendationEngine(embedder, now=now or datetime.now(timezone.utc))
    recs = {r.issue.id: r for r in engine.rank(profile, issues, top_k=None)}
    rows = [{
        "issue_id": i.id, "title": i.title,
        "keyword_score": round(keyword_score(profile, i), 1),
        "semantic_score": recs[i.id].scores.semantic_similarity,
        "hybrid_score": recs[i.id].scores.overall,
    } for i in issues if i.id in recs]
    df = pd.DataFrame(rows)
    for col in ("keyword", "semantic", "hybrid"):
        df[f"{col}_rank"] = df[f"{col}_score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("hybrid_rank").reset_index(drop=True)
