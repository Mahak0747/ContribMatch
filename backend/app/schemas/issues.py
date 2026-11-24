import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LANG_RE = re.compile(r"^[A-Za-z0-9+#.\- ]{1,30}$")


def _clean_text(v: str | None) -> str | None:
    """Strip characters that could inject GitHub search qualifiers or break quoting."""
    if v is None:
        return None
    v = re.sub(r"[\"':\\]", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None


class IssueSearchParams(BaseModel):
    """Validated query parameters for GET /api/issues/search."""
    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(None, description="Repository primary language, e.g. Python")
    labels: list[str] = Field(default_factory=list, description="Issue labels (repeat param or comma-separate). Max 5. Matched as OR.")
    domain: str | None = Field(None, description="Domain keywords, e.g. 'machine learning'")
    q: str | None = Field(None, description="Extra free-text keywords")
    sort: Literal["updated", "created", "comments", "best-match"] = "updated"
    per_page: int = Field(20, ge=1, le=50)
    page: int = Field(1, ge=1, le=10)
    unassigned: bool = Field(True, description="Only issues with no assignee")

    @field_validator("language")
    @classmethod
    def _language(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not _LANG_RE.match(v):
            raise ValueError("language contains invalid characters or is too long")
        return v

    @field_validator("labels", mode="before")
    @classmethod
    def _labels(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out: list[str] = []
        for item in v:
            for part in str(item).split(","):
                part = part.replace('"', "").strip()
                if not part:
                    continue
                if len(part) > 50:
                    raise ValueError("label too long (max 50 characters)")
                if part.lower() not in {x.lower() for x in out}:
                    out.append(part)
        if len(out) > 5:
            raise ValueError("at most 5 labels are allowed")
        return out

    @field_validator("domain", "q")
    @classmethod
    def _text(cls, v):
        v = _clean_text(v)
        if v and len(v) > 100:
            raise ValueError("must be at most 100 characters")
        return v

    def cache_key(self) -> tuple:
        return (
            (self.language or "").lower(),
            tuple(sorted(l.lower() for l in self.labels)),
            (self.domain or "").lower(),
            (self.q or "").lower(),
            self.sort, self.per_page, self.page, self.unassigned,
        )


class Issue(BaseModel):
    id: int
    number: int
    title: str
    body: str = ""
    url: str
    state: str
    labels: list[str] = Field(default_factory=list)
    comments: int = 0
    created_at: datetime
    updated_at: datetime
    repo_full_name: str
    repo_url: str
    repo_description: str | None = None
    repo_language: str | None = None
    repo_stars: int | None = None
    repo_pushed_at: datetime | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _strip_nul(cls, v):
        """PostgreSQL text/JSON columns cannot store the NUL character (U+0000); SQLite can. Strip it here so
        a stray NUL in a GitHub issue can never make a database write fail."""
        if isinstance(v, str):
            return v.replace("\x00", "")
        if isinstance(v, list):
            return [x.replace("\x00", "") if isinstance(x, str) else x for x in v]
        return v

    @field_validator("body", mode="before")
    @classmethod
    def _body_none(cls, v):
        return "" if v is None else v

    @field_validator("labels", mode="before")
    @classmethod
    def _labels_none(cls, v):
        return [] if v is None else v


class RateLimitInfo(BaseModel):
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None


class IssueSearchResponse(BaseModel):
    query: str = Field(description="The GitHub search query that was executed")
    total_count: int
    incomplete_results: bool = False
    count: int
    page: int
    per_page: int
    issues: list[Issue]
    cached: bool = False
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)
    rate_limit: RateLimitInfo | None = None
