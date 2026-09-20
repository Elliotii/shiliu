from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from shiliu.app import Application
from shiliu.retrieval.qwen import (
    LocalModelNotReadyError,
    QWEN_DIMENSION,
    QWEN_MAX_TOKENS,
    QWEN_QUERY_INSTRUCTION,
    QwenEmbeddingProvider,
    format_qwen_query,
)


class FakeTokenizer:
    def encode(self, text, add_special_tokens=True):
        values = list(text.encode("utf-8"))
        return ([1] + values + [2]) if add_special_tokens else values

    def decode(self, values, skip_special_tokens=True):
        return bytes(values).decode("utf-8", errors="ignore")


class FakeSentenceTransformer:
    instances = []

    def __init__(self, path, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.tokenizer = FakeTokenizer()
        self.max_seq_length = None
        self.calls = []
        self.__class__.instances.append(self)

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        vectors = []
        for text in texts:
            vector = np.zeros(QWEN_DIMENSION, dtype=np.float32)
            for index, value in enumerate(text.encode("utf-8")):
                vector[index % QWEN_DIMENSION] += value + 1
            vector[0] += 1
            vectors.append(vector / np.linalg.norm(vector))
        return np.asarray(vectors, dtype=np.float32)


def model_path(tmp_path: Path) -> Path:
    for name in (
        "config.json", "config_sentence_transformers.json", "modules.json",
        "model.safetensors", "tokenizer.json", "tokenizer_config.json",
        "1_Pooling/config.json",
    ):
        target = tmp_path / "model" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    (tmp_path / "model" / ".candidate-revision").write_text(
        "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3", encoding="utf-8"
    )
    return tmp_path / "model"


@pytest.fixture
def fake_runtime(monkeypatch):
    FakeSentenceTransformer.instances.clear()
    monkeypatch.setitem(
        sys.modules, "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setitem(
        sys.modules, "torch",
        SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))),
    )
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


def test_absolute_local_path_required_and_remote_repo_rejected() -> None:
    with pytest.raises(ValueError, match="absolute local path"):
        QwenEmbeddingProvider(model_path=Path("Qwen/Qwen3-Embedding-0.6B"))


def test_application_reuses_one_lazy_provider_instance(app_paths) -> None:
    application = Application(app_paths)
    assert application._dense_retrieval is None
    first = application.dense_retrieval
    second = application.dense_retrieval
    assert first is second
    assert isinstance(first.provider, QwenEmbeddingProvider)
    assert first.provider.load_count == 0


def test_missing_snapshot_and_offline_environment_are_structured(tmp_path, monkeypatch) -> None:
    provider = QwenEmbeddingProvider(model_path=tmp_path / "missing")
    with pytest.raises(LocalModelNotReadyError, match="incomplete"):
        provider.embed_query("MCP")
    path = model_path(tmp_path)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    with pytest.raises(LocalModelNotReadyError, match="must both equal 1"):
        QwenEmbeddingProvider(model_path=path).embed_query("MCP")


def test_lazy_single_load_query_document_separation_and_vector_contract(
    tmp_path, fake_runtime
) -> None:
    provider = QwenEmbeddingProvider(model_path=model_path(tmp_path))
    assert provider.load_count == 0 and FakeSentenceTransformer.instances == []
    document = "Document\nkeeps its projection formatting"
    document_vector = provider.embed_documents([document])[0]
    query_vector = provider.embed_query("  MCP   协议  ")
    assert provider.load_count == 1 and len(FakeSentenceTransformer.instances) == 1
    assert provider.active_device == "cpu"
    model = FakeSentenceTransformer.instances[0]
    assert model.calls[0][0] == [document]
    assert model.calls[1][0] == [format_qwen_query("MCP 协议")]
    assert model.calls[1][0][0].startswith(f"Instruct: {QWEN_QUERY_INSTRUCTION}\nQuery: ")
    for vector in (document_vector, query_vector):
        assert vector.dtype == np.float32 and vector.shape == (QWEN_DIMENSION,)
        assert np.isfinite(vector).all() and np.linalg.norm(vector) == pytest.approx(1.0)


def test_long_query_keeps_instruction_and_is_deterministically_truncated(
    tmp_path, fake_runtime
) -> None:
    provider = QwenEmbeddingProvider(model_path=model_path(tmp_path))
    provider.embed_query("x" * 2000)
    formatted = FakeSentenceTransformer.instances[0].calls[-1][0][0]
    assert formatted.startswith(f"Instruct: {QWEN_QUERY_INSTRUCTION}\nQuery: ")
    assert provider.count_tokens(formatted) <= QWEN_MAX_TOKENS
    first = formatted
    provider.embed_query("x" * 2000)
    assert FakeSentenceTransformer.instances[0].calls[-1][0][0] == first


def test_non_finite_formal_output_is_rejected(tmp_path, fake_runtime) -> None:
    provider = QwenEmbeddingProvider(model_path=model_path(tmp_path))
    model = provider._load()
    model.encode = lambda texts, **kwargs: np.full(
        (len(texts), QWEN_DIMENSION), np.nan, dtype=np.float32
    )
    with pytest.raises(ValueError, match="finite"):
        provider.embed_query("MCP")


def test_document_budget_is_explicitly_truncated_and_missing_dependency_is_structured(
    tmp_path, fake_runtime, monkeypatch
) -> None:
    provider = QwenEmbeddingProvider(model_path=model_path(tmp_path))
    provider.embed_documents(["x" * 600])
    submitted = FakeSentenceTransformer.instances[0].calls[-1][0][0]
    assert provider.count_tokens(submitted) <= QWEN_MAX_TOKENS
    provider = QwenEmbeddingProvider(model_path=model_path(tmp_path))
    monkeypatch.delitem(sys.modules, "sentence_transformers")
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(LocalModelNotReadyError, match="dependencies are missing"):
        provider.embed_query("MCP")
