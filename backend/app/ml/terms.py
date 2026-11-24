"""Term normalisation and matching shared by scoring, explanations and the keyword baseline.

Matching is whole-word and case-insensitive ("java" does not match "javascript"; "c++" works).
Very ambiguous names ("go", "r", "c") are only matched through the repository's primary language
(or an unambiguous alias such as "golang"), because they are common English words/letters.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from app.schemas.issues import Issue

ALIASES: dict[str, str] = {
    "js": "javascript", "ts": "typescript", "py": "python", "nodejs": "node.js",
    "reactjs": "react", "react.js": "react", "vuejs": "vue", "vue.js": "vue",
    "golang": "go", "ml": "machine learning", "k8s": "kubernetes", "postgres": "postgresql",
    "cpp": "c++", "csharp": "c#", "sklearn": "scikit-learn", "scikit learn": "scikit-learn",
    "nextjs": "next.js", "expressjs": "express", "tailwindcss": "tailwind", "tailwind css": "tailwind",
    "natural language processing": "nlp", "large language model": "llm", "large language models": "llm",
    "github action": "github actions",
}
AMBIGUOUS = frozenset({"go", "r", "c"})

_REVERSE: dict[str, list[str]] = defaultdict(list)
for _alias, _canon in ALIASES.items():
    _REVERSE[_canon].append(_alias)

# Technologies we can detect in issue text (used only for "skills you could learn": something is
# listed only if it is literally mentioned in the issue/labels/repository description/language).
TECH_VOCAB = frozenset({
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "ruby", "php", "swift",
    "kotlin", "scala", "r", "dart", "haskell", "elixir", "lua", "shell", "bash",
    "react", "vue", "angular", "svelte", "next.js", "node.js", "express", "django", "flask", "fastapi",
    "spring", "rails", "laravel", "tailwind", "flutter",
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "machine learning", "deep learning",
    "nlp", "computer vision", "transformers", "llm", "opencv", "jupyter",
    "docker", "kubernetes", "terraform", "aws", "azure", "gcp", "linux", "nginx", "github actions",
    "ci/cd", "ansible",
    "sql", "postgresql", "mysql", "sqlite", "mongodb", "redis", "graphql", "grpc", "rest api",
    "webassembly", "websocket", "oauth", "jwt",
    "pytest", "jest", "accessibility", "cli",
})


def canon(term: str) -> str:
    t = re.sub(r"\s+", " ", term.strip().lower())
    return ALIASES.get(t, t)


@lru_cache(maxsize=4096)
def _pattern(term: str) -> re.Pattern | None:
    variants = [term, *_REVERSE.get(term, [])]
    if term in AMBIGUOUS:
        variants = [v for v in variants if v != term]
    if not variants:
        return None
    alt = "|".join(re.escape(v) for v in sorted(set(variants), key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9+#])(?:{alt})(?![a-z0-9+#])")


@dataclass(frozen=True)
class IssueView:
    """Lower-cased, pre-joined text fields of an issue for matching."""
    title: str
    labels: list[str]          # original label names
    labels_text: str
    body: str
    repo_desc: str
    repo_lang: str

    @classmethod
    def of(cls, issue: Issue) -> "IssueView":
        return cls(
            title=(issue.title or "").lower(),
            labels=list(issue.labels or []),
            labels_text=" | ".join(re.sub(r"[-_]", " ", l.lower()) for l in (issue.labels or [])),
            body=(issue.body or "").lower(),
            repo_desc=(issue.repo_description or "").lower(),
            repo_lang=(issue.repo_language or "").strip().lower(),
        )


def match_strength(term: str, v: IssueView) -> str | None:
    """'strong' = in title, labels or repository language; 'weak' = only in description/repo
    description; None = not found. `term` must already be canonical."""
    if v.repo_lang and canon(v.repo_lang) == term:
        return "strong"
    pat = _pattern(term)
    if pat is None:
        return None
    if pat.search(v.title) or pat.search(v.labels_text):
        return "strong"
    if pat.search(v.body) or pat.search(v.repo_desc):
        return "weak"
    return None


def find_vocab_terms(v: IssueView) -> list[str]:
    """Known technologies literally mentioned by the issue (strong matches first, then A-Z)."""
    hits = [(0 if s == "strong" else 1, t) for t in TECH_VOCAB if (s := match_strength(t, v))]
    return [t for _, t in sorted(hits)]


def unique_canonical(items: list[str]) -> list[tuple[str, str]]:
    """[(canonical, display)] preserving order, de-duplicated by canonical form."""
    seen, out = set(), []
    for it in items:
        c = canon(it)
        if c and c not in seen:
            seen.add(c)
            out.append((c, it))
    return out
