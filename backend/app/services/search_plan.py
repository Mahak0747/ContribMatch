"""Turn a developer profile into a small set of GitHub issue searches (pure logic, no I/O)."""
from pydantic import ValidationError

from app.ml.profile import DeveloperProfile
from app.ml.terms import canon
from app.schemas.issues import IssueSearchParams

LEVEL_LABELS = {
    "beginner": ["good first issue", "beginner", "help wanted"],
    "intermediate": ["help wanted", "good first issue"],
    "advanced": ["help wanted"],
}
LANGUAGE_TERMS = frozenset({
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "ruby", "php", "swift",
    "kotlin", "scala", "r", "dart", "haskell", "elixir", "lua", "c",
})


def profile_languages(profile: DeveloperProfile) -> list[str]:
    """Preferred languages first; otherwise programming languages found among the skills."""
    if profile.preferred_languages:
        return profile.preferred_languages
    return [s for s in profile.skills if canon(s) in LANGUAGE_TERMS]


def build_search_plan(profile: DeveloperProfile, labels: list[str] | None = None,
                      per_page: int = 30, max_queries: int = 3) -> list[IssueSearchParams]:
    """Up to `max_queries` distinct searches, most specific first:
      with languages: each of the first two languages (+ the first domain keyword), then one widening query
        without the domain keyword;
      without languages: the first domain keyword, then the first skill as a keyword.
    The experience level picks default labels unless `labels` overrides them. Terms that GitHub-query
    validation rejects (e.g. a language with unusual characters) are skipped, never sent."""
    labs = labels if labels is not None else LEVEL_LABELS[profile.experience_level]
    langs = profile_languages(profile)[:2]
    domain = profile.domains[0] if profile.domains else None
    plans: list[IssueSearchParams] = []
    seen: set = set()

    def add(**kw):
        try:
            p = IssueSearchParams(labels=labs, per_page=per_page, **kw)
        except ValidationError:
            return
        if p.cache_key() not in seen:
            seen.add(p.cache_key())
            plans.append(p)

    if langs:
        for lang in langs:
            add(language=lang, domain=domain)
        if domain:
            add(language=langs[0])                 # widen: drop the domain keyword
    else:
        if domain:
            add(domain=domain)
        if profile.skills:
            add(q=profile.skills[0])               # keyword search on the first skill
    if not plans:                                  # nothing usable: label-only discovery
        add()
    return plans[:max_queries]
