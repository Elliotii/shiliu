"""Explicit Collection composition: real PG/stores, synthetic upstream/providers."""

import json

from shiliu.ask.deep.f1_tools import F1TranscriptTool
from shiliu.ask.f1_context import F1ContextBuilder
from shiliu.domain import FavoriteItem, SubtitleSegment, SyncMode, ASRTriggerMode
from shiliu.pipeline import PipelineService
from shiliu.sync import SyncService
from shiliu.asr import ASRService
from shiliu.library import LibraryService
from shiliu.retrieval.coordinator import ProjectionWorker, RetrievalIndexCoordinator
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.product_search import ProductSearchFilterRequest
from test_collection_pipeline import FakeAdapter, FakeProvider, bundle
from test_collection_asr import AudioAdapter, SuccessfulProvider
from test_collection_retrieval import add_video, product_composition, task_row


def test_sync_pipeline_manifest_f1_citation_update_remove_rebuild(retrieval, tmp_path):
    db, artifacts, lexical, dense = retrieval

    class Adapter(FakeAdapter):
        items = []

        def list_favorite_items(self, favorite_id):
            assert favorite_id == 42
            return self.items

    video_bundle = bundle().model_copy(
        update={
            "subtitle_segments": [
                SubtitleSegment.model_validate(
                    {
                        "from": 0.1,
                        "to": 2.2,
                        "content": "MCP 协议连接智能体和文件工具。",
                    }
                ),
                SubtitleSegment.model_validate(
                    {"from": 2.2, "to": 5, "content": "检索引用必须能够回到原始证据。"}
                ),
            ]
        }
    )
    adapter, provider = Adapter(video_bundle), FakeProvider()
    coordinator = RetrievalIndexCoordinator(
        db=db, lexical=lexical, dense_factory=lambda: dense
    )
    pipeline = PipelineService(
        db=db,
        adapter=adapter,
        artifacts=artifacts,
        provider_factory=lambda: provider,
        index_coordinator=coordinator,
    )
    sync = SyncService(
        db=db,
        adapter=adapter,
        pipeline=pipeline,
        favorite_id=42,
        lock_path=tmp_path / "sync.lock",
        index_coordinator=coordinator,
    )
    assert sync.sync(SyncMode.MANUAL).baseline_created
    adapter.items = [
        FavoriteItem(
            bvid=video_bundle.bvid, title=video_bundle.title, favorite_time=100
        )
    ]
    assert sync.sync(SyncMode.MANUAL).discovered_count == 1
    video = db.get_video_by_source(video_bundle.bvid)
    vid = video["id"]
    assert video["status"] == "completed"
    assert (
        provider.transcript_calls == provider.summary_calls == 1 and adapter.calls == 1
    )
    assert video["raw_subtitle_path"].startswith("artifact:")
    dense.rebuild()
    _, _, evidence = product_composition(retrieval)
    f1 = F1TranscriptTool(evidence, dense.provider, lexical)
    found = f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=(vid,))
    span = found["spans"][0]
    context = F1ContextBuilder(total_character_budget=1500).build(
        query="MCP", normalized_intent="MCP", spans=found["spans"]
    )
    payload = json.loads(context.model_context)
    assert len(context.model_context) <= 1500
    assert payload["citation_allowlist"] == list(context.citation_allowlist)
    assert span.citation_id in context.citation_allowlist
    citation = span.as_citation()
    replay = f1.materializer.reconstruct_citation(
        citation, execution_id="p2", search_trace_id=found["trace_id"], query="MCP"
    )
    assert (
        replay.quote_text == span.quote_text and replay.segment_ids == span.segment_ids
    )
    old_ref = video["raw_subtitle_path"]
    old_bytes = artifacts.raw_bytes(
        old_ref, expected_source_version=span.source_version
    )
    # A new immutable raw version invalidates the old generation immediately.
    batch = artifacts.batch(vid)
    _, ref = batch.save_raw_subtitle_bytes(
        b'[{"from":0,"to":3,"content":"new raw replacement"}]'
    )
    batch.commit(lambda c: db.update_video(vid, raw_subtitle_path=ref, conn=c))
    assert not f1.search("MCP", filters=ProductSearchFilterRequest(), video_ids=(vid,))[
        "spans"
    ]
    ProjectionWorker(lexical, dense).run_one(video_id=vid)
    replacement = f1.search(
        "replacement", filters=ProductSearchFilterRequest(), video_ids=(vid,)
    )["spans"][0]
    assert replacement.source_version != span.source_version
    assert (
        artifacts.raw_bytes(old_ref, expected_source_version=span.source_version)
        == old_bytes
    )
    adapter.items = []
    sync.sync(SyncMode.MANUAL)
    assert not lexical.search("replacement") and not dense.search("replacement")
    lexical.rebuild()
    dense.rebuild()
    assert not lexical.search("replacement") and not dense.search("replacement")
    assert provider.transcript_calls == provider.summary_calls == 1


def test_asr_manifest_completion_replaces_chunks_in_shared_index(retrieval):
    db, artifacts, lexical, dense = retrieval
    # AudioAdapter intentionally supports exactly this synthetic BVID.
    sid = db.create_favorite_source(folder_id=42, folder_title="合成ASR")
    db.record_source_snapshot(
        sid,
        [FavoriteItem(bvid="BV1234567890", title="合成ASR")],
        processing_profile="formal",
    )
    vid = db.get_video_by_source("BV1234567890")["id"]
    db.update_video(vid, duration_seconds=183, status="skipped_no_subtitle")
    dense.rebuild()
    provider = SuccessfulProvider()
    coordinator = RetrievalIndexCoordinator(
        db=db, lexical=lexical, dense_factory=lambda: dense
    )
    service = ASRService(
        db=db,
        adapter=AudioAdapter(),
        artifacts=artifacts,
        provider=provider,
        index_coordinator=coordinator,
    )
    assert service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert provider.upload_calls == provider.submit_calls == 1
    assert task_row(db, vid)["status"] == "completed"
    _, _, evidence = product_composition(retrieval)
    found = F1TranscriptTool(evidence, dense.provider, lexical).search(
        "第一句", filters=ProductSearchFilterRequest()
    )
    assert found["spans"] and found["spans"][0].source_type == "asr"
    assert found["spans"][0].segments[0].start_time == 0.1


def test_original_metadata_uploader_time_and_visibility_contracts_before_limit(
    retrieval,
):
    db, artifacts, lexical, dense = retrieval
    s1, v1 = add_video(retrieval, 1)
    _, v2 = add_video(retrieval, 2)
    db.update_video(v1, uploader="Alice Studio")
    db.update_video(v2, uploader="Alice Studio Extra")
    db.set_reading_state(v1, "read")
    db.set_marked(v1, True)
    db.set_archived(v1, True)
    db.set_ignored(v2, True)
    dense.rebuild()
    # Archive is a label in the original product contract; None includes both.
    assert {h.video_id for h in lexical.search("Claude", level="video")} == {v1}
    assert {
        h.video_id
        for h in lexical.search("Claude", level="video", include_ignored=True)
    } == {v1, v2}
    for filters, expected in [
        (RetrievalFilters(uploader="ALICE STUDIO"), {v1}),
        (RetrievalFilters(uploader="Alice"), set()),
        (RetrievalFilters(uploader_contains="alice studio"), {v1, v2}),
        (
            RetrievalFilters(
                source_db_id=s1,
                folder_id=1,
                favorite_time_from=101,
                favorite_time_to=101,
                reading_state="read",
                is_marked=True,
                archived=True,
            ),
            {v1},
        ),
        (RetrievalFilters(source_db_id=s1, favorite_time_to=100), set()),
        (RetrievalFilters(source_db_id=s1, folder_id=2), set()),
        (RetrievalFilters(archived=False), {v2}),
    ]:
        for search, query in [(lexical.search, "Claude"), (dense.search, "query")]:
            actual = {
                h.video_id
                for h in search(
                    query, level="video", top_k=1, filters=filters, include_ignored=True
                )
            }
            assert actual <= expected and len(actual) == min(1, len(expected))

    # Formal mutation commits even if post-commit execution fails; intent remains.
    class Broken:
        def safe_sync_video(self, *args, **kwargs):
            return None

    library = LibraryService(db, Broken())
    library.add_note(v1, "独有笔记token")
    assert task_row(db, v1)["status"] == "queued" and not lexical.search("笔记token")
    ProjectionWorker(lexical, dense).run_one(video_id=v1)
    assert lexical.search("笔记token", level="video")


def test_actual_fast_deep_f1_composition_and_tool_scope_defaults(retrieval):
    from shiliu.ask.service import AskService
    from shiliu.ask.deep.v2 import V2Action
    from shiliu.ask.deep.transcript import TranscriptSearchService

    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval, text="MCP 工具连接模型与文件，保留证据。")
    dense.rebuild()
    _, product, evidence = product_composition(retrieval)

    def no_online_provider(*args, **kwargs):
        raise AssertionError("P2 must not dispatch an online model")

    ask = AskService(
        db=db,
        artifacts=artifacts,
        product_search=product,
        evidence_search=evidence,
        provider_factory=no_online_provider,
        deep_embedding_provider=dense.provider,
        fast_f1=True,
    )
    assert ask.f1_transcripts is ask.deep_service.graph.transcripts
    fast = ask.f1_transcripts.search("MCP", filters=ProductSearchFilterRequest())
    assert fast["spans"]
    graph = ask.deep_service.graph
    for arguments in (
        {"query": "MCP"},
        {"query": "MCP", "video_ids": []},
        {"query": "MCP", "video_ids": [vid]},
    ):
        result = graph._execute_one(
            V2Action(
                action_id="p2",
                kind="search_transcripts",
                arguments=arguments,
                purpose="synthetic wiring",
            ),
            {"filters": ProductSearchFilterRequest(), "cache": {}},
        )
        assert result["status"] == "ok" and result["spans"]
    nav = graph._execute_one(
        V2Action(
            action_id="nav",
            kind="search_videos",
            arguments={"uploader_contains": ""},
            purpose="field query",
        ),
        {"filters": ProductSearchFilterRequest(), "cache": {}},
    )
    assert nav["status"] == "ok" and nav["sources"][0].video_id == vid
    assert nav["sources"][0].metadata["subtitle_available"]
    old_deep = TranscriptSearchService(
        evidence_search=evidence, materializer=ask.materializer
    )
    assert old_deep.search("MCP", filters=ProductSearchFilterRequest()).spans
    assert not old_deep.search(
        "MCP", filters=ProductSearchFilterRequest(), video_ids=()
    ).spans
    span = fast["spans"][0]
    assert (
        graph.windows.read_context(
            span, before_seconds=0, after_seconds=0
        ).span.segment_ids
        == span.segment_ids
    )


def test_generated_json_reader_pins_formal_version_not_newer_head(retrieval):
    from shiliu.domain import SummaryResult

    db, artifacts, lexical, dense = retrieval
    _, vid = add_video(retrieval)

    def summary(text):
        return SummaryResult(
            conclusion=text, key_points=["一", "二", "三"], detailed_notes=["合成摘要"]
        )

    batch = artifacts.batch(vid)
    _, old = batch.save_summary("unused", summary("pinnedold"), revision="refined")
    batch.commit(lambda c: db.update_video(vid, summary_path=old, conn=c))
    # A prepared/published derivative without a formal pointer is not current.
    newer = artifacts.batch(vid)
    newer.save_summary("unused", summary("unboundnew"), revision="refined")
    newer.commit(lambda c: None)
    dense.rebuild()
    assert lexical.search("pinnedold", level="video") and not lexical.search(
        "unboundnew"
    )
    assert b"pinnedold" in artifacts.generated_json_bytes(old)


def test_corpus_context_reads_pg_jsonb_with_original_boundary_identity(retrieval):
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from shiliu.db import collection_dto, utc_now
    from shiliu.taxonomy.corpus import TaxonomyCorpusService
    from shiliu.retrieval.corpus_search import (
        CorpusSearchContextProjection,
        _hash,
        _canonical_json,
    )
    from shiliu.research.schema import PERSONAL_WORKSPACE_POLICY_VERSION

    db, artifacts, lexical, dense = retrieval
    sid, vid = add_video(retrieval)
    db.update_video(vid, title="MCP 证据", description="MCP 协议简介")
    snapshot = TaxonomyCorpusService(db, artifacts).freeze([sid])
    task = "p2-corpus"
    with db.connect() as c:
        c.execute(
            "INSERT INTO shiliu.research_tasks(task_id,status,workspace_id,owner_user_id,created_at,updated_at) VALUES(%s,'ready',%s,%s,clock_timestamp(),clock_timestamp())",
            (task, db.workspace_id, db.context.user_id),
        )
        row = collection_dto(
            c.execute(
                "SELECT * FROM shiliu.taxonomy_corpus_snapshots WHERE id=%s",
                (snapshot.snapshot_id,),
            ).fetchone()
        )
        row.pop("workspace_id")
        for key in ("selected_source_ids_json", "evidence_counts_json"):
            row[key] = _canonical_json(row[key])
        refs = [
            dict(
                ref_type="taxonomy_snapshot",
                ref_id=str(snapshot.snapshot_id),
                boundary_hash=_hash(row),
            )
        ]
        payload = dict(observation_type="topic", value="MCP")
        content = dict(
            record_kind="corpus_observation",
            authority_class="corpus_soft_prior",
            status="current",
            semantic_key="MCP topic",
            payload=payload,
            source_refs=refs,
            confidence=None,
            expires_at=None,
            policy_version=PERSONAL_WORKSPACE_POLICY_VERSION,
        )
        values = dict(
            record_revision_id="p2-revision",
            record_id="p2-record",
            version=1,
            command_task_id=task,
            record_kind=content["record_kind"],
            authority_class=content["authority_class"],
            status=content["status"],
            semantic_key=content["semantic_key"],
            payload_json=Jsonb(payload),
            source_refs_json=Jsonb(refs),
            source_boundary_hash=_hash(refs),
            decision_action="create",
            reason="synthetic",
            principal_id=db.context.user_id,
            policy_version=PERSONAL_WORKSPACE_POLICY_VERSION,
            content_hash=_hash(content),
            command_id="p2-command",
            command_payload_hash="c" * 64,
            created_at=utc_now(),
            workspace_id=db.workspace_id,
        )
        c.execute(
            sql.SQL(
                "INSERT INTO shiliu.research_workspace_records({}) VALUES({})"
            ).format(
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.SQL("%s") for _ in values),
            ),
            list(values.values()),
        )
    projection = CorpusSearchContextProjection(db)
    result = projection.project(
        task_id=task,
        principal_id=db.context.user_id,
        normalized_query="MCP",
        enabled=True,
    )
    assert result.context["status"] == "eligible" and vid in result.matches_by_video
    assert (
        projection.project(
            task_id=task, principal_id="other", normalized_query="MCP", enabled=True
        ).context["status"]
        == "fail_closed"
    )
