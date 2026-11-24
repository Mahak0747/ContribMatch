import pytest
from pydantic import ValidationError

from app.ml.profile import DeveloperProfile
from app.ml.text_builder import clean_body, issue_text, profile_text
from tests.ml_doubles import make_issue


def test_profile_normalises_and_dedupes():
    p = DeveloperProfile(skills=["  Python ", "python", "Fast  API", ""], experience_level=" Intermediate ")
    assert p.skills == ["Python", "Fast API"] and p.experience_level == "intermediate"


def test_empty_profile_detected():
    assert DeveloperProfile().is_empty
    assert not DeveloperProfile(domains=["web"]).is_empty


@pytest.mark.parametrize("bad", [
    {"skills": "python"}, {"skills": [1, 2]}, {"experience_level": "guru"}, {"skills": ["x" * 51]},
    {"skills": [f"s{i}" for i in range(31)]}, {"unknown": 1},
])
def test_invalid_profiles(bad):
    with pytest.raises(ValidationError):
        DeveloperProfile(**bad)


def test_profile_text_omits_empty_parts_and_experience():
    t = profile_text(DeveloperProfile(skills=["Python"], experience_level="advanced"))
    assert t == "Developer skills: Python."
    assert "advanced" not in t


def test_issue_text_missing_description_and_labels():
    t = issue_text(make_issue(title="Fix crash", body="", labels=[], lang=None, repo_desc=None))
    assert t == "Fix crash."
    t = issue_text(make_issue(title="Fix crash", body=None))
    assert t == "Fix crash."


def test_issue_text_includes_available_fields_in_order():
    t = issue_text(make_issue(title="Add tests", body="Please add unit tests.", labels=["good first issue"],
                              lang="Python", repo_desc="A web framework"))
    assert t.index("Add tests") < t.index("Labels") < t.index("Language: Python") < t.index("Repository: A web framework") < t.index("Please add")


def test_clean_body_strips_noise():
    raw = "<!-- template -->Hello ![img](http://x/y.png) see https://example.com ```\ncode\n``` **bold**"
    assert clean_body(raw) == "Hello see bold"
    assert clean_body(None) == "" and len(clean_body("a " * 2000)) <= 1000
