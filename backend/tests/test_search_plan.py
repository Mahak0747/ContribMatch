from app.ml.profile import DeveloperProfile
from app.services.search_plan import build_search_plan, profile_languages


def P(**kw):
    return DeveloperProfile(**kw)


def test_language_and_domain_then_widening():
    plans = build_search_plan(P(skills=["x"], preferred_languages=["Python"], domains=["machine learning"]))
    assert [(p.language, p.domain) for p in plans] == [("Python", "machine learning"), ("Python", None)]


def test_two_languages_max_and_query_cap():
    plans = build_search_plan(P(preferred_languages=["Python", "Go", "Rust"], domains=["web"]), max_queries=2)
    assert len(plans) == 2 and {p.language for p in plans} == {"Python", "Go"}


def test_level_labels_and_override():
    assert build_search_plan(P(skills=["Python"], experience_level="advanced"))[0].labels == ["help wanted"]
    assert build_search_plan(P(skills=["Python"]), labels=["docs"])[0].labels == ["docs"]


def test_languages_derived_from_skills():
    assert profile_languages(P(skills=["Docker", "golang", "C++"])) == ["golang", "C++"]


def test_invalid_language_skipped_not_sent():
    plans = build_search_plan(P(skills=["Docker"], preferred_languages=["C/C++;"]))
    assert all(p.language is None for p in plans) and plans


def test_fallback_label_only_when_nothing_usable():
    plans = build_search_plan(P(learning_interests=["Rust"]))
    assert len(plans) == 1 and plans[0].language is None and plans[0].q is None


def test_plans_are_distinct_and_per_page_applied():
    plans = build_search_plan(P(preferred_languages=["Python", "python"]), per_page=15)
    assert len(plans) == 1 and plans[0].per_page == 15
