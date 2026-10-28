from dataclasses import replace
from shiliu.retrieval.lexical import F1Tokenizer as F1Tokenizer
from shiliu.retrieval.dense import PgExactDenseIndex
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.orchestrator import RawSearchHit


class F1LexicalIndex:
    """The shared Collection subtitle BM25, with F1's body-query profile."""

    def __init__(self, lexical):
        self.lexical = lexical
        self.tokenizer = lexical.tokenizer

    def ensure_ready(self):
        return self.lexical.chunk_index_identity()

    def validate_source(self):
        return self.ensure_ready()

    def search(self, query, *, filters):
        rows = self.lexical.search(
            query, level="transcript_chunk", top_k=50, filters=filters, navigation=False
        )
        return [
            RawSearchHit(
                unit_id=row.unit_id,
                video_id=row.video_id,
                unit_type=row.unit_type,
                rank=rank,
                score=row.lexical_score,
                retrieval_method="lexical",
                lexical_rank=rank,
                lexical_score=row.lexical_score,
                dense_rank=None,
                dense_score=None,
                rrf_score=None,
                title=row.title,
                uploader=row.uploader,
                subtitle_source=row.source_type,
                start_time=row.start_time,
                end_time=row.end_time,
                excerpt=row.matched_excerpt,
            )
            for rank, row in enumerate(rows, 1)
        ]


def dense_50(
    index: PgExactDenseIndex, query: str, filters: RetrievalFilters
) -> list[RawSearchHit]:
    rows = index.search(query, level="transcript_chunk", top_k=50, filters=filters)
    return [
        RawSearchHit(
            unit_id=row.unit_id,
            video_id=row.video_id,
            unit_type=row.unit_type,
            rank=rank,
            score=row.dense_score,
            retrieval_method="dense",
            lexical_rank=None,
            lexical_score=None,
            dense_rank=rank,
            dense_score=row.dense_score,
            rrf_score=None,
            title=row.title,
            uploader=row.uploader,
            subtitle_source=row.source_type,
            start_time=row.start_time,
            end_time=row.end_time,
            excerpt=row.matched_excerpt,
        )
        for rank, row in enumerate(rows, 1)
    ]


def rrf_50(
    dense: list[RawSearchHit], lexical: list[RawSearchHit]
) -> list[RawSearchHit]:
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
            entry = entries.setdefault(
                hit.unit_id,
                dict(
                    hit=hit,
                    score=0.0,
                    dense_rank=None,
                    dense_score=None,
                    lexical_rank=None,
                    lexical_score=None,
                ),
            )
            entry["score"] += 1 / (60 + hit.rank)
            entry[channel + "_rank"] = hit.rank
            entry[channel + "_score"] = hit.score
    ordered = sorted(
        entries.values(), key=lambda item: (-item["score"], item["hit"].unit_id)
    )
    return [
        replace(
            item["hit"],
            rank=rank,
            score=item["score"],
            retrieval_method="hybrid",
            rrf_score=item["score"],
            dense_rank=item["dense_rank"],
            dense_score=item["dense_score"],
            lexical_rank=item["lexical_rank"],
            lexical_score=item["lexical_score"],
        )
        for rank, item in enumerate(ordered[:50], 1)
    ]
