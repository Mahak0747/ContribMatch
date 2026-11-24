"""Ranking metrics and bootstrap statistics. Pure Python, no project imports.

`ranked_rels` is the list of graded relevance labels (0/1/2) of ALL candidates in ranked order.
A candidate counts as relevant when its label >= `threshold` (1 = lenient: partially or highly relevant,
2 = strict: highly relevant only). Metrics that are undefined for a query (it has no relevant candidate)
return None and are excluded from the mean (the number of queries used is reported).
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence


def _gain(rel: int) -> float:
    return 2.0 ** rel - 1.0


def _dcg(rels: Sequence[int]) -> float:
    return sum(_gain(r) / math.log2(i + 2) for i, r in enumerate(rels))


def precision_at_k(ranked_rels: Sequence[int], k: int, threshold: int = 1) -> float:
    """Relevant items in the top k divided by k."""
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / k


def recall_at_k(ranked_rels: Sequence[int], k: int, threshold: int = 1) -> float | None:
    """Relevant items in the top k divided by ALL relevant candidates for the query (None if there are none)."""
    total = sum(1 for r in ranked_rels if r >= threshold)
    if total == 0:
        return None
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / total


def ndcg_at_k(ranked_rels: Sequence[int], k: int) -> float | None:
    """Graded nDCG with gain 2^rel - 1 and log2 discount; ideal ordering is taken over all candidates."""
    ideal = _dcg(sorted(ranked_rels, reverse=True)[:k])
    if ideal == 0:
        return None
    return _dcg(ranked_rels[:k]) / ideal


def reciprocal_rank(ranked_rels: Sequence[int], threshold: int = 1) -> float | None:
    """1 / rank of the first relevant candidate over the whole ranking (None if no candidate is relevant)."""
    for i, r in enumerate(ranked_rels, start=1):
        if r >= threshold:
            return 1.0 / i
    return None


def mean(values: Sequence[float | None]) -> tuple[float | None, int]:
    """Mean of the defined values and how many there were."""
    v = [x for x in values if x is not None]
    return (sum(v) / len(v) if v else None), len(v)


def bootstrap_ci(values: Sequence[float], n_boot: int = 10_000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float] | None:
    """Percentile bootstrap confidence interval of the mean (resampling queries)."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int((alpha / 2) * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1]


def paired_difference(a: dict[str, float | None], b: dict[str, float | None], n_boot: int = 10_000, seed: int = 0) -> dict:
    """Mean of (a - b) over queries where both are defined, with a bootstrap CI over those queries."""
    diffs = [a[q] - b[q] for q in a if q in b and a[q] is not None and b[q] is not None]
    if not diffs:
        return {"mean_diff": None, "ci95": None, "n": 0}
    ci = bootstrap_ci(diffs, n_boot=n_boot, seed=seed)
    return {"mean_diff": sum(diffs) / len(diffs), "ci95": list(ci) if ci else None, "n": len(diffs),
            "queries_a_better": sum(d > 0 for d in diffs), "queries_b_better": sum(d < 0 for d in diffs),
            "ties": sum(d == 0 for d in diffs)}
