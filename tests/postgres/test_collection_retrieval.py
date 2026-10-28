from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from dataclasses import replace
import numpy as np
import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.retrieval.service import RetrievalService
from shiliu.retrieval.dense import (
    PgExactDenseIndex,
    DenseModelIdentity,
    DenseIndexNotReadyError,
    _validate_vector,
)
from shiliu.retrieval.coordinator import ProjectionWorker, ProjectionStale
from shiliu.retrieval.f1 import F1LexicalIndex, dense_50, rrf_50
from shiliu.retrieval.models import RetrievalFilters


class FixedProvider:
    model_id = "synthetic/fixed512"
    dimension = 512

    def __init__(self, revision="test-v1"):
        self.revision = revision
        self.calls = 0

    def model_identity(self):
        return DenseModelIdentity(
            self.model_id,
            self.revision,
            "synthetic-provider-v1",
            512,
            "unit-float32",
            "collection-projection-v1",
            "synthetic-query-v1",
            "synthetic-input512-v1",
            "pg-exact512-v1",
        )

    def count_tokens(self, text, *, add_special_tokens=True):
        return len(text) + (2 if add_special_tokens else 0)

    def truncate_text(self, text, max_content_tokens):
        return text[:max_content_tokens]

    def embed_documents(self, texts):
        self.calls += 1
        return [np.array([1.0] + [0.0] * 511, dtype=np.float32) for _ in texts]

    def embed_query(self, text):
        return np.array([1.0] + [0.0] * 511, dtype=np.float32)


def add_video(
    resources, index=1, text="智能体使用工具读取文件，保留原始证据。", *, sid=None
):
    db, artifacts, lexical, dense = resources
    sid = sid or db.create_favorite_source(folder_id=index, folder_title=f"合成{index}")
    bvid = f"BV{index:010d}"
    db.record_source_snapshot(
        sid,
        [
            FavoriteItem(
                bvid=bvid, title=f"Claude Code 智能体{index}", favorite_time=100 + index
            )
        ],
        processing_profile="formal",
    )
    vid = db.get_video_by_source(bvid)["id"]
    batch = artifacts.batch(vid)
    _, ref = batch.save_raw_subtitle(
        bvid, [SubtitleSegment.model_validate({"from": 0, "to": 3, "content": text})]
    )
    batch.commit(
        lambda conn: db.update_video(
            vid,
            raw_subtitle_path=ref,
            subtitle_source="human",
            subtitle_language="zh",
            status="completed",
            conn=conn,
        )
    )
    return sid, vid


def test_pg_lexical_vector_lifecycle_and_f1(retrieval):
    db, artifacts, lexical, dense = retrieval
    sid, vid = add_video(retrieval)
    result = ProjectionWorker(lexical).run_one(video_id=vid)
    assert result["lexical_state"] == "current" and result["dense_state"] == "partial"
    assert lexical.search("智能体", level="transcript_chunk")[0].video_id == vid
    assert (
        lexical.search("体", level="transcript_chunk")[0].retrieval_method
        == "lexical_substring_fallback"
    )
    assert lexical.search("") == [] and lexical.search("!!!") == []
    assert lexical.search("%", level="transcript_chunk") == []
    assert lexical.search("智能体", filters=RetrievalFilters(video_ids=())) == []
    with pytest.raises(DenseIndexNotReadyError):
        dense.search("智能体")
    dense.rebuild()
    assert dense.statistics()["index"]["ready"]
    hits = dense.search(
        "智能体",
        level="transcript_chunk",
        filters=RetrievalFilters(source_db_id=sid, video_ids=(vid,)),
    )
    assert hits and hits[0].dense_score == pytest.approx(1)
    assert (
        dense.search("智能体", filters=RetrievalFilters(source_db_id=sid + 1000)) == []
    )
    assert dense.search("智能体", filters=RetrievalFilters(video_ids=())) == []
    lexical50 = F1LexicalIndex(lexical).search(
        "智能体", filters=RetrievalFilters(video_ids=(vid,))
    )
    fused = rrf_50(
        dense_50(dense, "智能体", RetrievalFilters(video_ids=(vid,))), lexical50
    )
    assert fused[0].rrf_score == pytest.approx(2 / 61)
    assert len({h.unit_id for h in rrf_50([*fused[:1]], [*fused[:1]])}) == 1
    db.set_ignored(vid, True)
    assert lexical.search("智能体") == [] and dense.search("智能体") == []
    db.set_ignored(vid, False)
    assert lexical.search("智能体") == []  # old generation is immediately invalid
    assert (
        ProjectionWorker(lexical, dense).run_one(video_id=vid)["dense_state"]
        == "current"
    )
    assert dense.search("智能体")
    db.record_source_snapshot(sid, [], processing_profile="formal", authoritative=True)
    assert lexical.search("智能体") == [] and dense.search("智能体") == []


@pytest.mark.parametrize("mutation", ["update", "remove"])
def test_c08_delayed_encoding_cannot_complete_new_request(retrieval, mutation):
    db, artifacts, lexical, dense = retrieval
    sid, vid = add_video(retrieval, text="旧正文 alpha")
    dense.rebuild()
    db.update_video(vid, description="generation n")
    worker = ProjectionWorker(lexical, dense, owner="A")
    claim = worker.claim(video_id=vid)
    snapshot = worker.snapshot(claim)
    units, tokens = worker.build(snapshot, claim)
    encoding = Event()
    updated = Event()

    def a():
        vectors = dense.encode(units)
        encoding.set()
        assert updated.wait(5)
        with pytest.raises(ProjectionStale):
            worker.publish(claim, snapshot, units, tokens, vectors=vectors)

    with ThreadPoolExecutor(1) as executor:
        result = executor.submit(a)
        assert encoding.wait(5)
        if mutation == "update":
            batch = artifacts.batch(vid)
            _, ref = batch.save_raw_subtitle_bytes(
                b'[{"from":0,"to":3,"content":"new body beta"}]'
            )
            batch.commit(
                lambda conn: db.update_video(
                    vid, description="generation n+1", raw_subtitle_path=ref, conn=conn
                )
            )
        else:
            db.record_source_snapshot(
                sid, [], processing_profile="formal", authoritative=True
            )
        with db.pg.read() as c:
            new = c.execute(
                "SELECT * FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND resource_key=%s AND domain='collection'",
                (db.workspace_id, str(vid)),
            ).fetchone()
            assert (
                new["requested_generation"] == claim["requested_generation"] + 1
                and new["status"] == "queued"
            )
            assert not c.execute(
                "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction' LIMIT 1"
            ).fetchone()
        assert not lexical.search("alpha") and not dense.search("alpha")
        updated.set()
        result.result(5)
    with db.pg.read() as c:
        current = c.execute(
            "SELECT status,requested_generation,payload FROM shiliu.retrieval_projection_tasks WHERE id=%s",
            (claim["id"],),
        ).fetchone()
        assert (
            current["status"] == "queued"
            and current["requested_generation"] == new["requested_generation"]
        )
        assert current["payload"] == new["payload"]
    ProjectionWorker(lexical, dense, owner="B").run_one(video_id=vid)
    if mutation == "remove":
        assert not lexical.search("alpha") and not dense.search("alpha")
        with db.pg.read() as c:
            assert not c.execute(
                "SELECT 1 FROM shiliu.retrieval_units WHERE video_id=%s", (vid,)
            ).fetchone()
        return
    assert lexical.search("beta", level="transcript_chunk") and not lexical.search(
        "alpha", level="transcript_chunk"
    )
    assert (
        dense.search("beta", level="transcript_chunk")[0].matched_excerpt
        == "new body beta"
    )


def test_fixed_vector_validation_distance_tie_and_formal_filters(retrieval):
    db, artifacts, lexical, dense = retrieval
    s1, v1 = add_video(retrieval, 1)
    s2, v2 = add_video(retrieval, 2)
    dense.rebuild()
    q = np.array([1.0] + [0.0] * 511, dtype=np.float32)
    hits = dense.search_vector(q, level="transcript_chunk")
    assert [h.unit_id for h in hits] == sorted(h.unit_id for h in hits)
    with db.pg.transaction() as c:
        c.execute(
            "UPDATE shiliu.collection_embeddings SET embedding=%s WHERE workspace_id=%s AND unit_id=%s AND profile_id=%s",
            (
                np.array([0.0, 1.0] + [0.0] * 510, dtype=np.float32),
                db.workspace_id,
                hits[0].unit_id,
                dense.profile_id,
            ),
        )
    ordered = dense.search_vector(q, level="transcript_chunk")
    assert [h.dense_score for h in ordered] == pytest.approx([1, 0])
    db.set_marked(v1, True)
    ProjectionWorker(lexical, dense).run_one(video_id=v1)
    assert all(
        h.video_id == v1
        for h in dense.search("x", filters=RetrievalFilters(is_marked=True))
    )
    assert all(
        h.video_id == v1
        for h in lexical.search("Claude", filters=RetrievalFilters(is_marked=True))
    )
    db.set_archived(v1, True)
    assert all(h.video_id != v1 for h in dense.search("x"))
    for bad in (
        [1.0] * 511,
        [0.0] * 512,
        [float("nan")] + [0.0] * 511,
        [2.0] + [0.0] * 511,
        [float("inf")] + [0.0] * 511,
    ):
        with pytest.raises(ValueError):
            _validate_vector(bad, 512)


def test_same_stable_units_in_distinct_workspaces_do_not_overwrite(retrieval, tmp_path):
    from shiliu.db import Database
    from shiliu.storage.scope import ResourceContext

    db, artifacts, lexical, dense = retrieval
    s1, v1 = add_video(retrieval, 1)
    dense.rebuild()
    with db.pg.transaction() as c:
        c.execute(
            "INSERT INTO shiliu.users(id,display_name,created_at) VALUES('synthetic_b','B',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO shiliu.workspaces(id,kind,owner_user_id,created_at) VALUES('personal:synthetic_b','personal','synthetic_b',clock_timestamp())"
        )
        c.execute(
            "INSERT INTO shiliu.workspace_guards(workspace_id) VALUES('personal:synthetic_b')"
        )
    other = Database(db.pg, ResourceContext("personal:synthetic_b", "synthetic_b"))
    objects = ArtifactStore(artifacts.root, other)
    second_lexical = RetrievalService(db=other, artifacts=objects)
    second_dense = PgExactDenseIndex(
        db=other, provider=FixedProvider(), lexical=second_lexical
    )
    s2, v2 = add_video((other, objects, second_lexical, second_dense), 1)
    second_dense.rebuild()
    original = dense.search("智能体", level="transcript_chunk")
    second = second_dense.search("智能体", level="transcript_chunk")
    assert original[0].unit_id == second[0].unit_id
    assert original[0].video_id == v1 and second[0].video_id == v2 and v1 != v2
    ref1 = db.get_video(v1)["raw_subtitle_path"]
    ref2 = other.get_video(v2)["raw_subtitle_path"]
    p1 = artifacts.managed_file(ref1)
    p2 = objects.managed_file(ref2)
    assert p1 != p2 and p1.stat().st_ino != p2.stat().st_ino
    assert db.get_video(v2) is None and other.get_video(v1) is None
    assert not dense.search("智能体", filters=RetrievalFilters(source_db_id=s2))
    with pytest.raises(FileNotFoundError):
        artifacts.read_bytes(ref2)


def product_composition(resources):
    from shiliu.retrieval.orchestrator import SearchOrchestrator
    from shiliu.retrieval.hybrid import HybridRetrievalService
    from shiliu.retrieval.product_search import ProductSearchService
    from shiliu.retrieval.consolidation import SearchResultConsolidator
    from shiliu.retrieval.enrichment import EvidenceEnricher
    from shiliu.evidence.search import EvidenceSearchService

    db, artifacts, lexical, dense = resources
    hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
    raw = SearchOrchestrator(
        db=db,
        lexical=lexical,
        dense_factory=lambda: dense,
        hybrid_factory=lambda: hybrid,
    )
    product = ProductSearchService(
        db=db,
        raw_search=raw,
        consolidator=SearchResultConsolidator(),
        enricher=EvidenceEnricher(db=db, artifacts=artifacts),
    )
    evidence = EvidenceSearchService(
        db=db,
        product_search=product,
        artifacts=artifacts,
        authority_mode="live_current_exact_replay",
    )
    return raw, product, evidence


def test_pg_product_f1_manifest_citation_closed_loop(retrieval):
    from shiliu.retrieval.product_search import (
        ProductSearchRequest,
        ProductSearchFilterRequest,
    )
    from shiliu.ask.deep.f1_tools import F1TranscriptTool
    from shiliu.evidence.contracts import EvidenceContractError

    db, artifacts, lexical, dense = retrieval
    sid, vid = add_video(
        retrieval, text="MCP 协议允许智能体调用文件工具，原始证据必须可追溯。"
    )
    dense.rebuild()
    raw, product, evidence = product_composition(retrieval)
    response = product.search(
        ProductSearchRequest(query="MCP", mode="hybrid", scope="transcript_chunk"),
        video_ids=(vid,),
    )
    assert (
        response.results
        and response.trace_persisted
        and response.presentation_trace_persisted
    )
    trace = raw.get_trace(
        response.raw_trace_id
        if hasattr(response, "raw_trace_id")
        else response.trace_id
    )
    # Product and raw traces share a trace ID under the existing contract.
    assert (
        trace["storage_backend"] == "postgresql+pgvector"
        and trace["embedding_profile"] == dense.profile_id
    )
    assert product.get_presentation(response.trace_id)["group_summary"]
    assert not product.search(
        ProductSearchRequest(query="MCP", mode="lexical"), video_ids=()
    ).results
    f1 = F1TranscriptTool(evidence, dense.provider, lexical)
    result = f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=(vid,))
    assert result["hits"] and result["spans"] and not result["stale"]
    span = result["spans"][0]
    f1.materializer.validate_current(span)
    citation = span.as_citation()
    assert (
        f1.materializer.reconstruct_citation(
            citation,
            execution_id="p2-replay",
            search_trace_id=result["trace_id"],
            query="MCP",
        ).citation_id
        == span.citation_id
    )
    assert citation.source_version == span.source_version
    original = load_historical(
        artifacts, db.get_video(vid)["raw_subtitle_path"], span.source_version
    )
    assert span.segments[0].source_text in original.decode()
    # A formal visibility mutation immediately invalidates evidence before send.
    db.set_ignored(vid, True)
    with pytest.raises(EvidenceContractError):
        f1.materializer.validate_current(span)
    assert (
        f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=(vid,))[
            "spans"
        ]
        == ()
    )
    db.set_ignored(vid, False)
    ProjectionWorker(lexical, dense).run_one(video_id=vid)
    assert f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=(vid,))[
        "spans"
    ]
    assert (
        f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=())["spans"]
        == ()
    )


def load_historical(artifacts, ref, version):
    return artifacts.raw_bytes(ref, expected_source_version=version)


def task_row(db, vid):
    with db.pg.read() as c:
        return c.execute(
            "SELECT * FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
            (db.workspace_id, str(vid)),
        ).fetchone()


def due(db, vid):
    with db.pg.transaction() as c:
        c.execute(
            "UPDATE shiliu.retrieval_projection_tasks SET not_before=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
            (db.workspace_id, str(vid)),
        )


def queue_profile(db, vid, profile):
    from psycopg.types.json import Jsonb

    with db.connect(guard=True) as c:
        c.execute(
            "UPDATE shiliu.retrieval_projection_tasks SET payload=payload||%s,status='queued',attempt=0,not_before=clock_timestamp() WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
            (Jsonb(dict(target_profile=profile)), db.workspace_id, str(vid)),
        )


def test_profile_coverage_switch_and_query_policy_identity(retrieval):
    from shiliu.retrieval.dense import profile_identity

    db, artifacts, lexical, dense = retrieval
    _, v1 = add_video(retrieval, 1)
    _, v2 = add_video(retrieval, 2)
    dense.rebuild()
    provider = FixedProvider("test-v2")
    candidate = PgExactDenseIndex(db=db, provider=provider, lexical=lexical)
    candidate.register()
    assert candidate.profile_id != dense.profile_id

    class QueryChange(FixedProvider):
        def model_identity(self):
            return replace(
                super().model_identity(), query_instruction_version="query-only-v2"
            )

    assert profile_identity(QueryChange())[0] == dense.profile_id
    with pytest.raises(DenseIndexNotReadyError):
        candidate.activate()
    queue_profile(db, v1, candidate.profile_id)
    generation = task_row(db, v1)["requested_generation"]
    # Wrong-profile worker skips this task and can still process the next one.
    db.update_video(v2, description="independent next intent")
    next_claim = ProjectionWorker(lexical, dense).claim()
    assert next_claim["resource_key"] == str(v2)
    # Requeue the unexecuted claimed intent through the same explicit build path.
    queue_profile(db, v2, candidate.profile_id)
    ProjectionWorker(lexical, candidate).run_one(video_id=v1)
    assert task_row(db, v1)["requested_generation"] == generation
    assert dense.active_profile() == dense.profile_id
    assert dense.search("智能体", filters=RetrievalFilters(video_ids=(v1,)))
    with pytest.raises(DenseIndexNotReadyError):
        candidate.activate()
    ProjectionWorker(lexical, candidate).run_one(video_id=v2)
    candidate.activate()
    assert candidate.statistics()["index"]["ready"]
    assert candidate.search("智能体")
    with pytest.raises(DenseIndexNotReadyError):
        dense.search("智能体")
    with db.pg.read() as c:
        assert (
            c.execute(
                "SELECT count(DISTINCT profile_id) AS n FROM shiliu.collection_embeddings WHERE workspace_id=%s",
                (db.workspace_id,),
            ).fetchone()["n"]
            == 2
        )


def test_lexical_only_retry_bound_recovery_and_late_epoch(retrieval):
    from shiliu.ask.deep.f1_tools import F1TranscriptTool
    from shiliu.retrieval.product_search import ProductSearchFilterRequest

    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval, text="MCP 文件工具用于检索证据。")
    worker = ProjectionWorker(lexical)
    for attempt in range(1, 6):
        before = task_row(db, vid)
        result = worker.run_one(video_id=vid)
        row = task_row(db, vid)
        assert row["attempt"] == attempt
        assert row["status"] == ("failed" if attempt == 5 else "retry_wait")
        assert row["requested_generation"] == before["requested_generation"]
        assert row["payload"]["ready_generation"] == row["requested_generation"]
        assert (
            row["last_error"] == "model_unavailable"
            and result["dense_state"] == "partial"
        )
        assert (
            row["not_before"] - row["updated_at"]
        ).total_seconds() >= 2**attempt - 0.1
        assert lexical.search("MCP")
        due(db, vid)
    assert worker.run_one(video_id=vid) is None
    _, _, evidence = product_composition(retrieval)
    result = F1TranscriptTool(evidence, dense.provider, lexical).search(
        "MCP", filters=ProductSearchFilterRequest()
    )
    assert (
        result["spans"]
        and result["index_identity"]["degraded_reason"] == "DenseIndexNotReadyError"
    )
    assert dense.statistics()["index"]["failed_count"] == 1
    db.update_video(vid, title="MCP 新请求重置失败预算")
    assert task_row(db, vid)["attempt"] == 0
    old = ProjectionWorker(lexical, dense, owner="lost")
    claim = old.claim(video_id=vid)
    snapshot = old.snapshot(claim)
    units, tokens = old.build(snapshot, claim)
    vectors = dense.encode(units)
    with db.pg.transaction() as c:
        c.execute(
            "UPDATE shiliu.retrieval_projection_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (claim["id"],),
        )
    new = ProjectionWorker(lexical, dense, owner="recovered")
    new.recover()
    assert task_row(db, vid)["status"] == "retry_wait"
    due(db, vid)
    assert new.run_one(video_id=vid)["status"] == "completed"
    with pytest.raises(ProjectionStale):
        old.publish(claim, snapshot, units, tokens, vectors=vectors)
    assert task_row(db, vid)["status"] == "completed"
    dense.activate()
    assert dense.statistics()["index"]["ready"]


def test_partial_dense_returns_current_lexical_evidence_and_profile_trace(
    retrieval, monkeypatch
):
    from shiliu.ask.deep.f1_tools import F1TranscriptTool
    from shiliu.retrieval.product_search import (
        ProductSearchRequest,
        ProductSearchFilterRequest,
    )

    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval, text="MCP 文件协议的原始证据。")
    dense.rebuild()
    db.create_note(vid, "new generation")

    def unavailable(texts):
        raise RuntimeError("synthetic local encoder unavailable")

    monkeypatch.setattr(dense.provider, "embed_documents", unavailable)
    assert (
        ProjectionWorker(lexical, dense).run_one(video_id=vid)["dense_state"]
        == "partial"
    )
    assert dense.search("MCP", level="transcript_chunk") == []
    assert dense.statistics()["index"]["missing_count"] > 0
    raw, product, evidence = product_composition(retrieval)
    response = product.search(
        ProductSearchRequest(query="MCP", mode="hybrid", scope="transcript_chunk")
    )
    assert (
        response.results
        and raw.get_trace(response.trace_id)["degraded_reason"] == "partial"
    )
    found = F1TranscriptTool(evidence, dense.provider, lexical).search(
        "MCP", filters=ProductSearchFilterRequest()
    )
    assert found["spans"] and found["index_identity"]["degraded_reason"] == "partial"
    assert all(h.dense_rank is None for h in found["hits"])


def test_pinned_tokenizer_frequency_safe_or_ts_rank_and_short_scope(retrieval):
    db, artifacts, lexical, dense = retrieval
    s1, v1 = add_video(retrieval, 1, "MCP MCP MCP 唯一词")
    s2, v2 = add_video(retrieval, 2, "MCP 独立词")
    dense.rebuild()
    tokens = lexical.tokenizer.tokens("ＭＣＰ mcp MCP")
    assert tokens == ["mcp", "mcp", "mcp"]
    assert lexical.tokenizer.query("MCP mcp") == "'mcp'"
    assert (
        lexical.tokenizer.dictionary_hash
        == "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"
    )
    ranked = lexical.search("MCP", level="transcript_chunk")
    assert [h.video_id for h in ranked] == [v1, v2] and ranked[
        0
    ].lexical_score > ranked[1].lexical_score > 0
    for query in ("MCP | ! & ' " + chr(92), ":*", "MCP OR 未命中"):
        rows = lexical.search(
            query,
            level="transcript_chunk",
            top_k=1,
            filters=RetrievalFilters(source_db_id=s2),
        )
        assert all(h.video_id == v2 for h in rows)
    assert not lexical.search("唯一", filters=RetrievalFilters(source_db_id=s2))


def test_rebuild_and_library_changes_reuse_verified_unchanged_inputs(retrieval):
    from shiliu.library import LibraryService
    from shiliu.retrieval.coordinator import RetrievalIndexCoordinator

    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)
    first = dense.rebuild()
    calls = dense.provider.calls
    second = dense.rebuild()
    assert first.embedded_count == first.total_unit_count == 2
    assert second.embedded_count == 0 and second.reused_count == 2
    assert dense.provider.calls == calls
    coordinator = RetrievalIndexCoordinator(
        db=db, lexical=lexical, dense_factory=lambda: dense
    )
    library = LibraryService(db, coordinator)
    note = library.add_note(vid, "new included note")
    assert dense.provider.calls == calls + 1
    library.set_marked(vid, True)
    library.set_reading_state(vid, "read")
    library.set_archived(vid, True)
    assert dense.provider.calls == calls + 1
    library.delete_note(note["id"])
    assert dense.provider.calls == calls + 2
    assert dense.statistics()["index"]["ready"]
