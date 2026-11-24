"""Evaluate keyword-baseline, semantic-only and hybrid ranking on the same candidate sets.

    cd backend
    python evaluation/evaluate.py                    # all three systems (downloads the model on first run)
    python evaluation/evaluate.py --systems keyword  # keyword baseline only (no model needed)

Inputs  (all in evaluation/): evaluation_queries.csv, data/candidates.json, relevance_judgments.csv
Outputs (evaluation/results/): metrics_summary.json, per_query_metrics.csv, rankings.csv, RESULTS.md

Rules this script follows:
  * ALL systems rank exactly the same frozen candidate issues for a query.
  * Rankers never see relevance judgments: rankings are computed first, judgments are loaded afterwards.
  * Nothing is estimated or filled in: a system that cannot run is reported as `not_run` with the reason.
  * Fixed seed and a fixed reference time (the candidate collection time) make the metrics reproducible.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import metrics as M  # noqa: E402
from app.ml.baseline import keyword_score  # noqa: E402
from app.ml.embedder import Embedder, EmbeddingModelError  # noqa: E402
from app.ml.engine import RecommendationEngine  # noqa: E402
from app.ml.profile import DeveloperProfile  # noqa: E402
from app.schemas.issues import Issue  # noqa: E402

K = 5
SEED = 12345
SYSTEMS = ("keyword", "semantic", "hybrid")
LABELS = {"keyword": "Keyword baseline", "semantic": "Semantic similarity only", "hybrid": "Hybrid (full ContribMatch score)"}
Ranking = dict[str, list[tuple[int, float]]]   # query_id -> [(issue_id, score)] best first


# ----------------------------------------------------------------------------- loading
def _split(s: str) -> list[str]:
    return [x for x in (s or "").split("|") if x.strip()]


def load_queries(path: Path) -> dict[str, DeveloperProfile]:
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        out[r["query_id"]] = DeveloperProfile(
            skills=_split(r["skills"]), learning_interests=_split(r["learning_interests"]),
            experience_level=r["experience_level"], domains=_split(r["domains"]),
            preferred_languages=_split(r["preferred_languages"]))
    return out


def load_candidates(path: Path) -> tuple[dict, dict[str, list[Issue]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cands = {q: [Issue.model_validate({k: v for k, v in i.items() if k != "pool"}) for i in items] for q, items in raw["queries"].items()}
    return raw, cands


def load_judgments(path: Path, candidates: dict[str, list[Issue]]) -> dict[tuple[str, int], int]:
    """Read labels and check they cover exactly the candidate sets (no gaps, extras, duplicates or bad values)."""
    j: dict[tuple[str, int], int] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        key = (r["query_id"], int(r["issue_id"]))
        if key in j:
            raise ValueError(f"duplicate judgment for {key}")
        rel = int(r["relevance"])
        if rel not in (0, 1, 2):
            raise ValueError(f"relevance must be 0, 1 or 2, got {rel} for {key}")
        j[key] = rel
    expected = {(q, i.id) for q, issues in candidates.items() for i in issues}
    if missing := expected - set(j):
        raise ValueError(f"{len(missing)} candidates have no judgment, e.g. {sorted(missing)[:3]}")
    if extra := set(j) - expected:
        raise ValueError(f"{len(extra)} judgments match no candidate, e.g. {sorted(extra)[:3]}")
    return j


# ----------------------------------------------------------------------------- rankers (no judgments here)
def _order(issues: list[Issue], scores: dict[int, float]) -> list[tuple[int, float]]:
    """Score descending; ties broken by most recently updated, then issue id (neutral, same rule everywhere)."""
    by_id = {i.id: i for i in issues}
    return sorted(((i, scores[i]) for i in scores), key=lambda t: (-t[1], -by_id[t[0]].updated_at.timestamp(), t[0]))


def rank_keyword(profiles, candidates) -> Ranking:
    return {q: _order(c, {i.id: keyword_score(profiles[q], i) for i in c}) for q, c in candidates.items()}


def rank_semantic_and_hybrid(profiles, candidates, embedder: Embedder, now: datetime) -> tuple[Ranking, Ranking]:
    engine = RecommendationEngine(embedder, now=now)
    sem: Ranking = {}
    hyb: Ranking = {}
    for q, issues in candidates.items():
        recs = engine.rank(profiles[q], issues, top_k=None)
        sem[q] = _order(issues, {r.issue.id: r.cosine_similarity for r in recs})   # raw cosine, no calibration ties
        hyb[q] = [(r.issue.id, r.scores.overall) for r in recs]                   # engine order (same tie rule)
    return sem, hyb


# ----------------------------------------------------------------------------- scoring against judgments
def score_system(ranking: Ranking, judgments: dict[tuple[str, int], int]) -> dict[str, dict[str, float | None]]:
    per_query = {}
    for q, ranked in ranking.items():
        rels = [judgments[(q, i)] for i, _ in ranked]
        per_query[q] = {
            "p@5": M.precision_at_k(rels, K, 1), "recall@5": M.recall_at_k(rels, K, 1),
            "ndcg@5": M.ndcg_at_k(rels, K), "mrr": M.reciprocal_rank(rels, 1),
            "p@5_strict": M.precision_at_k(rels, K, 2), "recall@5_strict": M.recall_at_k(rels, K, 2),
            "mrr_strict": M.reciprocal_rank(rels, 2),
        }
    return per_query


def summarise(per_query: dict[str, dict[str, float | None]]) -> dict[str, dict]:
    out = {}
    for metric in next(iter(per_query.values())):
        vals = [pq[metric] for pq in per_query.values()]
        mu, n = M.mean(vals)
        defined = [v for v in vals if v is not None]
        ci = M.bootstrap_ci(defined, seed=SEED) if defined else None
        out[metric] = {"mean": mu, "ci95": list(ci) if ci else None, "n_queries": n}
    return out


def random_expected(candidates, judgments, n_shuffles: int = 1000) -> dict[str, dict[str, float | None]]:
    """Reference point, not a system: expected metric values of a RANDOM ordering of each query's candidates,
    averaged over `n_shuffles` seeded shuffles. Shows what scores are achievable by chance on this data."""
    import random
    out = {}
    for q, issues in candidates.items():
        rels = [judgments[(q, i.id)] for i in issues]
        rng = random.Random(f"{SEED}-{q}")
        sums: dict[str, list[float]] = {}
        for _ in range(n_shuffles):
            rng.shuffle(rels)
            ranking = {q: [(idx, 0.0) for idx in range(len(rels))]}
            one = score_system(ranking, {(q, idx): r for idx, r in enumerate(rels)})[q]
            for k, v in one.items():
                if v is not None:
                    sums.setdefault(k, []).append(v)
        out[q] = {k: (sum(sums[k]) / len(sums[k]) if k in sums else None) for k in one}
    return out


def oracle_ordering(candidates, judgments) -> dict[str, dict[str, float | None]]:
    """Reference ceiling: the best possible ordering (most relevant first). Shows the maximum achievable
    value of each metric on this data, e.g. Recall@5 cannot reach 1 when a query has more than 5 relevant issues."""
    out = {}
    for q, issues in candidates.items():
        ranked = sorted(issues, key=lambda i: -judgments[(q, i.id)])
        out[q] = score_system({q: [(i.id, 0.0) for i in ranked]}, judgments)[q]
    return out


# ----------------------------------------------------------------------------- orchestration
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _versions() -> dict[str, str]:
    from importlib import metadata
    v = {"python": platform.python_version()}
    for pkg in ("sentence-transformers", "torch", "scikit-learn", "numpy", "pandas"):
        try:
            v[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            v[pkg] = "not installed"
    return v


def run(systems=SYSTEMS, embedder: Embedder | None = None, data_dir: Path = HERE, out_dir: Path | None = None) -> dict:
    out_dir = out_dir or data_dir / "results"
    qpath, cpath, jpath = data_dir / "evaluation_queries.csv", data_dir / "data" / "candidates.json", data_dir / "relevance_judgments.csv"
    profiles = load_queries(qpath)
    raw, candidates = load_candidates(cpath)
    if set(profiles) != set(candidates):
        raise ValueError("queries and candidates cover different query ids")
    now = datetime.fromisoformat(raw["collected_at"])

    # 1) rank (no access to judgments)
    rankings: dict[str, Ranking] = {}
    status: dict[str, dict] = {}
    if "keyword" in systems:
        rankings["keyword"] = rank_keyword(profiles, candidates)
        status["keyword"] = {"status": "ok"}
    if {"semantic", "hybrid"} & set(systems):
        try:
            if embedder is None:
                from app.core.config import get_settings
                from app.ml.embedder import SentenceTransformerEmbedder
                embedder = SentenceTransformerEmbedder(get_settings().embedding_model)
            sem, hyb = rank_semantic_and_hybrid(profiles, candidates, embedder, now)
            for name, r in (("semantic", sem), ("hybrid", hyb)):
                if name in systems:
                    rankings[name] = r
                    status[name] = {"status": "ok", "embedding_model": embedder.model_name}
        except EmbeddingModelError as exc:
            for name in ("semantic", "hybrid"):
                if name in systems:
                    status[name] = {"status": "not_run", "reason": str(exc)}

    # 2) only now read the human relevance labels
    judgments = load_judgments(jpath, candidates)
    per_query = {s: score_system(r, judgments) for s, r in rankings.items()}
    reference = random_expected(candidates, judgments)
    oracle = oracle_ordering(candidates, judgments)

    summary = {
        "metadata": {
            "evaluated_at": datetime.now(timezone.utc).isoformat(), "k": K, "bootstrap_seed": SEED,
            "reference_time_for_activity_scores": raw["collected_at"],
            "repo_metadata_in_candidates": raw.get("repo_metadata_collected", False),
            "versions": _versions(),
            "input_hashes_sha256_16": {"queries": sha(qpath), "candidates": sha(cpath), "judgments": sha(jpath)},
        },
        "dataset": dataset_stats(candidates, judgments),
        "systems": {s: {**status.get(s, {"status": "not_requested"}),
                        **({"metrics": summarise(per_query[s])} if s in per_query else {})} for s in SYSTEMS},
        "paired_comparisons": paired(per_query),
    }
    summary["systems"]["random_reference"] = {
        "status": "ok", "note": "expected values of a random ordering (1000 seeded shuffles per query); a reference, not a system",
        "metrics": summarise(reference)}
    summary["systems"]["oracle_reference"] = {
        "status": "ok", "note": "the best possible ordering on this data (upper bound), a reference, not a system",
        "metrics": summarise(oracle)}
    summary["dataset"]["label_counts_by_pool"] = label_counts_by_pool(raw, judgments)
    write_outputs(out_dir, summary, {**per_query, "random_reference": reference, "oracle_reference": oracle}, rankings, judgments)
    return summary


def dataset_stats(candidates, judgments) -> dict:
    labels = [judgments[(q, i.id)] for q, c in candidates.items() for i in c]
    per_q = {q: [judgments[(q, i.id)] for i in c] for q, c in candidates.items()}
    return {
        "n_queries": len(candidates), "n_candidates": len(labels),
        "candidates_per_query": {"min": min(map(len, candidates.values())), "max": max(map(len, candidates.values()))},
        "label_counts": {str(k): labels.count(k) for k in (0, 1, 2)},
        "queries_with_any_relevant_lenient": sum(1 for v in per_q.values() if max(v) >= 1),
        "queries_with_any_relevant_strict": sum(1 for v in per_q.values() if max(v) >= 2),
    }


def label_counts_by_pool(raw: dict, judgments) -> dict:
    """Post-hoc only (never used for ranking): how labels are distributed over the three retrieval pools."""
    out: dict[str, dict[str, int]] = {}
    for q, items in raw["queries"].items():
        for i in items:
            c = out.setdefault(i.get("pool", "unknown"), {"0": 0, "1": 0, "2": 0})
            c[str(judgments[(q, i["id"])])] += 1
    return out


def paired(per_query) -> dict:
    out = {}
    for a, b in (("hybrid", "keyword"), ("semantic", "keyword"), ("hybrid", "semantic")):
        if a in per_query and b in per_query:
            out[f"{a}_minus_{b}"] = {
                m: M.paired_difference({q: v[m] for q, v in per_query[a].items()}, {q: v[m] for q, v in per_query[b].items()}, seed=SEED)
                for m in ("ndcg@5", "p@5", "mrr")}
    return out


def write_outputs(out_dir: Path, summary, per_query, rankings, judgments) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metric_names = list(next(iter(next(iter(per_query.values())).values())).keys()) if per_query else []
    with open(out_dir / "per_query_metrics.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["system", "query_id", *metric_names])
        for s, pq in per_query.items():
            for q, m in pq.items():
                w.writerow([s, q, *("" if m[k] is None else f"{m[k]:.6f}" for k in metric_names)])
    with open(out_dir / "rankings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["system", "query_id", "rank", "issue_id", "score", "relevance_label"])
        for s, r in rankings.items():
            for q, ranked in r.items():
                for pos, (iid, sc) in enumerate(ranked, start=1):
                    w.writerow([s, q, pos, iid, f"{sc:.6f}", judgments[(q, iid)]])
    (out_dir / "RESULTS.md").write_text(render_markdown(summary), encoding="utf-8")


def _fmt(m: dict | None) -> str:
    if not m or m["mean"] is None:
        return "n/a"
    ci = f" [{m['ci95'][0]:.2f}, {m['ci95'][1]:.2f}]" if m["ci95"] else ""
    return f"{m['mean']:.3f}{ci}"


def render_markdown(s: dict) -> str:
    d = s["dataset"]
    lines = [
        "# Evaluation results (generated by `evaluate.py`; do not edit by hand)", "",
        f"Queries: **{d['n_queries']}**, candidate issues: **{d['n_candidates']}** ({d['candidates_per_query']['min']}-{d['candidates_per_query']['max']} per query). "
        f"Label counts (0/1/2): {d['label_counts']['0']}/{d['label_counts']['1']}/{d['label_counts']['2']}. "
        f"Queries with at least one relevant candidate: {d['queries_with_any_relevant_lenient']} (lenient), {d['queries_with_any_relevant_strict']} (strict).", "",
        "Labels by retrieval pool (0/1/2): " + "; ".join(f"{p} {c['0']}/{c['1']}/{c['2']}" for p, c in d.get("label_counts_by_pool", {}).items()) + ".", "",
        f"Evaluated at {s['metadata']['evaluated_at']}. Mean over queries with 95% bootstrap CI in brackets. "
        "Lenient = label >= 1 counts as relevant, strict = label 2 only. nDCG uses the graded labels.", "",
        "| System | Status | P@5 | Recall@5 | nDCG@5 | MRR | P@5 strict | Recall@5 strict | MRR strict |", "|---|---|---|---|---|---|---|---|---|"]
    for name in SYSTEMS:
        sysd = s["systems"][name]
        if sysd["status"] == "ok":
            m = sysd["metrics"]
            lines.append(f"| {LABELS[name]} | ok | " + " | ".join(_fmt(m[k]) for k in ("p@5", "recall@5", "ndcg@5", "mrr", "p@5_strict", "recall@5_strict", "mrr_strict")) + " |")
        else:
            lines.append(f"| {LABELS[name]} | **{sysd['status']}** | " + " | ".join(["-"] * 7) + " |")
    ref = s["systems"].get("random_reference")
    if ref:
        m = ref["metrics"]
        lines.append("| *Random order (expected value, reference)* | ok | " + " | ".join(_fmt(m[k]) for k in ("p@5", "recall@5", "ndcg@5", "mrr", "p@5_strict", "recall@5_strict", "mrr_strict")) + " |")
    orc = s["systems"].get("oracle_reference")
    if orc:
        m = orc["metrics"]
        lines.append("| *Perfect order (upper bound, reference)* | ok | " + " | ".join(_fmt(m[k]) for k in ("p@5", "recall@5", "ndcg@5", "mrr", "p@5_strict", "recall@5_strict", "mrr_strict")) + " |")
    notrun = [(n, s["systems"][n].get("reason")) for n in SYSTEMS if s["systems"][n]["status"] == "not_run"]
    if notrun:
        lines += ["", "## Systems that did not run", ""] + [f"- **{LABELS[n]}**: {r}" for n, r in notrun]
    if s["paired_comparisons"]:
        lines += ["", "## Paired differences (A minus B, per-query, bootstrap 95% CI)", "", "| Comparison | Metric | Mean difference | 95% CI | A better / B better / tie |", "|---|---|---|---|---|"]
        for comp, ms in s["paired_comparisons"].items():
            for metric, r in ms.items():
                if r["mean_diff"] is None:
                    continue
                ci = f"[{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]" if r["ci95"] else "n/a"
                lines.append(f"| {comp.replace('_minus_', ' - ')} | {metric} | {r['mean_diff']:+.3f} | {ci} | {r['queries_a_better']}/{r['queries_b_better']}/{r['ties']} |")
    lines += ["", "Inputs (sha256, first 16 hex): " + ", ".join(f"{k}={v}" for k, v in s["metadata"]["input_hashes_sha256_16"].items()), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", default=",".join(SYSTEMS), help="comma-separated subset of keyword,semantic,hybrid")
    ap.add_argument("--require-all", action="store_true", help="exit with status 1 if any requested system could not run")
    a = ap.parse_args(argv)
    systems = tuple(x.strip() for x in a.systems.split(",") if x.strip())
    if not set(systems) <= set(SYSTEMS):
        ap.error(f"unknown system in {systems}")
    summary = run(systems)
    print((HERE / "results" / "RESULTS.md").read_text(encoding="utf-8"))
    bad = [n for n in systems if summary["systems"][n]["status"] != "ok"]
    return 1 if (bad and a.require_all) else 0


if __name__ == "__main__":
    raise SystemExit(main())
