"""Reusable F1 transcript retrieval primitives (no evaluation state)."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import threading
import unicodedata

import jieba

from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.orchestrator import RawSearchHit
from shiliu.retrieval.service import RetrievalService


class F1Tokenizer:
    def __init__(self) -> None:
        self.engine = jieba.Tokenizer(str(Path(jieba.__file__).with_name("dict.txt")))
        self.engine.initialize()

    def tokens(self, value: str) -> list[str]:
        result: list[str] = []
        for word in self.engine.cut(unicodedata.normalize("NFKC", value).casefold(), HMM=False):
            run = ""
            for character in word:
                category = unicodedata.category(character)
                if category[0] in "LN" or category == "Co":
                    run += character
                elif run:
                    result.append(run)
                    run = ""
            if run:
                result.append(run)
        return result

    def query(self, value: str) -> str:
        return " OR ".join('"' + term.replace('"', '""') + '"' for term in dict.fromkeys(self.tokens(value)))


class F1LexicalIndex:
    """Independent FTS file with source DB attached read only per search."""

    def __init__(self, path: Path, source_db: Path, tokenizer: F1Tokenizer | None = None) -> None:
        self.path, self.source_db = Path(path).resolve(), Path(source_db).resolve()
        self.tokenizer = tokenizer or F1Tokenizer()
        self._validated = False
        self._validation_lock = threading.Lock()

    def build(self) -> dict[str, str | int]:
        """Explicit offline build; the caller owns index lifecycle and atomic replacement."""
        if self.path.exists():
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.source_db.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(self.path) as target:
            source.row_factory = sqlite3.Row
            target.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, unit_id TEXT UNIQUE NOT NULL, content_hash TEXT NOT NULL)")
            target.execute("CREATE VIRTUAL TABLE body_fts USING fts5(body, tokenize='unicode61 remove_diacritics 1')")
            target.execute("CREATE TABLE identity (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            digest = sha256()
            count = 0
            for count, row in enumerate(source.execute("SELECT unit_id,source_text,content_hash FROM retrieval_units WHERE unit_type='transcript_chunk' ORDER BY unit_id"), 1):
                target.execute("INSERT INTO docs VALUES (?,?,?)", (count, row["unit_id"], row["content_hash"]))
                target.execute("INSERT INTO body_fts(rowid,body) VALUES (?,?)", (count, " ".join(self.tokenizer.tokens(row["source_text"]))))
                digest.update((row["unit_id"] + "\0" + row["content_hash"] + "\n").encode())
            target.execute("INSERT INTO body_fts(body_fts) VALUES ('optimize')")
            target.executemany("INSERT INTO identity VALUES (?,?)", [("content_sha256", digest.hexdigest()), ("unit_count", str(count))])
        return {"content_sha256": digest.hexdigest(), "unit_count": count}

    def sync_video(self, video_id: int) -> None:
        """Reuse the existing coordinator's per-video post-commit update boundary."""
        if not self.path.exists():
            return
        with self._validation_lock, sqlite3.connect(self.path.as_uri(), uri=True) as index, sqlite3.connect(
                self.source_db.as_uri() + "?mode=ro", uri=True) as source:
            source.row_factory = sqlite3.Row
            index.row_factory = sqlite3.Row
            index.execute("ATTACH DATABASE ? AS corpus", (self.source_db.as_uri() + "?mode=ro",))
            columns = {row[1] for row in index.execute("PRAGMA table_info(docs)")}
            if "content_hash" not in columns:
                raise ValueError("F1 companion needs explicit rebuild to track indexed content identity")
            if "video_id" not in columns:
                index.execute("ALTER TABLE docs ADD COLUMN video_id INTEGER")
                index.execute("UPDATE docs SET video_id=(SELECT u.video_id FROM corpus.retrieval_units u WHERE u.unit_id=docs.unit_id)")
            old = list(index.execute("SELECT id FROM docs WHERE video_id=? OR unit_id NOT IN (SELECT unit_id FROM corpus.retrieval_units)", (video_id,)))
            for (identity,) in old:
                index.execute("DELETE FROM body_fts WHERE rowid=?", (identity,))
                index.execute("DELETE FROM docs WHERE id=?", (identity,))
            ordinal = index.execute("SELECT COALESCE(MAX(id),0) FROM docs").fetchone()[0]
            for ordinal, row in enumerate(source.execute("SELECT unit_id,source_text,content_hash FROM retrieval_units WHERE unit_type='transcript_chunk' AND video_id=? ORDER BY unit_id", (video_id,)), ordinal + 1):
                index.execute("INSERT INTO docs(id,unit_id,video_id,content_hash) VALUES (?,?,?,?)", (ordinal, row["unit_id"], video_id, row["content_hash"]))
                index.execute("INSERT INTO body_fts(rowid,body) VALUES (?,?)", (ordinal, " ".join(self.tokenizer.tokens(row["source_text"]))))
            digest = sha256()
            count = 0
            for count, row in enumerate(index.execute("SELECT unit_id,content_hash FROM docs ORDER BY unit_id"), 1):
                digest.update((row["unit_id"] + "\0" + row["content_hash"] + "\n").encode())
            index.execute("CREATE TABLE IF NOT EXISTS identity (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            index.executemany("INSERT OR REPLACE INTO identity VALUES (?,?)", [("content_sha256", digest.hexdigest()), ("unit_count", str(count))])
            self._validated = False

    def _identity_token(self):
        # A live WAL commit may leave the main database's mtime/size unchanged.
        paths = (self.source_db, Path(str(self.source_db) + "-wal"), self.path)
        return tuple((path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
                     for path in paths)

    def validate_source(self) -> dict[str, str | int]:
        token = self._identity_token()
        if self._validated and token == self._source_stat:
            return self._validated_identity
        with self._validation_lock:
            token = self._identity_token()
            if self._validated and token == self._source_stat:
                return self._validated_identity
            result = self._validate_source_locked()
            self._source_stat = token
            return result

    def _validate_source_locked(self) -> dict[str, str | int]:
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as index, sqlite3.connect(self.source_db.as_uri() + "?mode=ro", uri=True) as source:
            index.row_factory = sqlite3.Row
            source.row_factory = sqlite3.Row
            index_count = index.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            digest = sha256()
            source_count = 0
            for source_count, row in enumerate(source.execute("SELECT unit_id,content_hash FROM retrieval_units WHERE unit_type='transcript_chunk' ORDER BY unit_id"), 1):
                digest.update((row["unit_id"] + "\0" + row["content_hash"] + "\n").encode())
            if index_count != source_count:
                raise ValueError("F1 lexical index/source unit count mismatch")
            try:
                expected = index.execute("SELECT value FROM identity WHERE key='content_sha256'").fetchone()
            except sqlite3.OperationalError:
                expected = None  # Frozen S2-H index predates the product identity table.
            if expected is not None and expected[0] != digest.hexdigest():
                raise ValueError("F1 lexical index/source content identity mismatch")
            if expected is None:
                index.execute("ATTACH DATABASE ? AS corpus", (self.source_db.as_uri() + "?mode=ro",))
                missing = index.execute("SELECT COUNT(*) FROM docs d LEFT JOIN corpus.retrieval_units u ON u.unit_id=d.unit_id WHERE u.unit_id IS NULL").fetchone()[0]
                if missing:
                    raise ValueError("F1 frozen lexical index/source unit identity mismatch")
        self._validated_identity = {"content_sha256": digest.hexdigest(), "unit_count": source_count,
                                    "lexical_path": str(self.path), "frozen_legacy_index": expected is None}
        self._validated = True
        return self._validated_identity

    def search(self, query: str, *, filters: RetrievalFilters) -> list[RawSearchHit]:
        self.validate_source()
        match = self.tokenizer.query(query)
        if not match:
            return []
        where, params = RetrievalService._search_filters(level="transcript_chunk", filters=filters, include_ignored=False)
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("ATTACH DATABASE ? AS corpus", (self.source_db.as_uri() + "?mode=ro",))
            rows = connection.execute(
                f"SELECT u.*, bm25(body_fts) AS score FROM body_fts JOIN docs d ON d.id=body_fts.rowid "
                f"JOIN corpus.retrieval_units u ON u.unit_id=d.unit_id "
                f"WHERE body_fts MATCH ? AND {where} ORDER BY score ASC,u.unit_id ASC LIMIT 50",
                [match, *params],
            ).fetchall()
        return [RawSearchHit(unit_id=row["unit_id"], video_id=row["video_id"], unit_type=row["unit_type"],
                             rank=rank, score=row["score"], retrieval_method="lexical", lexical_rank=rank,
                             lexical_score=row["score"], dense_rank=None, dense_score=None, rrf_score=None,
                             title=row["title"], uploader=row["uploader"], subtitle_source=row["source_type"],
                             start_time=row["start_time"], end_time=row["end_time"], excerpt=row["source_text"])
                for rank, row in enumerate(rows, 1)]


def dense_50(index: SQLiteExactDenseIndex, query: str, filters: RetrievalFilters) -> list[RawSearchHit]:
    rows = index.search(query, level="transcript_chunk", top_k=50, filters=filters)
    return [RawSearchHit(unit_id=row.unit_id, video_id=row.video_id, unit_type=row.unit_type,
                         rank=rank, score=row.dense_score, retrieval_method="dense", lexical_rank=None,
                         lexical_score=None, dense_rank=rank, dense_score=row.dense_score, rrf_score=None,
                         title=row.title, uploader=row.uploader, subtitle_source=row.source_type,
                         start_time=row.start_time, end_time=row.end_time, excerpt=row.matched_excerpt)
            for rank, row in enumerate(rows, 1)]


def rrf_50(dense: list[RawSearchHit], lexical: list[RawSearchHit]) -> list[RawSearchHit]:
    if len(dense) > 50 or len(lexical) > 50:
        raise ValueError("F1 channel depth exceeds 50")
    entries: dict[str, dict] = {}
    for channel, hits in (("dense", dense), ("lexical", lexical)):
        seen: set[str] = set()
        for hit in hits:
            if hit.unit_id in seen:
                continue
            seen.add(hit.unit_id)
            if not 1 <= hit.rank <= 50:
                raise ValueError("invalid F1 channel rank")
            entry = entries.setdefault(hit.unit_id, dict(hit=hit, score=0.0, dense_rank=None,
                                                         dense_score=None, lexical_rank=None, lexical_score=None))
            entry["score"] += 1 / (60 + hit.rank)
            entry[channel + "_rank"] = hit.rank
            entry[channel + "_score"] = hit.score
    ordered = sorted(entries.values(), key=lambda item: (-item["score"], item["hit"].unit_id))
    return [replace(item["hit"], rank=rank, score=item["score"], retrieval_method="hybrid",
                    rrf_score=item["score"], dense_rank=item["dense_rank"], dense_score=item["dense_score"],
                    lexical_rank=item["lexical_rank"], lexical_score=item["lexical_score"])
            for rank, item in enumerate(ordered[:50], 1)]
