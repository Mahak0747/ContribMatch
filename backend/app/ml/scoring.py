"""The five score components (each 0-100) and the weighted final score.

IMPORTANT: this is OUR hand-designed ranking algorithm. The weights, thresholds and heuristics below are
initial design choices, NOT learned parameters. Only the embedding model is a pretrained neural model.

GitHub does not provide "difficulty" or "suitable experience level". Experience compatibility and
beginner friendliness are therefore ESTIMATES from observable evidence (labels, description length,
comment count) and are reported together with that evidence.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ml.profile import DeveloperProfile
from app.ml.terms import IssueView, match_strength, unique_canonical
from app.schemas.issues import Issue

WEIGHTS: dict[str, float] = {
    "semantic": 0.45, "skill": 0.20, "experience": 0.15, "activity": 0.10, "beginner": 0.10,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# Cosine -> 0..100 calibration (design constants, not fitted): cosine <= LOW maps to 0, >= HIGH maps to 100.
# Typical MiniLM cosine for unrelated short texts is near 0-0.1 and for clearly related texts 0.4-0.7.
COSINE_LOW, COSINE_HIGH = 0.10, 0.60

ACTIVITY_HALF_LIFE_DAYS = 45.0
TARGET_DIFFICULTY = {"beginner": 0.2, "intermediate": 0.5, "advanced": 0.8}

_BEGINNER_RE = re.compile(
    r"\b(good first|beginner|beginners|easy|starter|newcomer|newcomers|newbie|first timers?|"
    r"first contribution|low hanging fruit|up for grabs)\b")
_ADVANCED_RE = re.compile(r"\b(advanced|expert|hard|difficult|complex)\b")
_HELP_RE = re.compile(r"\bhelp wanted\b")


def _norm_label(l: str) -> str:
    return re.sub(r"[-_:]+", " ", l.lower()).strip()


def beginner_labels(labels: list[str]) -> list[str]:
    return [l for l in labels if _BEGINNER_RE.search(_norm_label(l))]


def advanced_labels(labels: list[str]) -> list[str]:
    return [l for l in labels if _ADVANCED_RE.search(_norm_label(l))]


def help_wanted_labels(labels: list[str]) -> list[str]:
    return [l for l in labels if _HELP_RE.search(_norm_label(l))]


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# 1. Semantic similarity ------------------------------------------------------------------------
def semantic_score(cosine: float) -> float:
    """Map cosine similarity to 0-100 with a fixed linear calibration."""
    if math.isnan(cosine):
        return 0.0
    return _clip((cosine - COSINE_LOW) / (COSINE_HIGH - COSINE_LOW) * 100.0)


# 2. Skill compatibility ------------------------------------------------------------------------
def skill_compatibility(profile: DeveloperProfile, v: IssueView) -> tuple[float, list[str]]:
    """How well the issue text mentions the developer's skills and preferred languages.

    Terms = skills + preferred languages (de-duplicated, alias-normalised). A term found in the title,
    labels or repository language counts 1.0; found only in the description / repository description
    counts 0.6. Score = 100 * min(1, sum / min(#terms, 3)) so that listing many skills is not penalised
    (an issue rarely mentions more than a few). Returns (score, matched display names).
    """
    terms = unique_canonical([*profile.skills, *profile.preferred_languages])
    if not terms:
        return 0.0, []
    total, matched = 0.0, []
    for c, display in terms:
        s = match_strength(c, v)
        if s:
            total += 1.0 if s == "strong" else 0.6
            matched.append((0 if s == "strong" else 1, display))
    matched.sort(key=lambda x: x[0])
    return _clip(100.0 * min(1.0, total / min(len(terms), 3))), [d for _, d in matched]


# 3. Experience compatibility -------------------------------------------------------------------
def estimate_difficulty(issue: Issue) -> tuple[float, list[str]]:
    """Estimated difficulty in [0.05, 0.95] (0.5 = unknown) plus the evidence used."""
    d, ev = 0.5, []
    beg, adv = beginner_labels(issue.labels), advanced_labels(issue.labels)
    if beg and not adv:
        d = 0.2
        ev.append(f"label '{beg[0]}' (beginner signal)")
    elif adv and not beg:
        d = 0.85
        ev.append(f"label '{adv[0]}' (higher-difficulty signal)")
    elif beg and adv:
        ev.append("conflicting difficulty labels")
    body = (issue.body or "").strip()
    if len(body) >= 1500:
        d += 0.10
        ev.append("long description")
    elif not body:
        d += 0.05
        ev.append("no description (scope unclear)")
    if issue.comments >= 10:
        d += 0.10
        ev.append(f"{issue.comments} comments (long discussion)")
    elif issue.comments >= 5:
        d += 0.05
        ev.append(f"{issue.comments} comments")
    return _clip(d, 0.05, 0.95), ev


def experience_compatibility(level: str, difficulty: float, has_evidence: bool) -> float:
    """100 when estimated difficulty equals the developer's target level; falls off linearly.
    Too hard is penalised more than too easy. With no difficulty evidence the score is a neutral 50."""
    if not has_evidence:
        return 50.0
    diff = difficulty - TARGET_DIFFICULTY[level]
    penalty = diff / 0.6 if diff > 0 else abs(diff) / 0.9
    return _clip(100.0 * (1.0 - min(1.0, penalty)))


# 4. Repository activity ------------------------------------------------------------------------
def _recency(dt: datetime, now: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return 100.0 * 0.5 ** (age_days / ACTIVITY_HALF_LIFE_DAYS)


def repository_activity(issue: Issue, now: datetime) -> float:
    """Weighted mean of: repo last push recency (0.50), issue last update recency (0.35) and
    repository stars on a log scale, 10k stars = 100 (0.15). Components that GitHub did not
    return are left out and the remaining weights renormalised."""
    parts: list[tuple[float, float]] = []
    if issue.repo_pushed_at is not None:
        parts.append((0.50, _recency(issue.repo_pushed_at, now)))
    parts.append((0.35, _recency(issue.updated_at, now)))
    if issue.repo_stars is not None:
        parts.append((0.15, _clip(100.0 * math.log10(max(issue.repo_stars, 0) + 1) / 4.0)))
    wsum = sum(w for w, _ in parts)
    return _clip(sum(w * s for w, s in parts) / wsum)


# 5. Beginner friendliness ----------------------------------------------------------------------
def beginner_friendliness(issue: Issue) -> tuple[float, list[str]]:
    """Independent of the developer: base 30, +45 beginner label, +10 'help wanted', +10 description of
    at least 200 chars, -10 empty description, -10 for >=10 comments, -25 higher-difficulty label."""
    s, ev = 30.0, []
    beg, adv, hw = beginner_labels(issue.labels), advanced_labels(issue.labels), help_wanted_labels(issue.labels)
    if beg:
        s += 45
        ev.append(f"label '{beg[0]}'")
    if hw:
        s += 10
        ev.append(f"label '{hw[0]}'")
    body = (issue.body or "").strip()
    if len(body) >= 200:
        s += 10
        ev.append("has a substantive description")
    elif not body:
        s -= 10
        ev.append("no description")
    if issue.comments >= 10:
        s -= 10
        ev.append("long discussion")
    if adv:
        s -= 25
        ev.append(f"label '{adv[0]}' (higher difficulty)")
    return _clip(s), ev


# Final -------------------------------------------------------------------------------------------
@dataclass
class Components:
    semantic: float
    skill: float
    experience: float
    activity: float
    beginner: float
    matched_skills: list[str] = field(default_factory=list)
    difficulty: float = 0.5
    difficulty_signals: list[str] = field(default_factory=list)
    beginner_signals: list[str] = field(default_factory=list)


def final_score(c: Components, weights: dict[str, float] = WEIGHTS) -> float:
    return _clip(sum(weights[k] * getattr(c, k) for k in weights))


def score_issue(profile: DeveloperProfile, issue: Issue, cosine: float, now: datetime,
                view: IssueView | None = None) -> Components:
    v = view or IssueView.of(issue)
    skill, matched = skill_compatibility(profile, v)
    diff, diff_ev = estimate_difficulty(issue)
    beg, beg_ev = beginner_friendliness(issue)
    return Components(
        semantic=semantic_score(cosine), skill=skill,
        experience=experience_compatibility(profile.experience_level, diff, bool(diff_ev)),
        activity=repository_activity(issue, now), beginner=beg,
        matched_skills=matched, difficulty=diff, difficulty_signals=diff_ev, beginner_signals=beg_ev,
    )
