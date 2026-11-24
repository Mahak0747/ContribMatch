"""Structural tests of the keyword-vs-semantic comparison code.
They use a TEST DOUBLE embedder, so they verify the code path only; they do NOT measure the real model."""
from app.ml.baseline import compare_rankings, keyword_score
from app.ml.profile import DeveloperProfile
from tests.ml_doubles import NOW, ConceptEmbedder, make_issue

P = DeveloperProfile(skills=["Python"], domains=["machine learning"])


def test_keyword_score_counts_literal_terms_only():
    synonym = make_issue(1, "Fix gradient bug in neural network trainer")
    literal = make_issue(2, "Add machine learning example in Python")
    assert keyword_score(P, synonym) == 0
    assert keyword_score(P, literal) == 100
    assert keyword_score(DeveloperProfile(), literal) == 0


def test_comparison_table_shape_and_synonym_case():
    iss = [make_issue(1, "Fix gradient bug in neural network trainer"),
           make_issue(2, "Update CSS colours", "frontend styling"),
           make_issue(3, "Add machine learning example in Python")]
    df = compare_rankings(P, iss, ConceptEmbedder(), now=NOW)
    assert {"keyword_score", "semantic_score", "hybrid_score", "keyword_rank", "semantic_rank", "hybrid_rank"} <= set(df.columns)
    assert len(df) == 3
    syn = df[df.issue_id == 1].iloc[0]
    css = df[df.issue_id == 2].iloc[0]
    assert syn.keyword_score == 0 and css.keyword_score == 0          # keyword matching cannot tell them apart
    assert syn.keyword_rank == css.keyword_rank
    assert syn.semantic_score > css.semantic_score                    # concept-aware matching can
    assert syn.semantic_rank < css.semantic_rank


def test_compare_cli_reports_model_failure_cleanly(monkeypatch, capsys):
    """Without the model (e.g. offline) the CLI exits 1 with a clear message instead of a traceback."""
    from app.ml import compare

    class Broken:
        model_name = "x"
        def embed(self, texts):
            raise OSError("no network")

    monkeypatch.setattr(compare, "get_embedder", lambda: Broken())
    assert compare.main([]) == 1
    assert "Could not run the embedding model" in capsys.readouterr().err


def test_compare_cli_runs_with_injected_embedder(monkeypatch, capsys):
    from app.ml import compare
    monkeypatch.setattr(compare, "get_embedder", lambda: ConceptEmbedder())
    assert compare.main([]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "keyword_score" in out and "hybrid_rank" in out
