"""Explanations built ONLY from features that were actually detected for this issue/profile."""
from __future__ import annotations

from datetime import datetime, timezone

from app.ml.profile import DeveloperProfile
from app.ml.scoring import Components, advanced_labels, beginner_labels, help_wanted_labels
from app.ml.terms import IssueView, canon, find_vocab_terms, match_strength, unique_canonical
from app.schemas.issues import Issue

MAX_LEARN = 5


def _days_ago(dt: datetime, now: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - dt).total_seconds() // 86400))


def relevant_labels(profile: DeveloperProfile, issue: Issue, v: IssueView) -> list[str]:
    """Labels that match a profile term, or are contribution-friendliness signals."""
    terms = unique_canonical([*profile.skills, *profile.preferred_languages, *profile.domains, *profile.learning_interests])
    out = []
    for lab in issue.labels:
        single = IssueView(title="", labels=[lab], labels_text=lab.lower().replace("-", " ").replace("_", " "),
                           body="", repo_desc="", repo_lang="")
        is_signal = lab in beginner_labels([lab]) or lab in help_wanted_labels([lab]) or lab in advanced_labels([lab])
        if is_signal or any(match_strength(c, single) for c, _ in terms):
            out.append(lab)
    return out


def potential_skills(profile: DeveloperProfile, v: IssueView) -> tuple[list[str], list[str]]:
    """(learning interests found in the issue, other known technologies mentioned that the developer
    did not list). Both are literally present in the issue/repository text."""
    learn = [d for c, d in unique_canonical(profile.learning_interests) if match_strength(c, v)]
    # things the developer already lists (skills, languages, preferred domains) are not "new" skills
    known = {c for c, _ in unique_canonical([*profile.skills, *profile.preferred_languages, *profile.domains])}
    learn_canon = {canon(x) for x in learn}
    new = [t for t in find_vocab_terms(v) if t not in known and t not in learn_canon]
    return learn, new


def domain_hits(profile: DeveloperProfile, v: IssueView) -> list[str]:
    return [d for c, d in unique_canonical(profile.domains) if match_strength(c, v)]


def build_explanation(profile: DeveloperProfile, issue: Issue, v: IssueView, c: Components,
                      learn: list[str], domains: list[str], now: datetime) -> str:
    parts: list[str] = []
    lang_pref = [x for x in profile.preferred_languages if issue.repo_language and canon(x) == canon(issue.repo_language)]

    if not (c.matched_skills or domains or lang_pref or learn):
        parts.append("No explicit overlap with your listed skills, domains or interests was found in this issue; "
                     "the match relies on semantic similarity.")
    if c.matched_skills:
        parts.append(f"Mentions your skills: {', '.join(c.matched_skills)}.")
    if lang_pref:
        parts.append(f"The repository's main language is {issue.repo_language}, one of your preferred languages.")
    if domains:
        parts.append(f"Relates to your preferred domain: {', '.join(domains)}.")
    if learn:
        parts.append(f"Touches topics you want to learn: {', '.join(learn)}.")

    beg, adv = beginner_labels(issue.labels), advanced_labels(issue.labels)
    if beg and not adv:
        fit = f", which fits your {profile.experience_level} level" if profile.experience_level == "beginner" else ""
        parts.append(f"Labelled '{beg[0]}', a beginner-friendly signal{fit}.")
    elif adv and not beg:
        parts.append(f"Labelled '{adv[0]}', which suggests higher difficulty.")

    if issue.repo_pushed_at is not None:
        parts.append(f"The repository was last pushed to {_days_ago(issue.repo_pushed_at, now)} day(s) ago; "
                     f"the issue was updated {_days_ago(issue.updated_at, now)} day(s) ago.")
    else:
        parts.append(f"The issue was last updated {_days_ago(issue.updated_at, now)} day(s) ago.")

    level = "strong" if c.semantic >= 70 else "moderate" if c.semantic >= 40 else "weak"
    parts.append(f"Semantic similarity to your profile: {c.semantic:.0f}/100 ({level}).")
    return " ".join(parts)
