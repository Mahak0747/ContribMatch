"""Build the text that is embedded for developer profiles and issues.

The experience level is deliberately NOT embedded: it is handled by its own score component,
and putting words like "beginner" into the text would double count with label matching.
"""
import re

from app.ml.profile import DeveloperProfile
from app.schemas.issues import Issue

MAX_BODY_CHARS = 1000   # MiniLM truncates at 256 word pieces (~1000 chars); title/labels come first

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_URL = re.compile(r"https?://\S+")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_NOISE = re.compile(r"[#>*_`|\[\]]+")


def clean_body(body: str | None) -> str:
    if not body:
        return ""
    t = _HTML_COMMENT.sub(" ", body)
    t = _CODE_FENCE.sub(" ", t)
    t = _MD_IMAGE.sub(" ", t)
    t = _URL.sub(" ", t)
    t = _MD_NOISE.sub(" ", t)
    return " ".join(t.split())[:MAX_BODY_CHARS]


def profile_text(p: DeveloperProfile) -> str:
    parts = []
    if p.skills:
        parts.append("Developer skills: " + ", ".join(p.skills) + ".")
    if p.preferred_languages:
        parts.append("Preferred programming languages: " + ", ".join(p.preferred_languages) + ".")
    if p.domains:
        parts.append("Interested domains: " + ", ".join(p.domains) + ".")
    if p.learning_interests:
        parts.append("Wants to learn: " + ", ".join(p.learning_interests) + ".")
    return " ".join(parts)


def issue_text(i: Issue) -> str:
    """Missing/empty fields are simply omitted (no placeholder text is invented)."""
    parts = []
    if i.title and i.title.strip():
        parts.append(i.title.strip().rstrip(".") + ".")
    if i.labels:
        parts.append("Labels: " + ", ".join(i.labels) + ".")
    if i.repo_language:
        parts.append(f"Language: {i.repo_language}.")
    if i.repo_description and i.repo_description.strip():
        parts.append("Repository: " + i.repo_description.strip().rstrip(".") + ".")
    body = clean_body(i.body)
    if body:
        parts.append(body)
    return " ".join(parts)
