"""Keyword vs semantic vs hybrid comparison using the REAL pretrained model.

    python -m app.ml.compare                       # built-in SYNTHETIC illustration
    python -m app.ml.compare --issues saved.json   # real issues (output of GET /api/issues/search, or a list)
    python -m app.ml.compare --issues saved.json --profile profile.json

The built-in issues are hand-written illustrations (NOT real GitHub data and NOT an evaluation).
The systematic evaluation with human relevance labels is Stage 6. The first run downloads the model
(~90 MB) from Hugging Face, so it needs internet access.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from app.ml.baseline import compare_rankings
from app.ml.embedder import get_embedder
from app.ml.profile import DeveloperProfile
from app.schemas.issues import Issue

DEMO_PROFILE = {"skills": ["Python", "PyTorch"], "domains": ["machine learning"],
                "learning_interests": ["computer vision"], "experience_level": "intermediate"}

_DEMO = [  # (title, body, labels, language)
    ("Training loss becomes NaN after a few epochs", "The optimiser diverges when the learning rate is high; gradients explode.", ["bug"], None),
    ("Add image classification example", "Show how to fine-tune a convolutional network on a small dataset.", ["enhancement", "help wanted"], None),
    ("Update button colours in settings page", "The primary button colour does not match the design system.", ["ui"], None),
    ("Fix typo in installation docs", "There is a spelling mistake in the install guide.", ["documentation", "good first issue"], None),
    ("Support Python 3.13 in CI", "Add Python 3.13 to the test matrix.", ["ci"], "Python"),
    ("Speed up tensor batching", "Collating variable-length samples is slow; consider a faster collate function.", ["performance"], None),
]


def _demo_issues() -> list[Issue]:
    return [Issue(id=i, number=i, title=t, body=b, url=f"https://example.invalid/demo/{i}", state="open", labels=l,
                  created_at="2026-10-01T00:00:00Z", updated_at="2026-11-10T00:00:00Z",
                  repo_full_name="demo/demo", repo_url="https://example.invalid/demo", repo_language=lang)
            for i, (t, b, l, lang) in enumerate(_DEMO, start=1)]


def _load_issues(path: str) -> list[Issue]:
    data = json.load(open(path, encoding="utf-8"))
    items = data["issues"] if isinstance(data, dict) else data
    return [Issue.model_validate(x) for x in items]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issues")
    ap.add_argument("--profile")
    a = ap.parse_args(argv)

    profile = DeveloperProfile.model_validate(json.load(open(a.profile)) if a.profile else DEMO_PROFILE)
    issues = _load_issues(a.issues) if a.issues else _demo_issues()
    if not a.issues:
        print("NOTE: built-in SYNTHETIC illustration, not real GitHub data and not an evaluation.\n")
    try:
        df = compare_rankings(profile, issues, get_embedder(), now=datetime.now(timezone.utc))
    except Exception as exc:  # model download/load problems
        print(f"Could not run the embedding model ({type(exc).__name__}: {exc}).\n"
              "The first run needs internet access to download sentence-transformers/all-MiniLM-L6-v2.", file=sys.stderr)
        return 1
    df["title"] = df["title"].str.slice(0, 45)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
