"""Tests for the evaluation framework itself (metric maths, pipeline, safeguards).
They use synthetic data and a TEST DOUBLE embedder, so they prove the code is correct, not how good the real model is."""
import csv
import json
import math
from pathlib import Path

import pytest

from evaluation import evaluate as E
from evaluation import metrics as M
from tests.github_mock import make_item
from tests.ml_doubles import ConceptEmbedder

# ------------------------------------------------------------------ metrics (hand-computed expectations)
R = [2, 0, 1, 0, 0, 2, 0]


def test_precision_recall_rr_hand_computed():
    assert M.precision_at_k(R, 5, 1) == pytest.approx(2 / 5)       # relevant in top5: ranks 1 and 3
    assert M.precision_at_k(R, 5, 2) == pytest.approx(1 / 5)
    assert M.recall_at_k(R, 5, 1) == pytest.approx(2 / 3)           # 3 relevant overall
    assert M.recall_at_k(R, 5, 2) == pytest.approx(1 / 2)
    assert M.reciprocal_rank(R, 1) == 1.0
    assert M.reciprocal_rank([0, 0, 1], 1) == pytest.approx(1 / 3)
    assert M.reciprocal_rank([1, 1, 2], 2) == pytest.approx(1 / 3)


def test_ndcg_hand_computed():
    dcg = 3 / math.log2(2) + 1 / math.log2(4)                       # gains 2^rel-1 at ranks 1 and 3
    ideal = 3 / math.log2(2) + 3 / math.log2(3) + 1 / math.log2(4)  # [2,2,1,0,0]
    assert M.ndcg_at_k(R, 5) == pytest.approx(dcg / ideal)
    assert M.ndcg_at_k([2, 2, 1, 0, 0, 0], 5) == pytest.approx(1.0)  # already ideal
    assert M.ndcg_at_k([0, 0, 0, 1, 2], 5) < M.ndcg_at_k([2, 1, 0, 0, 0], 5)


def test_undefined_cases_return_none():
    zeros = [0, 0, 0, 0, 0, 0]
    assert M.recall_at_k(zeros, 5) is None and M.ndcg_at_k(zeros, 5) is None and M.reciprocal_rank(zeros) is None
    assert M.precision_at_k(zeros, 5) == 0
    assert M.recall_at_k([1, 0, 0], 5, threshold=2) is None          # nothing strictly relevant


def test_mean_skips_undefined():
    assert M.mean([1.0, None, 0.0]) == (0.5, 2)
    assert M.mean([None]) == (None, 0)


def test_bootstrap_is_deterministic_and_sane():
    vals = [0.2, 0.4, 0.6, 0.8, 1.0, 0.1, 0.9]
    a, b = M.bootstrap_ci(vals, seed=1), M.bootstrap_ci(vals, seed=1)
    assert a == b and a[0] <= sum(vals) / len(vals) <= a[1]
    assert M.bootstrap_ci([0.5] * 6, seed=0) == (0.5, 0.5)
    assert M.bootstrap_ci([0.5], seed=0) is None


def test_paired_difference():
    r = M.paired_difference({"a": .5, "b": .7, "c": None}, {"a": .3, "b": .7, "c": .1})
    assert r["n"] == 2 and r["mean_diff"] == pytest.approx(0.1)
    assert (r["queries_a_better"], r["queries_b_better"], r["ties"]) == (1, 0, 1)
    assert M.paired_difference({}, {})["mean_diff"] is None


# ------------------------------------------------------------------ pipeline on a tiny synthetic dataset
def _write_dataset(d: Path, judge=None):
    (d / "data").mkdir(parents=True, exist_ok=True)
    rows = [
        {"query_id": "qa", "description": "ml dev", "skills": "Python|PyTorch", "learning_interests": "", "experience_level": "beginner", "domains": "machine learning", "preferred_languages": "Python"},
        {"query_id": "qb", "description": "web dev", "skills": "React|CSS", "learning_interests": "", "experience_level": "intermediate", "domains": "web development", "preferred_languages": "JavaScript"},
    ]
    with open(d / "evaluation_queries.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    def issues(prefix):
        base = [("Neural network training bug", "gradient problem in the model trainer", ["bug"]),
                ("Add PyTorch Python tests", "tests for the training loop", ["good first issue"]),
                ("Fix CSS button colour", "frontend html styling", ["good first issue"]),
                ("React component crashes", "browser dom javascript error", ["help wanted"]),
                ("Docker deploy pipeline fails", "container terraform", ["bug"]),
                ("Typo in README", "docs typo", ["documentation"])]
        out = []
        for n, (t, b, l) in enumerate(base, start=1):
            it = make_item(n + (100 if prefix == "qb" else 0), "o/r", body=b, labels=tuple(l)); it["title"] = t
            from app.schemas.issues import Issue
            p = Issue.model_validate(_norm(it))
            out.append({**json.loads(p.model_dump_json()), "pool": "specific"})
        return out

    cands = {"queries": {q: issues(q) for q in ("qa", "qb")}, "collected_at": "2026-11-21T00:00:00+00:00", "repo_metadata_collected": False}
    (d / "data" / "candidates.json").write_text(json.dumps(cands))
    labels = judge or {"qa": [1, 2, 0, 0, 0, 0], "qb": [0, 0, 2, 2, 0, 0]}
    with open(d / "relevance_judgments.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["query_id", "issue_id", "relevance"])
        for q, ls in labels.items():
            for it, rel in zip(cands["queries"][q], ls):
                w.writerow([q, it["id"], rel])
    return d


def _norm(item):
    """GitHub search item -> Issue kwargs, via the production parser."""
    from app.services.github_client import GitHubClient
    return GitHubClient._parse_issue(item)[0]


def _stable(summary):
    s = json.loads(json.dumps(summary))
    s["metadata"].pop("evaluated_at")
    return s


def test_pipeline_runs_all_systems(tmp_path):
    d = _write_dataset(tmp_path)
    s = E.run(embedder=ConceptEmbedder(), data_dir=d, out_dir=d / "results")
    for name in E.SYSTEMS:
        assert s["systems"][name]["status"] == "ok"
        m = s["systems"][name]["metrics"]
        assert all(0 <= m[k]["mean"] <= 1 for k in ("p@5", "recall@5", "ndcg@5", "mrr"))
        assert m["ndcg@5"]["n_queries"] == 2
    assert s["dataset"]["n_queries"] == 2 and s["dataset"]["label_counts"] == {"0": 8, "1": 1, "2": 3}
    assert "hybrid_minus_keyword" in s["paired_comparisons"]
    for f in ("metrics_summary.json", "per_query_metrics.csv", "rankings.csv", "RESULTS.md"):
        assert (d / "results" / f).exists()
    assert "Hybrid" in (d / "results" / "RESULTS.md").read_text()


def test_same_candidates_for_every_system(tmp_path):
    d = _write_dataset(tmp_path)
    E.run(embedder=ConceptEmbedder(), data_dir=d, out_dir=d / "results")
    rows = list(csv.DictReader(open(d / "results" / "rankings.csv")))
    for q in ("qa", "qb"):
        sets = {s: {r["issue_id"] for r in rows if r["system"] == s and r["query_id"] == q} for s in E.SYSTEMS}
        assert sets["keyword"] == sets["semantic"] == sets["hybrid"] and len(sets["keyword"]) == 6


def test_rankers_never_see_judgments(tmp_path):
    """Changing every label must change the metrics but not a single ranking."""
    a = _write_dataset(tmp_path / "a")
    b = _write_dataset(tmp_path / "b", judge={"qa": [0, 0, 0, 0, 2, 2], "qb": [2, 2, 0, 0, 1, 1]})
    E.run(embedder=ConceptEmbedder(), data_dir=a, out_dir=a / "results")
    E.run(embedder=ConceptEmbedder(), data_dir=b, out_dir=b / "results")
    ra = [(r["system"], r["query_id"], r["rank"], r["issue_id"], r["score"]) for r in csv.DictReader(open(a / "results" / "rankings.csv"))]
    rb = [(r["system"], r["query_id"], r["rank"], r["issue_id"], r["score"]) for r in csv.DictReader(open(b / "results" / "rankings.csv"))]
    assert ra == rb
    assert (a / "results" / "metrics_summary.json").read_text() != (b / "results" / "metrics_summary.json").read_text()


def test_reproducible(tmp_path):
    d = _write_dataset(tmp_path)
    s1 = E.run(embedder=ConceptEmbedder(), data_dir=d, out_dir=d / "r1")
    s2 = E.run(embedder=ConceptEmbedder(), data_dir=d, out_dir=d / "r2")
    assert _stable(s1) == _stable(s2)
    assert (d / "r1" / "rankings.csv").read_text() == (d / "r2" / "rankings.csv").read_text()


def test_missing_model_reports_not_run_instead_of_inventing(tmp_path):
    from app.ml.embedder import EmbeddingModelError

    class NoModel:
        model_name = "x"
        def embed(self, texts):
            raise EmbeddingModelError("Could not load embedding model 'x': OSError")

    d = _write_dataset(tmp_path)
    s = E.run(embedder=NoModel(), data_dir=d, out_dir=d / "results")
    assert s["systems"]["keyword"]["status"] == "ok" and "metrics" in s["systems"]["keyword"]
    for name in ("semantic", "hybrid"):
        assert s["systems"][name]["status"] == "not_run" and "metrics" not in s["systems"][name]
        assert "Could not load" in s["systems"][name]["reason"]
    assert set(s["paired_comparisons"]) == set()                      # nothing to compare
    md = (d / "results" / "RESULTS.md").read_text()
    assert "did not run" in md and "not_run" in md


def test_keyword_only_needs_no_model(tmp_path):
    d = _write_dataset(tmp_path)
    s = E.run(systems=("keyword",), data_dir=d, out_dir=d / "results")
    assert s["systems"]["keyword"]["status"] == "ok" and s["systems"]["hybrid"]["status"] == "not_requested"


# ------------------------------------------------------------------ judgment validation
def test_judgment_validation(tmp_path):
    d = _write_dataset(tmp_path)
    _, cands = E.load_candidates(d / "data" / "candidates.json")
    j = d / "relevance_judgments.csv"
    lines = j.read_text().splitlines()

    j.write_text("\n".join(lines[:-1]) + "\n")                      # a candidate without a label
    with pytest.raises(ValueError, match="no judgment"):
        E.load_judgments(j, cands)
    j.write_text("\n".join(lines + ["qa,999999,1"]) + "\n")          # a label without a candidate
    with pytest.raises(ValueError, match="match no candidate"):
        E.load_judgments(j, cands)
    j.write_text("\n".join(lines + [lines[1]]) + "\n")              # duplicate
    with pytest.raises(ValueError, match="duplicate"):
        E.load_judgments(j, cands)
    j.write_text("\n".join([lines[0], lines[1].rsplit(",", 1)[0] + ",3", *lines[2:]]) + "\n")   # label 3
    with pytest.raises(ValueError, match="0, 1 or 2"):
        E.load_judgments(j, cands)


def test_tie_break_is_neutral_and_deterministic():
    from app.schemas.issues import Issue
    mk = lambda n, upd: Issue.model_validate(_norm(make_item(n, updated_at=upd)))
    old, new_a, new_b = mk(1, "2026-01-01T00:00:00Z"), mk(2, "2026-02-01T00:00:00Z"), mk(3, "2026-02-01T00:00:00Z")
    tie = lambda issues: [i for i, _ in E._order(issues, {x.id: 0.0 for x in issues})]
    assert tie([old, new_a]) == [new_a.id, old.id]                       # equal score: newer first
    assert tie([new_b, new_a]) == [new_a.id, new_b.id]                   # equal date: lower id first
    assert tie([new_a, old, new_b]) == tie([new_b, old, new_a])          # input order is irrelevant


def test_random_reference_matches_chance_level(tmp_path):
    d = _write_dataset(tmp_path)
    s = E.run(systems=("keyword",), data_dir=d, out_dir=d / "results")
    ref = s["systems"]["random_reference"]["metrics"]
    # qa has 2/6 and qb has 2/6 lenient-relevant candidates, so chance-level P@5 is ~ (5/6)*... = fraction relevant
    assert ref["p@5"]["mean"] == pytest.approx(2 / 6, abs=0.03)
    assert 0 < ref["ndcg@5"]["mean"] < 1
    assert "Random order" in (d / "results" / "RESULTS.md").read_text()


def test_oracle_reference_is_perfect_and_bounds_systems(tmp_path):
    d = _write_dataset(tmp_path)
    s = E.run(embedder=ConceptEmbedder(), data_dir=d, out_dir=d / "results")
    orc = s["systems"]["oracle_reference"]["metrics"]
    assert orc["ndcg@5"]["mean"] == pytest.approx(1.0) and orc["mrr"]["mean"] == 1.0
    for name in E.SYSTEMS:
        m = s["systems"][name]["metrics"]
        assert m["ndcg@5"]["mean"] <= 1.0 + 1e-9 and m["p@5"]["mean"] <= orc["p@5"]["mean"] + 1e-9
    assert set(s["dataset"]["label_counts_by_pool"]) == {"specific"}


# ------------------------------------------------------------------ the shipped dataset
EVAL = Path(__file__).resolve().parents[1] / "evaluation"


def test_shipped_dataset_is_complete_and_consistent():
    profiles = E.load_queries(EVAL / "evaluation_queries.csv")
    raw, cands = E.load_candidates(EVAL / "data" / "candidates.json")
    j = E.load_judgments(EVAL / "relevance_judgments.csv", cands)   # raises on any gap/extra/duplicate/bad value
    assert set(profiles) == set(cands) and len(profiles) == 20
    assert all(10 <= len(v) <= 15 for v in cands.values())
    assert len({p.experience_level for p in profiles.values()}) == 3
    assert all(not p.is_empty for p in profiles.values())
    # real GitHub issues: open issues only, never pull requests, valid GitHub URLs
    for issues in cands.values():
        for i in issues:
            assert i.state == "open" and i.url.startswith("https://github.com/") and "/pull/" not in i.url
    assert {0, 1, 2} <= set(j.values())
    # every query has at least one relevant candidate (otherwise recall/MRR would be undefined for it)
    for q, issues in cands.items():
        assert max(j[(q, i.id)] for i in issues) >= 1
    assert raw["collected_at"]


def test_shipped_rationales_present():
    rows = list(csv.DictReader(open(EVAL / "relevance_judgments.csv", encoding="utf-8")))
    assert len(rows) == 240 and all(r["rationale"].strip() for r in rows)
