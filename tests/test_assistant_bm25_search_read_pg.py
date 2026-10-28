"""Opt-in: real Assistant path, only random children of the guarded 55487 fixture."""
import asyncio
from copy import deepcopy
from pathlib import Path
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from test_collection_bm25_product import resources
from shiliu.artifacts import ArtifactStore
from shiliu.assistant.contracts import KnowledgeSearchArgs
from shiliu.assistant.delivery import project_tool_result
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.db import Database
from shiliu.domain import FavoriteItem
from shiliu.retrieval.bm25 import RANKING_VERSION, check_index
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.retrieval.dense import PgExactDenseIndex
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.hybrid import HybridRetrievalService
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import ProductSearchService
from shiliu.retrieval.service import INDEX_VERSION, RetrievalService
from shiliu.storage.scope import ResourceContext
from research.postgres_eval.bm25_product import ROOT, admin
import importlib.util

pytestmark = pytest.mark.skipif(os.environ.get("SHILIU_BM25_PRODUCT_TEST") != "1",
    reason="explicit isolated BM25 test cluster required")
spec = importlib.util.spec_from_file_location("assistant_fixed_provider", Path(__file__).parent / "postgres/test_collection_retrieval.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


@pytest.fixture(scope="module")
def assistant_pg(resources, request):
    db, artifacts, lexical, _ = resources
    owned_roots = [artifacts.root]
    def cleanup():
        for root in owned_roots:
            assert root.parent == ROOT / "fixture-artifacts" and root.name.startswith("shiliu_bm25_fixture_")
            if root.exists():
                shutil.rmtree(root)
    request.addfinalizer(cleanup)
    def seed(db, artifacts, lexical, index, *, source_id=None, raw=None, title="Synthetic", uploader="Author", description=""):
        sid = source_id or db.create_favorite_source(folder_id=index, folder_title=f"Synthetic{index}")
        bvid = f"BV{index:010d}"
        db.record_source_snapshot(sid, [FavoriteItem(bvid=bvid, title=title, uploader=uploader,
            favorite_time=100 + index)], processing_profile="formal", authoritative=False)
        vid = db.get_video_by_source(bvid)["id"]
        if raw:
            batch = artifacts.batch(vid)
            ref = batch._save("subtitle-raw.json", raw.encode(), media_type="application/json")
            batch.commit(lambda conn: db.update_video(vid, raw_subtitle_path=ref,
                subtitle_source="human", subtitle_language="zh", description=description,
                status="completed", conn=conn))
        else:
            db.update_video(vid, description=description, status="completed")
        ProjectionWorker(lexical).run_one(video_id=vid)
        return sid, vid

    segments = [{"from": 0, "to": 10, "content": "alpha earlier " + "前文。" * 90},
                {"from": 11, "to": 12, "content": " \n "},
                {"from": 200, "to": 210, "content": 'alpha UniqueTarget 中文 "引号" \\ \n末尾'}]
    raw_text = json.dumps(segments, ensure_ascii=True, indent=2)
    sid, target = seed(db, artifacts, lexical, 701, raw=raw_text)
    _, metadata = seed(db, artifacts, lexical, 702, title="TitleUnique", uploader="AuthorUnique", description="DescriptionUnique")
    _, outside = seed(db, artifacts, lexical, 703, raw=raw_text)
    _, ignored = seed(db, artifacts, lexical, 704, source_id=sid, raw=raw_text)
    _, removed = seed(db, artifacts, lexical, 705, source_id=sid, raw=raw_text)
    with db.connect() as c:
        c.execute("INSERT INTO shiliu.users(id,display_name,created_at) VALUES('assistant_other','Synthetic',clock_timestamp())")
        c.execute("INSERT INTO shiliu.workspaces(id,kind,owner_user_id,created_at) VALUES('personal:assistant_other','personal','assistant_other',clock_timestamp())")
        c.execute("INSERT INTO shiliu.workspace_guards(workspace_id) VALUES('personal:assistant_other')")
    other = Database(db.pg, ResourceContext("personal:assistant_other", "assistant_other"))
    other_artifacts = ArtifactStore(artifacts.root.parent / (artifacts.root.name + "_other"), other)
    owned_roots.append(other_artifacts.root)
    other_lexical = RetrievalService(db=other, artifacts=other_artifacts)
    _, foreign = seed(other, other_artifacts, other_lexical, 706, raw=raw_text)
    dense = PgExactDenseIndex(db=db, provider=helpers.FixedProvider(), lexical=lexical)
    dense.rebuild()  # Only five tiny synthetic videos; every fake-token input fits 512.
    db.set_ignored(ignored, True)
    with db.connect(guard=True) as c:
        c.execute("UPDATE shiliu.video_source_memberships SET removed_at=clock_timestamp() WHERE workspace_id=%s AND video_id=%s",
                  (db.workspace_id, removed))
        db._touch(c, removed, reason="synthetic_membership_removed")
    ProjectionWorker(lexical, dense).run_one(video_id=ignored)
    ProjectionWorker(lexical, dense).run_one(video_id=removed)
    hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
    orchestrator = SearchOrchestrator(db=db, lexical=lexical, dense_factory=lambda: dense,
        hybrid_factory=lambda: hybrid, persist_trace=False)
    product = ProductSearchService(db=db, raw_search=orchestrator,
        consolidator=SearchResultConsolidator(), enricher=EvidenceEnricher(db=db, artifacts=artifacts),
        persist_trace=False)
    sources = CollectionSourceService(db=db, artifacts=artifacts, snapshots=SourceSnapshotStore(db, artifacts), product_search=product)
    registry = AssistantToolRegistry(sources=sources, store=None, memories=None)
    context = {"space": {"id": 1, "source_ids": [sid], "all_active": False,
                          "video_ids": [target, outside, ignored, removed, foreign], "scope_version": 1},
               "thread": {"id": "synthetic"}}
    value = SimpleNamespace(db=db, artifacts=artifacts, lexical=lexical, dense=dense,
        product=product, sources=sources, registry=registry, context=context,
        target=target, metadata=metadata, outside=outside, raw_text=raw_text)
    value.foreign = foreign
    yield value


def search(p, query, *, scope="all", context=None, **kwargs):
    return asyncio.run(p.registry.search_knowledge(KnowledgeSearchArgs(query=query,
        sources=["collection"], collection_scope=scope, **kwargs), call_id="pg-search",
        run_context=context or p.context))


def test_registry_real_bm25_hybrid_hint_and_current_scope(assistant_pg, monkeypatch):
    p = assistant_pg
    captured = []
    actual = p.product.search_with_raw
    def observe(*args, **kwargs):
        raw, result = actual(*args, **kwargs)
        captured.append(raw)
        return raw, result
    monkeypatch.setattr(p.product, "search_with_raw", observe)
    result = search(p, "UniqueTarget", scope="transcript_chunk")
    assert result["status"] == "ok"
    assert [c["video_id"] for c in result["items"][0]["candidates"]] == [p.target]
    raw = captured[-1]
    assert raw.plan.scope == "transcript_chunk" and raw.executed_mode == "lexical"
    assert raw.index_identity["lexical_index_version"] == RANKING_VERSION
    assert all(hit.lexical_score > 0 for hit in raw.raw_hits)
    with p.db.connect(read_only=True) as conn:
        check_index(conn)
    assert p.lexical.search("UniqueTarget", level="transcript_chunk",
        filters=RetrievalFilters(video_ids=(p.foreign,))) == []
    assert p.dense.statistics()["index"]["ready"]
    model = project_tool_result("search_knowledge", result, result_ref="run-result:r:search", sources=p.sources)
    card = model["items"][0]["candidates"][0]
    assert len(card["read_hints"]) == 1
    read_args = card["read_hints"][0]["read_args"]
    scope = SourceScope(source_db_ids=frozenset(p.context["space"]["source_ids"]), video_ids=frozenset({p.target}))
    read = p.sources.read(call_id="read", scope=scope, **read_args)
    assert read.status == "ok" and "UniqueTarget" in read.items[0]["content"]
    start = read.coverage["read_position"]["start"]
    assert start > 0 and read.items[0]["content"] == p.raw_text[start:]
    assert p.sources.read(call_id="narrowed", scope=SourceScope(video_ids=frozenset({p.outside})), **read_args).error_code == "source_out_of_scope"
    before = len(captured)
    assert search(p, "如何核对 UniqueTarget", scope="transcript_chunk")["status"] == "ok"
    hybrid = captured[-1]
    assert len(captured) == before + 1 and hybrid.executed_mode == "hybrid"
    assert hybrid.candidate_counts["lexical"] and hybrid.candidate_counts["dense"]
    assert hybrid.index_identity["lexical_index_version"] == RANKING_VERSION
    assert hybrid.index_identity["model_id"] == "synthetic/fixed512"
    # Short common path retains ILIKE; no forced F1 navigation=False behavior.
    assert search(p, "al", scope="transcript_chunk")["status"] == "ok"
    short = captured[-1]
    assert short.index_identity["lexical_index_version"] == INDEX_VERSION
    assert all(h.retrieval_method == "lexical_substring_fallback" for h in short.raw_hits)
    print({"bm25_index": raw.index_identity["lexical_index_version"], "visible_video_ids": [p.target],
           "hint_read_start": start, "hybrid_counts": hybrid.candidate_counts,
           "embedding_profile": hybrid.index_identity["embedding_profile"], "short_index": INDEX_VERSION})


def test_real_composite_metadata_and_missing_bm25_fail_closed(assistant_pg, monkeypatch):
    from psycopg.conninfo import conninfo_to_dict
    p = assistant_pg
    context = deepcopy(p.context)
    context["space"].update(all_active=True, video_ids=[p.metadata])
    for scope in ("all", "video"):
        for token in ("TitleUnique", "AuthorUnique", "DescriptionUnique"):
            result = search(p, token, scope=scope, context=context)
            assert result["status"] == "ok"
            card = result["items"][0]["candidates"][0]
            assert card["video_id"] == p.metadata and card["read_hints"] == []
    result = search(p, "TitleUnique", context=context, mode="metadata", uploader="AuthorUnique")
    assert result["status"] == "ok" and result["items"][0]["coverage"]["exhaustive"]
    paging = deepcopy(context)
    paging["space"]["video_ids"] = [p.target, p.metadata]
    first = search(p, None, context=paging, mode="metadata", limit=1)
    assert first["next_cursor"]
    second = search(p, None, scope="transcript_chunk", context=paging, mode="metadata",
        limit=1, cursor=first["next_cursor"])
    assert second["status"] == "ok" and second["next_cursor"] is None
    assert first["source_refs"] != second["source_refs"]
    assert search(p, "TitleUnique", scope="transcript_chunk", context=context)["status"] == "empty"
    name = conninfo_to_dict(p.db.pg.config.database_url)["dbname"]
    assert name.startswith("shiliu_bm25_fixture_")
    with admin(name) as c:
        c.execute("ALTER INDEX shiliu.retrieval_units_chunk_bm25 RENAME TO assistant_missing_bm25")
    try:
        unavailable = search(p, "UniqueTarget", scope="transcript_chunk")
        assert unavailable["status"] == "unavailable"
        assert not unavailable["items"][0]["candidates"]
    finally:
        with admin(name) as c:
            c.execute("ALTER INDEX shiliu.assistant_missing_bm25 RENAME TO retrieval_units_chunk_bm25")
    print({"composite_unique_fields": ["title", "uploader", "description"],
           "scopes": ["all", "video"], "missing_bm25_status": unavailable["status"]})
