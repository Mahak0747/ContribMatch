"""Hybrid recommendation engine: pretrained embeddings + our own weighted scoring."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from app.ml.embedder import Embedder
from app.ml.explain import build_explanation, domain_hits, potential_skills, relevant_labels
from app.ml.profile import DeveloperProfile
from app.ml.scoring import WEIGHTS, final_score, score_issue
from app.ml.terms import IssueView
from app.ml.text_builder import issue_text, profile_text
from app.ml.types import Recommendation, ScoreBreakdown
from app.schemas.issues import Issue


class InvalidProfileError(ValueError):
    """Profile has no skills, languages, domains or learning interests to match on."""


class RecommendationEngine:
    def __init__(self, embedder: Embedder, weights: dict[str, float] | None = None, now: datetime | None = None):
        self.embedder = embedder
        self.weights = weights or WEIGHTS
        if set(self.weights) != set(WEIGHTS) or abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("weights must have the five component keys and sum to 1")
        self._now = now

    def _prepare(self, profile, issues):
        if not isinstance(profile, DeveloperProfile):
            profile = DeveloperProfile.model_validate(profile)   # raises pydantic ValidationError
        if profile.is_empty:
            raise InvalidProfileError("Profile needs at least one skill, language, domain or learning interest")
        seen, unique = set(), []
        for i in issues:
            if i.id not in seen:
                seen.add(i.id)
                unique.append(i)
        return profile, unique

    def cosine_similarities(self, profile: DeveloperProfile, issues: list[Issue]) -> list[float]:
        """One batched embedding call for the profile and all issues, then cosine similarity."""
        if not issues:
            return []
        vecs = self.embedder.embed([profile_text(profile), *[issue_text(i) for i in issues]])
        return [float(x) for x in cosine_similarity(vecs[:1], vecs[1:])[0]]

    def rank(self, profile: DeveloperProfile | dict, issues: list[Issue], top_k: int | None = 10) -> list[Recommendation]:
        if top_k is not None and not (1 <= top_k <= 100):
            raise ValueError("top_k must be between 1 and 100")
        profile, issues = self._prepare(profile, issues)
        if not issues:
            return []
        now = self._now or datetime.now(timezone.utc)
        cosines = self.cosine_similarities(profile, issues)
        views = [IssueView.of(i) for i in issues]
        comps = [score_issue(profile, i, c, now, v) for i, c, v in zip(issues, cosines, views)]
        overall = [final_score(c, self.weights) for c in comps]

        table = pd.DataFrame({
            "idx": range(len(issues)), "overall": overall,
            "updated": [i.updated_at for i in issues], "id": [i.id for i in issues],
        }).sort_values(["overall", "updated", "id"], ascending=[False, False, True], kind="mergesort")
        order = table["idx"].tolist()[:top_k]

        out = []
        for rank, idx in enumerate(order, start=1):
            i, c, v = issues[idx], comps[idx], views[idx]
            learn, new = potential_skills(profile, v)
            domains = domain_hits(profile, v)
            out.append(Recommendation(
                rank=rank, issue=i,
                scores=ScoreBreakdown(
                    overall=round(overall[idx], 1), semantic_similarity=round(c.semantic, 1),
                    skill_compatibility=round(c.skill, 1), experience_compatibility=round(c.experience, 1),
                    repository_activity=round(c.activity, 1), beginner_friendliness=round(c.beginner, 1)),
                cosine_similarity=round(cosines[idx], 4),
                matching_skills=c.matched_skills,
                relevant_labels=relevant_labels(profile, i, v),
                explanation=build_explanation(profile, i, v, c, learn, domains, now),
                potential_skills_to_learn=[*learn, *new][:5],
                difficulty_signals=c.difficulty_signals,
            ))
        return out
