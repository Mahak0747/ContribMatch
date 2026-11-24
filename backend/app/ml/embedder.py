"""Local sentence-embedding wrapper.

The embedding model is a PRETRAINED, third-party model (default sentence-transformers/all-MiniLM-L6-v2).
This project does not train or fine-tune it. It is loaded lazily, once per process, and embeddings are
cached by text so unchanged issues are never re-encoded.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingModelError(RuntimeError):
    """The embedding model could not be loaded (missing package, no network for first download, ...)."""


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return an (n, dim) float array of L2-normalised vectors, one row per text."""


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
                 batch_size: int = 32, cache_max_items: int = 5000, cache_folder: str | None = None):
        self.model_name = model_name
        self.cache_folder = cache_folder          # where model files live on disk (None = library default)
        self.batch_size = batch_size
        self._cache_max = cache_max_items
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._model = None
        self._lock = threading.Lock()
        self.load_count = 0
        self.cache_hits = 0
        self.cache_misses = 0

    # -- model loading (once) ------------------------------------------------
    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info("Loading embedding model %s", self.model_name)
                    try:
                        from sentence_transformers import SentenceTransformer  # heavy import, lazy
                        kwargs = {"cache_folder": self.cache_folder} if self.cache_folder else {}
                        self._model = SentenceTransformer(self.model_name, **kwargs)
                    except Exception as exc:
                        raise EmbeddingModelError(
                            f"Could not load embedding model '{self.model_name}': {type(exc).__name__}") from exc
                    self.load_count += 1
        return self._model

    def preload(self) -> None:
        self._load()

    # -- cache -----------------------------------------------------------------
    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}\x00{text}".encode()).hexdigest()

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if len(texts) == 0:
            return np.zeros((0, 0), dtype=np.float32)
        keys = [self._key(t) for t in texts]
        missing: dict[str, str] = {}
        for k, t in zip(keys, texts):
            if k in self._cache:
                self.cache_hits += 1
                self._cache.move_to_end(k)
            elif k not in missing:
                missing[k] = t
                self.cache_misses += 1
            else:
                self.cache_hits += 1
        fresh: dict[str, np.ndarray] = {}
        if missing:
            vecs = self._load().encode(
                list(missing.values()), batch_size=self.batch_size,
                normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
            )
            for k, v in zip(missing.keys(), np.asarray(vecs, dtype=np.float32)):
                fresh[k] = v
                self._cache[k] = v
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
        return np.vstack([fresh[k] if k in fresh else self._cache[k] for k in keys])


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformerEmbedder:
    """Process-wide singleton built from settings (the model itself loads on first embed/preload)."""
    from app.core.config import get_settings
    s = get_settings()
    cache = s.model_cache_path
    return SentenceTransformerEmbedder(s.embedding_model, s.embedding_batch_size, s.embedding_cache_max_items,
                                       cache_folder=str(cache) if cache else None)
