# ContribMatch evaluation

A reproducible framework that compares three rankers on the **same** candidate issues for 20 developer profiles,
scored against relevance labels that are kept separate from every model.

## Status: what is done and what is not

| | State |
|---|---|
| 20 diverse developer profiles | done (`evaluation_queries.csv`) |
| 240 real GitHub issues (12 per profile), frozen in `data/candidates.json` | done |
| Relevance labels 0/1/2 for all 240, each with a one-line rationale | done (`relevance_judgments.csv`), **single AI annotator, see below** |
| Metrics code (P@5, Recall@5, nDCG@5, MRR, bootstrap CIs) with unit tests | done |
| Keyword baseline, random and perfect-order references | **computed** (numbers below) |
| **Semantic-only and Hybrid rankings** | **NOT RUN.** They need the pretrained model `all-MiniLM-L6-v2`, which could not be downloaded in the environment where this was built. `evaluate.py` reports them as `not_run` with the reason instead of estimating anything. |

To finish the benchmark, run on a machine with internet access (see "Reproduce").

## Files

| Path | Purpose |
|---|---|
| `evaluation_queries.csv` | the 20 developer profiles |
| `data/candidates.json` | frozen candidate issues per profile (real GitHub data, collection time recorded) |
| `relevance_judgments.csv` | human-style relevance labels, **never read by any ranker** |
| `collect_candidates.py` | how candidates were collected (resumable; `--enrich` adds repo metadata with a token) |
| `metrics.py` | metric functions and bootstrap statistics |
| `evaluate.py` | runs the systems, then scores them against the labels |
| `results/` | `RESULTS.md`, `metrics_summary.json`, `per_query_metrics.csv`, `rankings.csv` (all generated) |

## Dataset

**Profiles.** 20 synthetic personas (not real users): 7 beginner, 9 intermediate, 4 advanced; 12 different domains (web, ML, NLP, systems,
DevOps, mobile, games, security, documentation, CLI tools, developer tools, data science); different languages and learning interests.
One persona (documentation contributor) has no programming language.

**Candidates.** Real open issues (pull requests excluded, unassigned) collected from the GitHub search API at
`2026-11-22T09:09:34.054130+00:00`. For each profile three searches were pooled, ranked by **GitHub's own best-match order, not by any
ContribMatch scorer**: a *specific* search (profile language + domain keyword, 6 issues), a *broad* search (language only, 4)
and a *distractor* search (an unrelated language/keyword, 2), using labels suited to the profile's level.
That gives 240 candidate rows (12 per profile); some issues appear for several profiles. Candidate order was shuffled with a fixed seed.
The pool tag is stored for after-the-fact analysis only and was hidden while labelling.
Repository metadata (description, language, stars, last push) was **not** collected (see Limitations).

## How relevance labels were assigned

**Annotator.** All 240 labels were assigned by one annotator, **the AI assistant (Claude) that built this project**, by reading each issue against its
profile. They are *not* independent human judgments and have no inter-annotator agreement. **Please review them**: every row has a
`rationale`, and the file can be edited and `evaluate.py` re-run.

**Evidence shown.** Title, labels, repository name and the first ~240-340 characters of the cleaned description (the ranking systems see up to 1000 characters).
Repository language and stars were not available to the annotator, so a label only counts a language/framework match that is visible in the text.

**Rubric.**
- **2 Highly relevant:** the main deliverable uses the profile's core skills or language and fits its domain, and the scope suits the experience level.
- **1 Partially relevant:** matches part of the profile (same language but another domain, same domain but another language, a stated learning interest, or
  testing/documentation work around the right stack), **or** a good topical match with a clear level mismatch (for example a
  `hard` issue for a beginner or a trivial "good first issue" for an advanced developer).
- **0 Not relevant:** unrelated stack or domain, no visible link to the profile, or no description to judge by.

**Order of work.** All labels were written before any system was scored; no ranking output was seen while labelling.
The annotator did know the pooling design (specific / broad / distractor), although individual pool tags were hidden.

Resulting label counts (0 / 1 / 2): **61 / 87 / 92**.
By pool: specific 5/51/64, broad 18/35/27, distractor 38/1/1.

## Systems compared (same candidates for each)

1. **Keyword baseline:** share of all profile terms (skills, languages, domains, interests) literally present in the issue text (`app.ml.baseline.keyword_score`).
2. **Semantic only:** raw cosine similarity of profile and issue embeddings from the pretrained `all-MiniLM-L6-v2` model.
3. **Hybrid:** the full ContribMatch score (45% semantic, 20% skill, 15% experience, 10% activity, 10% beginner friendliness).

Ties are broken the same way everywhere (most recently updated, then lower issue id). Activity scores use the collection time as "now", so results do not drift.
Two non-system references are reported: a **random ordering** (expected values over 1000 seeded shuffles per profile) and a **perfect ordering** (upper bound).

## Metrics

Computed per profile over the full ranking of its candidates, then averaged over profiles; 95% CIs are percentile bootstrap over profiles (10,000 resamples, fixed seed).
- **Precision@5:** relevant items in the top 5 / 5.
- **Recall@5:** relevant items in the top 5 / all relevant candidates **in the pool** (not all relevant issues on GitHub).
- **nDCG@5:** graded labels, gain 2^label - 1, log2 discount, ideal ordering over the candidates.
- **MRR:** mean of 1 / rank of the first relevant candidate.
- *Lenient* counts label >= 1 as relevant; *strict* counts only label 2. nDCG always uses the graded labels.
- Paired per-profile differences between systems (with bootstrap CIs) are written to `results/metrics_summary.json` once two systems have run.

## Results actually computed so far

Generated by `python evaluation/evaluate.py` (see `results/RESULTS.md`). 20 profiles, mean [95% CI].

| System | P@5 | Recall@5 | nDCG@5 | MRR | P@5 strict | Recall@5 strict | MRR strict |
|---|---|---|---|---|---|---|---|
| Keyword baseline | 0.930 [0.86, 0.98] | 0.521 [0.49, 0.55] | 0.781 [0.71, 0.85] | 0.950 [0.88, 1.00] | 0.610 [0.50, 0.71] | 0.685 [0.60, 0.77] | 0.787 [0.66, 0.90] |
| *Random order (expected)* | 0.746 [0.70, 0.79] | 0.417 [0.42, 0.42] | 0.544 [0.52, 0.58] | 0.863 [0.83, 0.89] | 0.381 [0.32, 0.44] | 0.414 [0.41, 0.42] | 0.594 [0.53, 0.65] |
| *Perfect order (upper bound)* | 1.000 | 0.570 [0.53, 0.61] | 1.000 | 1.000 | 0.830 [0.71, 0.93] | 0.936 [0.88, 0.98] | 1.000 |
| Semantic similarity only | *not run* | | | | | | |
| Hybrid | *not run* | | | | | | |

How to read this honestly:
- **Lenient P@5 and Recall@5 are close to their ceilings** (random 0.75; perfect-order Recall@5 is only 0.57 because every profile has 6 to 10 relevant
  candidates, more than the 5 slots). They barely separate systems. Prefer nDCG@5, strict P@5 and strict MRR.
- The keyword baseline beats random order clearly on nDCG@5 and strict P@5, but it is **not** a weak baseline here, for the reasons under "Bias toward lexical matching".
- **No claim is made about semantic or hybrid ranking.** There are no numbers for them yet.

## Reproduce

```bash
cd backend
pip install -r requirements-dev.txt          # includes sentence-transformers / torch and pytest
python evaluation/evaluate.py                # all systems; first run downloads the model (~90 MB)
python evaluation/evaluate.py --systems keyword      # no model needed
python evaluation/evaluate.py --require-all  # exit status 1 if a system could not run
pytest tests/test_evaluation.py              # tests for metrics, pipeline and dataset integrity
```
Reproducibility is numerical, not bitwise: running the keyword evaluation on Python 3.11 and 3.12 gave values that differ by at most 3e-15 (Python 3.12 sums floats with a compensated algorithm), and identical rankings. Inputs are fixed files, so results depend only on the model version (recorded in `metrics_summary.json` with data hashes and package versions).
To re-collect candidates (about 7 minutes, unauthenticated): `python evaluation/collect_candidates.py` (this changes the data, so labels must be redone).
With a `GITHUB_TOKEN`, `--enrich` adds repository metadata; the existing labels do not depend on it, but the dataset hash changes.

## Limitations

- **Small sample.** 20 profiles, 240 judged issues. Confidence intervals are wide; differences of a few points are not meaningful. No multiple-comparison correction is applied.
- **Single, non-independent annotator** (an AI assistant). Labels are judgment calls from short excerpts; no inter-annotator agreement; possible systematic bias.
- **Bias toward lexical matching.** Candidates were retrieved by keyword/language searches and labelled from visible text, both of which reward literal term overlap. This
  favours the keyword baseline and can understate semantic methods, especially their ability to match paraphrases.
- **Easy negatives and dense relevance.** 75% of candidates have label >= 1, and distractors are almost always label 0. The task is easier than ranking a
  realistic mixed feed, which inflates every system's lenient scores.
- **Hybrid is evaluated with degraded inputs.** Without repository metadata, activity uses only the issue's update time, language matching cannot use the repository's
  language, and "skills to learn" cannot use the repository description. Production recommendations have these fields, so hybrid results here are not a full
  measure of the production system.
- **Recall is relative to a 12-issue pool**, not to GitHub.
- **Snapshot in time and English-heavy.** Issues change or close; a few candidates are in other languages (Thai, German, Russian, Chinese), which are hard to judge.
- **Synthetic personas**, not real developers. Level, interests and "relevance" are as imagined by the annotator.
- **Untuned design constants.** The cosine calibration and component weights were fixed beforehand and are not tuned on this data; do not tune them on these
  same labels and then report the result as a test score.

## What remains

1. Run `python evaluation/evaluate.py` with network access to produce the semantic and hybrid numbers (the harness and tests are ready).
2. Have at least one independent human re-label (or spot-check) the judgments; report agreement.
3. Re-collect with `--enrich` (token required) to evaluate hybrid with full repository metadata.
4. Grow the benchmark (more profiles, harder negatives, candidates not retrieved by keyword search) before drawing conclusions.
