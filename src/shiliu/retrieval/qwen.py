from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Sequence

import numpy as np

from shiliu.retrieval.dense import DenseModelIdentity, _validate_vector


QWEN_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
QWEN_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN_MODEL_PATH = Path(
    "/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B"
)
QWEN_DIMENSION = 512
QWEN_MAX_TOKENS = 512
QWEN_PROVIDER_VERSION = "v3-qwen3-embedding-provider-v1"
QWEN_EMBEDDING_MODE = "mrl-first-512-normalized"
QWEN_QUERY_INSTRUCTION = (
    "Given a Chinese or English AI and software engineering knowledge retrieval "
    "query, retrieve the most relevant evidence passages."
)
QWEN_QUERY_INSTRUCTION_VERSION = "v3-qwen-query-instruction-v1"
QWEN_INPUT_POLICY_VERSION = "v3-qwen-input-512-v1"
QWEN_PROJECTION_VERSION = "v3-dense-projection-qwen-v1"
QWEN_DENSE_INDEX_VERSION = "v3-dense-qwen3-0.6b-mrl512-v1"


class LocalModelNotReadyError(RuntimeError):
    """The pinned local Qwen snapshot or its offline runtime is unavailable."""


def normalize_embedding_text(text: str) -> str:
    return " ".join(text.split())


def format_qwen_query(query: str) -> str:
    return f"Instruct: {QWEN_QUERY_INSTRUCTION}\nQuery: {query}"


def verify_qwen_snapshot(path: Path, revision: str = QWEN_MODEL_REVISION) -> None:
    if not path.is_absolute():
        raise LocalModelNotReadyError("Qwen model path must be absolute")
    required = (
        "config.json", "config_sentence_transformers.json", "modules.json",
        "model.safetensors", "tokenizer.json", "tokenizer_config.json",
        "1_Pooling/config.json", ".candidate-revision",
    )
    missing = [name for name in required if not (path / name).is_file()]
    if missing:
        raise LocalModelNotReadyError(
            f"local Qwen model is incomplete at {path}; missing: {', '.join(missing)}"
        )
    actual = (path / ".candidate-revision").read_text(encoding="utf-8").strip()
    if actual != revision:
        raise LocalModelNotReadyError(
            f"local Qwen revision mismatch: expected {revision}, got {actual or '<empty>'}"
        )


class QwenEmbeddingProvider:
    """Lazy, process-local, offline-only formal Qwen embedding provider."""

    model_id = QWEN_MODEL_ID
    revision = QWEN_MODEL_REVISION
    dimension = QWEN_DIMENSION
    query_instruction = QWEN_QUERY_INSTRUCTION

    def __init__(self, *, model_path: Path = QWEN_MODEL_PATH) -> None:
        if not isinstance(model_path, Path):
            model_path = Path(model_path)
        if not model_path.is_absolute():
            raise ValueError("Qwen model path must be an absolute local path")
        self.model_path = model_path
        self._model: object | None = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()
        self.load_count = 0
        self.active_device: str | None = None

    def model_identity(self) -> DenseModelIdentity:
        return DenseModelIdentity(
            model_id=self.model_id,
            model_revision=self.revision,
            provider_version=QWEN_PROVIDER_VERSION,
            dimension=self.dimension,
            embedding_mode=QWEN_EMBEDDING_MODE,
            projection_version=QWEN_PROJECTION_VERSION,
            query_instruction_version=QWEN_QUERY_INSTRUCTION_VERSION,
            input_policy_version=QWEN_INPUT_POLICY_VERSION,
            dense_index_version=QWEN_DENSE_INDEX_VERSION,
        )

    def _load(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            verify_qwen_snapshot(self.model_path, self.revision)
            if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get(
                "TRANSFORMERS_OFFLINE"
            ) != "1":
                raise LocalModelNotReadyError(
                    "HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE must both equal 1"
                )
            try:
                import torch
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise LocalModelNotReadyError(
                    "Qwen runtime dependencies are missing; install the 'qwen' extra"
                ) from exc
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            try:
                model = SentenceTransformer(
                    str(self.model_path),
                    local_files_only=True,
                    truncate_dim=self.dimension,
                    processor_kwargs={"padding_side": "left"},
                    device=device,
                )
            except Exception as exc:
                raise LocalModelNotReadyError(
                    f"failed to initialize local Qwen model at {self.model_path}: {exc}"
                ) from exc
            model.max_seq_length = QWEN_MAX_TOKENS
            self._model = model
            self.active_device = device
            self.load_count += 1
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[np.ndarray]:
        if not texts:
            return []
        prepared = [self.prepare_document_text(text) for text in texts]
        for text in prepared:
            if self.count_tokens(text) > QWEN_MAX_TOKENS:
                raise ValueError("document exceeds the 512-token Qwen input policy")
        with self._encode_lock:
            values = self._load().encode(
                prepared, normalize_embeddings=True, truncate_dim=self.dimension,
                batch_size=8, show_progress_bar=False,
            )
        return [_validate_vector(value, self.dimension) for value in values]

    def prepare_document_text(self, text: str) -> str:
        if self.count_tokens(text) <= QWEN_MAX_TOKENS:
            return text
        low, high = 0, self.count_tokens(text, add_special_tokens=False)
        while low < high:
            middle = (low + high + 1) // 2
            candidate = self.truncate_text(text, middle)
            if self.count_tokens(candidate) <= QWEN_MAX_TOKENS:
                low = middle
            else:
                high = middle - 1
        prepared = self.truncate_text(text, low)
        if self.count_tokens(prepared) > QWEN_MAX_TOKENS:
            raise ValueError("unable to enforce the 512-token document input policy")
        return prepared

    def embed_query(self, text: str) -> np.ndarray:
        body = self._truncate_query_body(normalize_embedding_text(text))
        formatted = format_qwen_query(body)
        if self.count_tokens(formatted) > QWEN_MAX_TOKENS:
            raise ValueError("formatted query exceeds the 512-token Qwen input policy")
        with self._encode_lock:
            value = self._load().encode(
                [formatted], normalize_embeddings=True, truncate_dim=self.dimension,
                show_progress_bar=False,
            )[0]
        return _validate_vector(value, self.dimension)

    def count_tokens(self, text: str, *, add_special_tokens: bool = True) -> int:
        return len(
            self._load().tokenizer.encode(text, add_special_tokens=add_special_tokens)
        )

    def truncate_text(self, text: str, max_content_tokens: int) -> str:
        if max_content_tokens < 1:
            return ""
        tokenizer = self._load().tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)[:max_content_tokens]
        return tokenizer.decode(token_ids, skip_special_tokens=True).rstrip()

    def _truncate_query_body(self, body: str) -> str:
        if self.count_tokens(format_qwen_query(body)) <= QWEN_MAX_TOKENS:
            return body
        low, high = 0, self.count_tokens(body, add_special_tokens=False)
        while low < high:
            middle = (low + high + 1) // 2
            candidate = self.truncate_text(body, middle)
            if self.count_tokens(format_qwen_query(candidate)) <= QWEN_MAX_TOKENS:
                low = middle
            else:
                high = middle - 1
        return self.truncate_text(body, low)
