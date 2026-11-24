"""TEST DOUBLES ONLY. These are NOT the real embedding model and say nothing about its quality."""
import re
from datetime import datetime, timezone

import numpy as np

from app.schemas.issues import Issue

NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)

CONCEPTS = {
    "ml": {"machine", "learning", "neural", "network", "networks", "training", "trainer", "pytorch", "tensorflow",
           "model", "models", "deep", "gradient", "ml", "tensor"},
    "web": {"web", "frontend", "html", "css", "react", "browser", "ui", "javascript", "component", "dom"},
    "devops": {"docker", "kubernetes", "container", "deploy", "pipeline", "terraform"},
    "docs": {"documentation", "docs", "typo", "readme"},
}
_NAMES = list(CONCEPTS)
HASH_DIM = 64


class ConceptEmbedder:
    """Deterministic: words in the same hand-written concept group map to the same dimension;
    other words fall into hashed buckets (tiny weight)."""
    model_name = "test-concept-embedder"

    def __init__(self):
        self.calls = 0
        self.texts_seen = 0

    def embed(self, texts):
        self.calls += 1
        self.texts_seen += len(texts)
        out = np.zeros((len(texts), len(_NAMES) + HASH_DIM), dtype=np.float32)
        for r, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9+#.]+", t.lower()):
                hit = False
                for k, name in enumerate(_NAMES):
                    if w in CONCEPTS[name]:
                        out[r, k] += 1.0
                        hit = True
                if not hit:
                    out[r, len(_NAMES) + (sum(map(ord, w)) % HASH_DIM)] += 0.05
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return out / norms


def make_issue(i=1, title="Some issue", body="", labels=(), lang=None, repo_desc=None, comments=0,
               stars=100, pushed="2026-11-15T00:00:00Z", updated="2026-11-18T00:00:00Z", repo="o/r"):
    return Issue(
        id=i, number=i, title=title, body=body, url=f"https://github.com/{repo}/issues/{i}", state="open",
        labels=list(labels), comments=comments, created_at="2026-10-01T00:00:00Z", updated_at=updated,
        repo_full_name=repo, repo_url=f"https://github.com/{repo}", repo_description=repo_desc,
        repo_language=lang, repo_stars=stars, repo_pushed_at=pushed,
    )
