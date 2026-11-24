import pytest

from app.ml.profile import DeveloperProfile
from app.ml import scoring as S
from app.ml.terms import IssueView
from tests.ml_doubles import NOW, make_issue


def v(**kw):
    return IssueView.of(make_issue(**kw))


# ---- semantic
def test_semantic_mapping_bounds_and_monotonic():
    assert S.semantic_score(-0.5) == 0 and S.semantic_score(0.10) == 0
    assert S.semantic_score(0.60) == 100 and S.semantic_score(0.99) == 100
    assert S.semantic_score(0.35) == pytest.approx(50)
    assert S.semantic_score(float("nan")) == 0
    assert S.semantic_score(0.2) < S.semantic_score(0.3)


# ---- skill compatibility
def test_skill_whole_word_matching():
    p = DeveloperProfile(skills=["Java"])
    assert S.skill_compatibility(p, v(title="Fix JavaScript bug"))[0] == 0
    assert S.skill_compatibility(p, v(title="Fix Java bug"))[1] == ["Java"]


def test_skill_symbols_and_aliases():
    assert S.skill_compatibility(DeveloperProfile(skills=["C++"]), v(title="Crash in C++ parser"))[1] == ["C++"]
    assert S.skill_compatibility(DeveloperProfile(skills=["JS"]), v(title="javascript tooling"))[1] == ["JS"]
    assert S.skill_compatibility(DeveloperProfile(skills=["nodejs"]), v(title="node.js streams"))[1] == ["nodejs"]


def test_ambiguous_names_need_repo_language():
    go = DeveloperProfile(skills=["Go"])
    assert S.skill_compatibility(go, v(title="Let's go and fix this"))[0] == 0
    assert S.skill_compatibility(go, v(title="Fix bug", lang="Go"))[0] == 100
    assert S.skill_compatibility(go, v(title="golang module"))[1] == ["Go"]
    assert S.skill_compatibility(DeveloperProfile(skills=["R"]), v(title="R is great"))[0] == 0


def test_skill_strong_vs_weak_and_saturation():
    p = DeveloperProfile(skills=["Python"])
    strong = S.skill_compatibility(p, v(title="Python bug"))[0]
    weak = S.skill_compatibility(p, v(title="bug", body="written in python"))[0]
    assert strong == 100 and weak == pytest.approx(60)
    many = DeveloperProfile(skills=["a1", "b1", "c1", "d1", "e1", "Python"])
    assert S.skill_compatibility(many, v(title="Python"))[0] == pytest.approx(100 / 3)


def test_skill_no_terms_or_no_match():
    assert S.skill_compatibility(DeveloperProfile(domains=["web"]), v(title="x")) == (0.0, [])
    assert S.skill_compatibility(DeveloperProfile(skills=["Rust"]), v(title="Python")) == (0.0, [])


# ---- experience
def test_difficulty_from_labels():
    assert S.estimate_difficulty(make_issue(labels=["good first issue"], body="ok"))[0] == pytest.approx(0.2)
    assert S.estimate_difficulty(make_issue(labels=["advanced"], body="ok"))[0] == pytest.approx(0.85)
    d, ev = S.estimate_difficulty(make_issue(labels=["bug"], body="ok"))
    assert d == 0.5 and ev == []


def test_hardware_label_not_treated_as_hard():
    assert S.advanced_labels(["hardware"]) == []


def test_experience_compat_values():
    f = S.experience_compatibility
    assert f("beginner", 0.2, True) == 100
    assert f("beginner", 0.85, True) == 0
    assert f("advanced", 0.2, True) < 100 and f("advanced", 0.2, True) > f("beginner", 0.85, True)
    assert f("intermediate", 0.5, False) == 50          # no evidence -> neutral
    assert f("beginner", 0.35, True) > f("beginner", 0.5, True)


def test_experience_fits_level_ordering():
    easy = make_issue(labels=["good first issue"], body="ok")
    hard = make_issue(labels=["advanced"], body="ok")
    for issue, lvl, better in [(easy, "beginner", True), (hard, "beginner", False)]:
        d, ev = S.estimate_difficulty(issue)
        s = S.experience_compatibility(lvl, d, bool(ev))
        assert (s >= 90) == better


# ---- activity
def test_activity_decay_and_missing_data():
    fresh = make_issue(pushed="2026-11-21T00:00:00Z", updated="2026-11-21T00:00:00Z", stars=10000)
    old = make_issue(pushed="2024-01-01T00:00:00Z", updated="2024-01-01T00:00:00Z", stars=0)
    assert S.repository_activity(fresh, NOW) == pytest.approx(100)
    assert S.repository_activity(old, NOW) < 5
    no_repo = make_issue(pushed=None, stars=None, updated="2026-11-21T00:00:00Z")
    assert S.repository_activity(no_repo, NOW) == pytest.approx(100)    # only issue recency available
    half = make_issue(pushed=None, stars=None, updated="2026-10-07T00:00:00Z")   # 45 days
    assert S.repository_activity(half, NOW) == pytest.approx(50, abs=0.5)


def test_activity_future_dates_clamped():
    assert S.repository_activity(make_issue(pushed="2027-01-01T00:00:00Z", updated="2027-01-01T00:00:00Z"), NOW) <= 100


# ---- beginner friendliness
def test_beginner_friendliness():
    assert S.beginner_friendliness(make_issue(body="x" * 300, labels=["good first issue", "help wanted"]))[0] == 95
    assert S.beginner_friendliness(make_issue(body="x" * 300, labels=["bug"]))[0] == 40
    assert S.beginner_friendliness(make_issue(body="", labels=[]))[0] == 20
    assert S.beginner_friendliness(make_issue(body="", labels=["advanced"], comments=12))[0] == 0   # clipped


# ---- final
def test_weights_and_final_formula():
    assert sum(S.WEIGHTS.values()) == pytest.approx(1) and S.WEIGHTS["semantic"] == 0.45
    c = S.Components(semantic=100, skill=50, experience=0, activity=100, beginner=20)
    assert S.final_score(c) == pytest.approx(0.45 * 100 + 0.20 * 50 + 0 + 0.10 * 100 + 0.10 * 20)


def test_all_components_in_range_for_extremes():
    p = DeveloperProfile(skills=["Python"], experience_level="advanced")
    for issue in (make_issue(), make_issue(body="x" * 5000, comments=999, labels=["hard", "good first issue"], stars=0, pushed=None)):
        for cos in (-1, 0, 0.3, 1):
            c = S.score_issue(p, issue, cos, NOW)
            for val in (c.semantic, c.skill, c.experience, c.activity, c.beginner, S.final_score(c)):
                assert 0 <= val <= 100
