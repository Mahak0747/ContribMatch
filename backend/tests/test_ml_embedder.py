import sys
import types

import numpy as np
import pytest

from app.ml.embedder import SentenceTransformerEmbedder, get_embedder


class FakeST:
    instances = 0
    encode_calls: list = []
    init_kwargs: dict = {}

    def __init__(self, name, **kwargs):
        FakeST.instances += 1
        self.name = name
        FakeST.init_kwargs = kwargs

    def encode(self, texts, batch_size, normalize_embeddings, convert_to_numpy, show_progress_bar):
        FakeST.encode_calls.append((list(texts), batch_size, normalize_embeddings))
        return np.array([[float(len(t)), 1.0] for t in texts]) / 10


@pytest.fixture()
def fake_st(monkeypatch):
    FakeST.instances, FakeST.encode_calls = 0, []
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    return FakeST


def test_model_not_loaded_until_needed_and_loaded_once(fake_st):
    e = SentenceTransformerEmbedder("m")
    assert fake_st.instances == 0
    e.embed(["a"]); e.embed(["b"]); e.preload()
    assert fake_st.instances == 1 and e.load_count == 1


def test_single_batched_encode_with_normalisation(fake_st):
    e = SentenceTransformerEmbedder("m", batch_size=16)
    out = e.embed([f"text {i}" for i in range(10)])
    assert out.shape == (10, 2)
    assert len(fake_st.encode_calls) == 1
    texts, bs, norm = fake_st.encode_calls[0]
    assert len(texts) == 10 and bs == 16 and norm is True


def test_cache_skips_unchanged_texts(fake_st):
    e = SentenceTransformerEmbedder("m")
    first = e.embed(["alpha", "beta"])
    second = e.embed(["beta", "gamma", "alpha"])
    assert [c[0] for c in fake_st.encode_calls] == [["alpha", "beta"], ["gamma"]]
    assert np.allclose(second[0], first[1]) and np.allclose(second[2], first[0])
    assert e.cache_hits == 2 and e.cache_misses == 3


def test_duplicate_texts_in_one_call_encoded_once(fake_st):
    e = SentenceTransformerEmbedder("m")
    out = e.embed(["same", "same", "same"])
    assert len(fake_st.encode_calls[0][0]) == 1 and out.shape[0] == 3


def test_cache_key_depends_on_model_name(fake_st):
    a, b = SentenceTransformerEmbedder("m1"), SentenceTransformerEmbedder("m2")
    assert a._key("x") != b._key("x")


def test_small_cache_still_returns_all_rows(fake_st):
    e = SentenceTransformerEmbedder("m", cache_max_items=2)
    assert e.embed([f"t{i}" for i in range(6)]).shape == (6, 2)


def test_empty_input(fake_st):
    assert SentenceTransformerEmbedder("m").embed([]).shape[0] == 0
    assert fake_st.instances == 0


def test_get_embedder_is_singleton():
    get_embedder.cache_clear()
    assert get_embedder() is get_embedder()
    assert get_embedder().model_name == "sentence-transformers/all-MiniLM-L6-v2"
    get_embedder.cache_clear()


def test_model_cache_folder_is_passed_only_when_configured(fake_st):
    SentenceTransformerEmbedder("m").preload()
    assert fake_st.init_kwargs == {}
    SentenceTransformerEmbedder("m", cache_folder="/data/models").preload()
    assert fake_st.init_kwargs == {"cache_folder": "/data/models"}


def test_get_embedder_uses_the_configured_cache_folder(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("MODEL_CACHE_DIR", "/models")
    get_settings.cache_clear(); get_embedder.cache_clear()
    try:
        assert get_embedder().cache_folder == "/models"
    finally:
        get_settings.cache_clear(); get_embedder.cache_clear()
