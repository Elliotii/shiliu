from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RuntimeMode = Literal["product_runtime", "frozen_eval_runtime"]


@dataclass(frozen=True)
class ProductRuntimeConfig:
    runtime_mode: Literal["product_runtime"]
    corpus_identity: str
    sync_allowed: bool
    mutable_index_allowed: bool


PRODUCT_RUNTIME_CONFIG = ProductRuntimeConfig(
    runtime_mode="product_runtime",
    corpus_identity="shiliu-live-current",
    sync_allowed=True,
    mutable_index_allowed=True,
)
