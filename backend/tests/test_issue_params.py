import pytest
from pydantic import ValidationError

from app.schemas.issues import IssueSearchParams
from app.services.github_client import build_search_query


def test_defaults_query():
    q = build_search_query(IssueSearchParams())
    assert q == "is:issue is:open archived:false no:assignee"


def test_full_query():
    p = IssueSearchParams(language="Python", labels=["good first issue", "help wanted"], domain="machine learning", q="tokenizer")
    q = build_search_query(p)
    assert "language:Python" in q
    assert 'label:"good first issue","help wanted"' in q
    assert "machine learning tokenizer" in q and q.endswith("in:title,body")


def test_special_language_quoted():
    assert 'language:"C++"' in build_search_query(IssueSearchParams(language="C++"))


def test_labels_comma_split_and_dedupe():
    p = IssueSearchParams(labels=["Beginner, help wanted", "beginner"])
    assert p.labels == ["Beginner", "help wanted"]


def test_qualifier_injection_stripped():
    p = IssueSearchParams(domain='web" repo:evil/x user:bob')
    assert ":" not in p.domain and '"' not in p.domain


@pytest.mark.parametrize("kw", [
    {"per_page": 0}, {"per_page": 51}, {"page": 0}, {"page": 11}, {"sort": "random"},
    {"language": "py;thon!"}, {"labels": list("abcdef")}, {"q": "x" * 101}, {"bogus": 1},
])
def test_invalid_params(kw):
    with pytest.raises(ValidationError):
        IssueSearchParams(**kw)


def test_empty_strings_become_none():
    p = IssueSearchParams(language="  ", domain="  ", q="")
    assert p.language is None and p.domain is None and p.q is None
