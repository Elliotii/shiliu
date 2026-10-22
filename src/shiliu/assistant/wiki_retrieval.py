"""Rebuildable, block-addressed Wiki retrieval; SQLite Wiki owns visibility."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any

import jieba
import numpy as np

from shiliu.retrieval.qwen import QWEN_MAX_TOKENS

WIKI_QUERY_INSTRUCTION = (
    "Given a Chinese or English knowledge or personal experience query, "
    "retrieve relevant knowledge passages, including applicable conditions and personal notes."
)
PROJECTION_VERSION = "wiki-block-windows-v1"


class WikiHybridIndex:
    def __init__(self, provider: Any, cache_path: Path | None = None) -> None:
        self.provider = provider
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._vectors: dict[str, np.ndarray] = {}
        self._windows: dict[str, list[dict[str, Any]]] = {}
        self._tokenizer = jieba.Tokenizer()

    def tokens(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return [word for word in self._tokenizer.cut(normalized, HMM=False)
                if re.search(r"[\w\u4e00-\u9fff]", word)]

    def _block_windows(self, page: dict, block: dict) -> list[dict]:
        # Hash the effective projection, never a hidden/raw block representation.
        text = str(block.get("markdown") or "")
        prefix = "\n".join([str(page["title"]), " ".join(page.get("aliases") or []),
                             str(block.get("heading") or ""), str(block.get("applicability") or "")])
        key = hashlib.sha256((prefix + "\0" + text).encode()).hexdigest()
        if key in self._windows:
            return self._windows[key]
        prefix = self.provider.truncate_text(prefix, 120)
        windows = []
        start = 0
        while start < len(text):
            low, high = start + 1, min(len(text), start + 2000)
            while low < high:
                end = (low + high + 1) // 2
                if self.provider.count_tokens(prefix + "\n" + text[start:end]) <= QWEN_MAX_TOKENS:
                    low = end
                else:
                    high = end - 1
            end = low
            represented = prefix + "\n" + text[start:end]
            if self.provider.count_tokens(represented) > QWEN_MAX_TOKENS:
                raise ValueError("wiki_window_input_too_large")
            windows.append({"text": represented, "start": start, "end": end})
            if end == len(text):
                break
            start = max(start + 1, end - min(80, (end - start) // 5))
        if not windows:
            windows = [{"text": prefix, "start": 0, "end": 0}]
        self._windows[key] = windows
        return windows

    def _cached_vectors(self, entries: list[dict]) -> int:
        identity = self.provider.model_identity()
        model = vars(identity) if hasattr(identity, "__dict__") else str(identity)
        connection = None
        try:
            if self.cache_path is not None:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(self.cache_path, timeout=5)
                connection.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector BLOB NOT NULL)")
            missing: dict[str, str] = {}
            for entry in entries:
                key = hashlib.sha256(json.dumps(
                    [PROJECTION_VERSION, model, entry["page_id"], entry["block_id"], entry["text"]],
                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                entry["vector_key"] = key
                if key not in self._vectors and connection is not None:
                    row = connection.execute("SELECT vector FROM vectors WHERE key=?", (key,)).fetchone()
                    if row:
                        value = np.frombuffer(row[0], dtype=np.float32).copy()
                        if value.shape == (self.provider.dimension,) and np.isfinite(value).all() and np.isclose(np.linalg.norm(value), 1, atol=.01):
                            self._vectors[key] = value
                if key not in self._vectors:
                    missing[key] = entry["text"]
            keys = list(missing)
            for offset in range(0, len(keys), 8):
                batch = keys[offset:offset + 8]
                vectors = self.provider.embed_documents([missing[key] for key in batch])
                for key, vector in zip(batch, vectors, strict=True):
                    value = np.asarray(vector, dtype=np.float32)
                    if value.shape != (self.provider.dimension,) or not np.isfinite(value).all():
                        raise ValueError("wiki_embedding_invalid")
                    norm = float(np.linalg.norm(value))
                    if norm <= 0:
                        raise ValueError("wiki_embedding_invalid")
                    value = value / norm
                    self._vectors[key] = value
                    if connection is not None:
                        connection.execute("INSERT OR REPLACE INTO vectors VALUES (?,?)", (key, value.tobytes()))
            if connection is not None:
                connection.commit()
            return len(keys)
        finally:
            if connection is not None:
                connection.close()

    def search(self, pages: list[dict], query: str, *, limit: int = 3) -> dict:
        started = time.monotonic()
        with self._lock:
            return self._search(pages, query, limit, started)

    def _search(self, pages: list[dict], query: str, limit: int, started: float) -> dict:
        blocks = [(page, block) for page in pages for block in page["blocks"]]
        terms = self.tokens(query)
        entries, error = [], None
        try:
            for index, (page, block) in enumerate(blocks):
                entries.extend({**window, "index": index, "page_id": page["id"], "block_id": block["stable_id"]}
                               for window in self._block_windows(page, block))
        except Exception as exc:
            error = {"error_code": type(exc).__name__, "message": str(exc)[:250], "retryable": True}
            # A failed Dense runtime does not suppress available lexical results.
            entries = [{"index": index, "start": start, "end": min(start + 512, len(str(block.get("markdown") or "")))}
                       for index, (_, block) in enumerate(blocks)
                       for start in range(0, max(1, len(str(block.get("markdown") or ""))), 450)]
        docs = []
        for entry in entries:
            page, block = blocks[entry["index"]]
            title = " ".join([page["title"], *(page.get("aliases") or []), str(block.get("heading") or "")])
            body = str(block.get("markdown") or "")[entry["start"]:entry["end"]]
            docs.append(Counter(self.tokens(title) * 3 + self.tokens(str(block.get("applicability") or "")) * 2 + self.tokens(body)))
        avg = sum(sum(doc.values()) for doc in docs) / max(1, len(docs)) or 1
        frequency = Counter(term for doc in docs for term in doc)
        lexical_best, lexical_positions = {}, {}
        for entry, doc in zip(entries, docs):
            index = entry["index"]
            page, block = blocks[index]
            score = 0.0
            for term in set(terms):
                tf = doc[term]
                if tf:
                    idf = math.log(1 + (len(docs) - frequency[term] + .5) / (frequency[term] + .5))
                    score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * sum(doc.values()) / avg))
            exact = unicodedata.normalize("NFKC", query).casefold().strip()
            if exact and any(exact in str(value).casefold() for value in
                             [page["title"], *(page.get("aliases") or []), block.get("heading", "")]):
                score += 3
            if score > 0 and score > lexical_best.get(index, 0):
                lexical_best[index] = score
                lexical_positions[index] = {"start": entry["start"], "end": entry["end"]}
        lexical = list(lexical_best.items())
        lexical.sort(key=lambda item: (-item[1], blocks[item[0]][0]["id"], blocks[item[0]][1]["stable_id"]))
        lexical = lexical[:20]
        dense, positions, encoded = [], {}, 0
        if blocks and error is None:
            try:
                encoded = self._cached_vectors(entries)
                vector = self.provider.embed_query(query, instruction=WIKI_QUERY_INSTRUCTION)
                best = {}
                for entry in entries:
                    score = float(np.dot(self._vectors[entry["vector_key"]], vector))
                    index = entry["index"]
                    if index not in best or score > best[index]:
                        best[index] = score
                        positions[index] = {"start": entry["start"], "end": entry["end"]}
                dense = sorted(best.items(), key=lambda item: (-item[1], item[0]))[:20]
            except Exception as exc:
                error = {"error_code": type(exc).__name__, "message": str(exc)[:250], "retryable": True}
        ranks: dict[int, dict] = {}
        for channel, values in (("lexical", lexical), ("dense", dense)):
            for rank, (index, _) in enumerate(values, 1):
                ranks.setdefault(index, {})[channel] = rank
        ordered = sorted(ranks, key=lambda index: (-sum(1 / (60 + rank) for rank in ranks[index].values()), index))
        candidates: dict[str, dict] = {}
        for index in ordered:
            page, block = blocks[index]
            page_id = str(page["id"])
            if page_id not in candidates:
                if len(candidates) >= limit:
                    continue
                candidates[page_id] = {"page_id": page_id, "page_version": page["version"], "version": page["version"],
                                       "title": page["title"], "availability": page["availability"], "hits": []}
            hits = candidates[page_id]["hits"]
            if len(hits) >= 3:
                continue
            text = str(block.get("markdown") or "")
            position = lexical_positions.get(index) if ranks[index].get("lexical") else positions.get(index)
            position = position or {"start": 0, "end": min(240, len(text))}
            directory_only = bool(ranks[index].get("lexical")) and not any(
                term in (text + str(block.get("heading") or "") + str(block.get("applicability") or "")).casefold()
                for term in terms)

            if ranks[index].get("lexical"):
                offsets = [text.casefold().find(term) for term in terms if term in text.casefold()]
                if offsets:
                    position = {"start": max(0, min(offsets) - 60), "end": min(len(text), min(offsets) + 180)}
            hits.append({"block_id": block["stable_id"], "heading": block.get("heading", ""),
                         "role": block.get("role") or ("personal" if block.get("assessment") == "user_explicit" else
                                                       "analysis" if block.get("assessment") == "system_synthesis" else "source"),
                         "assessment": block.get("assessment"), "match_kind": "page_directory" if directory_only else "block_candidate",
                         "candidate_excerpt": "" if directory_only else text[position["start"]:position["end"]][:240],
                         "position": {} if directory_only else position, "ranks": ranks[index]})
        return {"source": "wiki", "status": "partial" if error else "ok" if candidates else "empty",
                "candidates": list(candidates.values()),
                "coverage": {"query": query, "exhaustive": False, "candidate_count": len(candidates),
                             "valid_blocks": len(blocks), "lexical_candidates": len(lexical), "dense_candidates": len(dense),
                             "encoded_windows": encoded, "retrieval_method": "bm25" if error else "hybrid", "rrf_k": 60,
                             "elapsed_ms": round((time.monotonic() - started) * 1000)}, **(error or {})}
