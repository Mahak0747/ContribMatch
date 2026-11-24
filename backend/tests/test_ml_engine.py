import pytest
from pydantic import ValidationError

from app.ml.engine import InvalidProfileError, RecommendationEngine
from app.ml.profile import DeveloperProfile
from tests.ml_doubles import NOW, ConceptEmbedder, make_issue

ML_PROFILE = DeveloperProfile(skills=["Python", "PyTorch"], domains=["machine learning"],
                              learning_interests=["Rust"], experience_level="beginner", preferred_languages=["Python"])


def engine(**kw):
    return RecommendationEngine(ConceptEmbedder(), now=NOW, **kw)


def issues():
    return [
        make_issue(1, "Fix typo in README", "There is a typo in the docs.", ["documentation", "good first issue"], lang="Markdown"),
        make_issue(2, "Add PyTorch dataloader tests", "Training the neural network needs coverage. Python code.",
                   ["good first issue", "machine-learning"], lang="Python", repo_desc="Deep learning library"),
        make_issue(3, "Dockerfile build fails", "Container pipeline broken on kubernetes.", ["bug"], lang="Dockerfile"),
        make_issue(4, "Refactor gradient engine", "Complex autograd rewrite. Rust bindings may help.", ["advanced"], lang="Python",
                   comments=15),
    ]


# ---- ranking behaviour
def test_relevant_issue_ranked_first_for_relevant_profile():
    recs = engine().rank(ML_PROFILE, issues())
    assert recs[0].issue.id == 2
    assert [r.rank for r in recs] == [1, 2, 3, 4]
    assert [r.scores.overall for r in recs] == sorted([r.scores.overall for r in recs], reverse=True)


def test_unrelated_profile_scores_lower_on_same_issue():
    web = DeveloperProfile(skills=["React", "CSS"], domains=["web development"])
    iss = [issues()[1]]
    rel = engine().rank(ML_PROFILE, iss)[0]
    unrel = engine().rank(web, iss)[0]
    assert unrel.scores.semantic_similarity < rel.scores.semantic_similarity
    assert unrel.scores.skill_compatibility < rel.scores.skill_compatibility
    assert unrel.scores.overall < rel.scores.overall


def test_all_scores_between_0_and_100():
    for r in engine().rank(ML_PROFILE, issues()):
        for v in r.scores.model_dump().values():
            assert 0 <= v <= 100


def test_overall_matches_weighted_formula():
    r = engine().rank(ML_PROFILE, issues())[0]
    s = r.scores
    # rounding of each component to 1 decimal -> small tolerance
    expected = (.45 * s.semantic_similarity + .20 * s.skill_compatibility + .15 * s.experience_compatibility
                + .10 * s.repository_activity + .10 * s.beginner_friendliness)
    assert s.overall == pytest.approx(expected, abs=0.2)


def test_top_k_default_10_and_limits():
    many = [make_issue(i, f"Issue {i}") for i in range(1, 26)]
    assert len(engine().rank(ML_PROFILE, many)) == 10
    assert len(engine().rank(ML_PROFILE, many, top_k=3)) == 3
    assert len(engine().rank(ML_PROFILE, many, top_k=None)) == 25
    for bad in (0, -1, 101):
        with pytest.raises(ValueError):
            engine().rank(ML_PROFILE, many, top_k=bad)


def test_deterministic_and_tie_break_stable():
    same = [make_issue(i, "Same title") for i in (5, 3, 9)]
    a = [r.issue.id for r in engine().rank(ML_PROFILE, same)]
    b = [r.issue.id for r in engine().rank(ML_PROFILE, list(reversed(same)))]
    assert a == b == [3, 5, 9]


def test_duplicate_issue_ids_removed():
    iss = issues() + [issues()[0]]
    assert len(engine().rank(ML_PROFILE, iss)) == 4


# ---- invalid / edge input
def test_empty_profile_rejected():
    with pytest.raises(InvalidProfileError):
        engine().rank(DeveloperProfile(), issues())
    with pytest.raises(InvalidProfileError):
        engine().rank({"experience_level": "advanced"}, issues())


def test_invalid_profile_input_rejected():
    with pytest.raises(ValidationError):
        engine().rank({"skills": "python"}, issues())
    with pytest.raises(ValidationError):
        engine().rank({"experience_level": "wizard", "skills": ["x"]}, issues())


def test_dict_profile_accepted():
    assert engine().rank({"skills": ["Python"]}, issues())


def test_no_issues_returns_empty_without_embedding():
    emb = ConceptEmbedder()
    assert RecommendationEngine(emb, now=NOW).rank(ML_PROFILE, []) == []
    assert emb.calls == 0


def test_missing_description_and_labels_ok():
    r = engine().rank(ML_PROFILE, [make_issue(1, "Python PyTorch question", body="", labels=[])])[0]
    assert r.relevant_labels == [] and r.issue.body == ""
    assert r.matching_skills == ["Python", "PyTorch"]


def test_single_batched_embedding_call():
    emb = ConceptEmbedder()
    RecommendationEngine(emb, now=NOW).rank(ML_PROFILE, issues())
    assert emb.calls == 1 and emb.texts_seen == 5   # 1 profile + 4 issues


def test_bad_weights_rejected():
    with pytest.raises(ValueError):
        RecommendationEngine(ConceptEmbedder(), weights={"semantic": 1.0})
    with pytest.raises(ValueError):
        RecommendationEngine(ConceptEmbedder(), weights={"semantic": .5, "skill": .5, "experience": .5, "activity": 0, "beginner": 0})


# ---- explanations come from real features
def test_explanation_only_states_real_matches():
    r = {x.issue.id: x for x in engine().rank(ML_PROFILE, issues())}
    top = r[2]
    assert top.matching_skills == ["Python", "PyTorch"]
    assert "Mentions your skills: Python, PyTorch." in top.explanation
    assert "preferred domain" in top.explanation          # 'machine learning' found via label 'machine-learning'
    assert "good first issue" in top.explanation and "fits your beginner level" in top.explanation
    assert top.relevant_labels == ["good first issue", "machine-learning"]
    docs = r[1]
    assert docs.matching_skills == []
    assert "Mentions your skills" not in docs.explanation
    assert "No explicit overlap" in docs.explanation


def test_explanation_never_mentions_absent_skill():
    docs = engine().rank(ML_PROFILE, [issues()[0]])[0]
    for word in ("PyTorch", "Rust", "machine learning"):
        assert word not in docs.explanation


def test_potential_skills_are_literally_in_issue():
    r = {x.issue.id: x for x in engine().rank(ML_PROFILE, issues())}
    assert r[4].potential_skills_to_learn[0] == "Rust"          # a stated learning interest mentioned in the issue
    assert r[1].potential_skills_to_learn == []
    assert "docker" in r[3].potential_skills_to_learn or "kubernetes" in r[3].potential_skills_to_learn
    for x in r.values():
        text = (x.issue.title + " " + x.issue.body + " " + " ".join(x.issue.labels) + " " + (x.issue.repo_description or "")
                + " " + (x.issue.repo_language or "")).lower()
        for s in x.potential_skills_to_learn:
            assert s.lower() in text
        assert not set(map(str.lower, x.potential_skills_to_learn)) & {"python", "pytorch", "machine learning"}   # already listed by the developer


def test_difficulty_signals_exposed():
    r = {x.issue.id: x for x in engine().rank(ML_PROFILE, issues())}
    assert any("advanced" in s for s in r[4].difficulty_signals)
    assert r[4].scores.experience_compatibility < r[2].scores.experience_compatibility


def test_semantic_explanation_sentence_reflects_score():
    r = engine().rank(ML_PROFILE, issues())
    for x in r:
        assert f"{x.scores.semantic_similarity:.0f}/100" in x.explanation
