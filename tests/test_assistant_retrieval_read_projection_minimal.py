"""Offline wiring/position probes; no Application, database, provider or indexing."""
import asyncio
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from shiliu.assistant.contracts import KnowledgeSearchArgs as UnifiedSearchArgs
from shiliu.assistant.delivery import project_tool_result, read_evidence
from shiliu.assistant.snapshots import CapturedSource
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.domain import SubtitleSegment
from shiliu.retrieval.chunking import build_raw_subtitle_chunks


REVISION = "a" * 64
REF = f"video:7:{REVISION}"
CONTEXT = {"space": {"id": 1, "source_ids": [3], "video_ids": [7],
                     "all_active": False, "scope_version": 2},
           "thread": {"id": "thread"}}


@pytest.fixture
def probe(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline probe attempted external I/O")

    # Two ordinary short source samples: unique phrase and repeated keyword.
    text = "alpha earlier unrelated condition. " + "前文。" * 600
    text += "alpha UNIQUE_TARGET exact condition. " + "后文。" * 100
    target = text.index("alpha UNIQUE_TARGET")
    captured = CapturedSource(REVISION, "synthetic-snapshot", {
        "metadata": {"id": 7, "source_id": "BVsynthetic", "part": 1,
                     "title": "Synthetic", "uploader": "Author"},
        "materials": {"transcript": text}, "notes": [], "memberships": [],
        "material_hashes": {}, "coverage": "full_available_transcript"})
    snapshots = SimpleNamespace(capture=lambda video: captured)
    requests = []

    def product_search(request, **kwargs):
        requests.append((request, kwargs))
        result = SimpleNamespace(video_id=7, match_excerpt=text[target:target + 35],
            windows=[{"component_chunk_ids": ["chunk-target"], "best_chunk_id": "chunk-target",
                      "window_start": 60, "window_end": 65, "jump_time": 60}],
            best_unit_id="chunk-target", best_unit_type="transcript_chunk",
            retrieval_methods=("lexical",))
        return SimpleNamespace(executed_mode="lexical"), SimpleNamespace(results=[result])

    sources = CollectionSourceService(db=SimpleNamespace(connect=forbidden),
        artifacts=SimpleNamespace(), snapshots=snapshots,
        product_search=SimpleNamespace(search_with_raw=product_search))
    monkeypatch.setattr(sources, "_allowed_sources", lambda *a: {3})
    monkeypatch.setattr(sources, "visible_video_ids", lambda *a, **kw: [7])
    monkeypatch.setattr(sources, "_candidate_video_ids", lambda *a, **kw: ([7], 0))
    monkeypatch.setattr(sources, "_material_coverage", lambda ids: {})
    monkeypatch.setattr(sources, "_card", lambda video, **kw: {
        "video_id": video, "source_ref": "video:7", "title": "Synthetic",
        "matched_excerpt": kw.get("excerpt"), "available_views": ["transcript"]})
    monkeypatch.setattr(sources, "_video_is_available", lambda *a, **kw: True)
    monkeypatch.setattr(sources, "_capture_or_load", lambda *a: captured)
    registry = AssistantToolRegistry(sources=sources, memories=None, store=None)
    return SimpleNamespace(sources=sources, registry=registry, captured=captured,
                           text=text, target=target, requests=requests)


def test_unified_collection_path_keeps_all_and_search_window_is_not_model_locator(probe):
    raw = asyncio.run(probe.registry.search_knowledge(
        UnifiedSearchArgs(query="alpha", sources=["collection"]),
        call_id="search", run_context=CONTEXT))
    assert raw["status"] == "ok"
    request, kwargs = probe.requests[0]
    assert (request.mode, request.scope, request.corpus_aware) == ("auto", "all", False)
    assert kwargs["scope_video_ids"] == (7,)
    card = raw["items"][0]["candidates"][0]
    assert card["windows"][0]["component_chunk_ids"] == ["chunk-target"]
    assert card["source_ref"] == REF
    projected = project_tool_result("search_knowledge", raw,
        result_ref="run-result:r:search", sources=probe.sources)
    model_card = projected["items"][0]["candidates"][0]
    assert "windows" not in model_card and "best_unit_id" not in model_card
    assert model_card["matched_excerpt"] == card["matched_excerpt"]
    assert "UNIQUE_TARGET" in model_card["matched_excerpt"]
    # Same keyword as Search returns the earlier occurrence, outside the hit.
    repeated = probe.sources.read(call_id="read", scope=SourceScope(video_ids=frozenset({7})),
        source_ref=REF, view="transcript", query="alpha", max_characters=1000)
    assert repeated.coverage["read_position"]["start"] == 0
    assert "UNIQUE_TARGET" not in repeated.items[0]["content"]
    # A distinctive literal substring from the excerpt can recover the target.
    unique = probe.sources.read(call_id="unique", scope=SourceScope(all_active=True),
        source_ref=REF, view="transcript", query="UNIQUE_TARGET", max_characters=1000)
    assert "UNIQUE_TARGET" in unique.items[0]["content"]
    print({"hit_character": probe.target, "keyword_read": repeated.coverage["read_position"],
           "unique_read": unique.coverage["read_position"]})


@pytest.mark.parametrize("page_size", [24000, 40000])
def test_read_pages_and_capacity_projection_preserve_continuation(probe, page_size):
    text = "始。" + "合成条件。" * 9000 + "终。"
    probe.captured.snapshot["materials"]["transcript"] = text
    args = dict(scope=SourceScope(all_active=True), source_ref=REF, view="transcript")
    first = probe.sources.read(call_id="page1", **args, **(
        {} if page_size == 24000 else {"max_characters": page_size})).model_dump(mode="json")
    assert len(first["items"][0]["content"]) == page_size
    assert first["truncated"] and not first["coverage"]["read_complete"]
    raw_before = deepcopy(first)
    full = project_tool_result("collection_read", first, result_ref="run-result:r:read", sources=probe.sources)
    assert full["items"][0]["content"] == text[:page_size]
    clipped = project_tool_result("collection_read", first, result_ref="run-result:r:read",
        sources=probe.sources, body_characters=1200)
    assert first == raw_before  # projection does not rewrite the receipt
    assert clipped["coverage"]["read_result_ref"] == "run-result:r:read"
    assert clipped["coverage"]["next_read_args"]["cursor"] == clipped["next_cursor"]
    spans, _ = read_evidence("collection_read", clipped, result_ref="run-result:r:read")
    assert spans[0]["end"] == 1200 and spans[0]["total"] == len(text)
    continuation = probe.sources.read(call_id="clipped-next", **args, cursor=clipped["next_cursor"])
    assert continuation.coverage["read_position"]["start"] == 1200
    parts, cursor = [first["items"][0]["content"]], first["next_cursor"]
    while cursor:
        page = probe.sources.read(call_id="next", **args, cursor=cursor, max_characters=page_size)
        assert page.coverage["read_position"]["start"] == sum(map(len, parts))
        parts.append(page.items[0]["content"])
        cursor = page.next_cursor
    assert "".join(parts) == text and page.coverage["read_complete"]
    print({"page_size": page_size, "total": len(text), "pages": list(map(len, parts)),
           "clipped_end": spans[0]["end"], "continued_start": continuation.coverage["read_position"]["start"]})


def test_run_read_result_recovers_receipt_field_with_absolute_source_position(probe, monkeypatch):
    receipt = probe.sources.read(call_id="original", scope=SourceScope(all_active=True),
        source_ref=REF, view="transcript", query="UNIQUE_TARGET", max_characters=1000).model_dump(mode="json")
    original = deepcopy(receipt)
    checks = []

    def resolve(ref, **kwargs):
        assert ref == "run-result:r:original"
        assert kwargs == {"current_thread_id": "thread", "current_scope_version": 2}
        return {"result": receipt, "name": "collection_read", "result_ref": ref}

    probe.registry.store = SimpleNamespace(resolve_run_result=resolve)
    # Dependency/scope validation is a separate PG contract, not claimed here.
    monkeypatch.setattr(probe.registry, "_validate_historical_result", lambda *a, **kw: checks.append(kw))
    recovered = asyncio.run(probe.registry.execute(name="run_read_result", call_id="recover",
        arguments={"result_ref": "run-result:r:original", "field": "content", "start": 20,
                   "max_characters": 1000}, run_context=CONTEXT))
    assert checks and recovered["status"] == "ok"
    assert recovered["items"][0]["value"] == receipt["items"][0]["content"][20:]
    source_start = receipt["coverage"]["read_position"]["start"]
    assert recovered["coverage"]["read_spans"][0]["start"] == source_start + 20
    assert receipt == original


@pytest.mark.parametrize("scope", ["all", "video", "transcript_chunk"])
def test_explicit_scope_mixed_wiki_and_one_request_per_variant(probe, monkeypatch, scope):
    wiki_calls = []
    def wiki_search(*args, **kwargs):
        wiki_calls.append((args, kwargs))
        return {"source": "wiki", "status": "empty", "candidates": [], "coverage": {}}
    probe.registry.wiki = SimpleNamespace(
        retrieval=SimpleNamespace(search=wiki_search), list_pages=lambda **kw: [])
    probe.registry.store = SimpleNamespace(tool_execution_scope=lambda *a: nullcontext())
    result = asyncio.run(probe.registry.execute(name="search_knowledge", arguments={
        "query": "alpha", "query_variants": ["beta", "gamma"], "collection_scope": scope},
        call_id="scoped", run_context={**CONTEXT, "run": {"id": "r", "run_epoch": 1}}))
    assert result["status"] == "ok"
    assert len(probe.requests) == 3
    assert [request.scope for request, _ in probe.requests] == [scope] * 3
    assert [request.query for request, _ in probe.requests] == ["alpha", "beta", "gamma"]
    assert len(wiki_calls) == 1
    assert "collection_scope" not in wiki_calls[0][1]
    group = next(g for g in result["items"] if g["source"] == "collection")
    assert group["coverage"]["collection_scope"] == scope
    assert all(d["collection_scope"] == scope for d in group["coverage"]["retrieval_details"])
    monkeypatch.setattr(probe.sources, "_transcript_available_ids", lambda ids: ids)
    probe.requests.clear()
    asyncio.run(probe.registry.search_knowledge(UnifiedSearchArgs(
        query="alpha", sources=["collection"], require_transcript=True),
        call_id="available", run_context=CONTEXT))
    assert len(probe.requests) == 1 and probe.requests[0][0].scope == "all"


def test_metadata_ignores_scope_without_product_search(probe, monkeypatch):
    monkeypatch.setattr(probe.sources, "_ordered_metadata_ids", lambda *a, **kw: [7])
    results = []
    for scope in ("all", "transcript_chunk"):
        result = asyncio.run(probe.registry.search_knowledge(UnifiedSearchArgs(
            mode="metadata", collection_scope=scope, sources=["collection"]),
            call_id="metadata", run_context=CONTEXT))
        results.append(result["items"][0]["candidates"])
    assert results[0] == results[1] and not probe.requests


def test_bootstrap_still_issues_one_default_all_request(probe):
    from shiliu.assistant.runtime import AssistantExecutionGraph
    context = deepcopy(CONTEXT)
    context["run"] = {"working_state": {"execution_budget": {}}, "tool_count": 0,
                      "status": "running", "run_epoch": 1}
    context["thread"]["messages"] = [{"id": "u", "role": "user", "run_id": "r", "content": "alpha"}]
    context["thread"]["runs"] = []
    calls = []
    store = SimpleNamespace(run_context=lambda rid: context, get_thread=lambda tid: context["thread"],
        set_knowledge_bootstrap=lambda *a, **kw: None, begin_tool_call=lambda *a, **kw: None,
        dispatch_tool=lambda *a, **kw: None, get_run=lambda rid: context["run"],
        task_space=lambda tid: context["space"], execution_remaining=lambda rid: 100,
        finish_tool_call=lambda *a, **kw: calls.append(kw), save_step=lambda *a, **kw: None,
        initialize_execution_budget=lambda *a, **kw: None)
    graph = SimpleNamespace(store=store, tools=probe.registry, max_steps=32, max_tool_calls=64,
        _discovery_request=lambda text: (True, ["collection"], False), _run_epoch_active=lambda state: True)
    asyncio.run(AssistantExecutionGraph._bootstrap_knowledge(graph,
        {"run_id": "r", "epoch": 1, "tool_count": 0, "step_count": 0, "usage": {}}))
    assert len(probe.requests) == len(calls) == 1
    assert probe.requests[0][0].scope == "all"


@pytest.fixture(params=[False, True], ids=["unicode", "escaped-unicode"])
def mapped_probe(probe, monkeypatch, request):
    content = 'alpha 重复原话 "引号" \\换行\n' + "中" * 900
    segments = [{"from": 100, "to": 110, "content": content},
                {"from": 111, "to": 112, "content": " \n "},
                {"content": content, "to": 10, "from": 0}]
    elements = [json.dumps(segment, ensure_ascii=request.param, indent=2) for segment in segments]
    raw = " \n[ \n" + ", \n \t".join(elements) + "\n ] \n"
    probe.captured.snapshot["materials"] = {"raw_subtitle": raw}
    version = sha256(raw.encode()).hexdigest()
    probe.captured.snapshot["material_hashes"] = {"raw_subtitle": version}
    probe.captured.snapshot["metadata"].update(platform="bilibili", source_id="BVsynthetic", part=1)
    chunks = build_raw_subtitle_chunks(platform="bilibili", source_id="BVsynthetic", part=1,
        source_type="human", segments=[SubtitleSegment.model_validate(s) for s in segments])
    chunk = chunks[-1]
    unit_id = "transcript:bilibili:BVsynthetic:p1:" + chunk.chunk_id
    row = dict(unit_id=unit_id, video_id=7, platform="bilibili", source_id="BVsynthetic", part=1,
        raw_subtitle_path="artifact:synthetic", subtitle_source="human", subtitle_language="zh",
        chunk_id=chunk.chunk_id, start_time=chunk.start_time, end_time=chunk.end_time,
        source_text=chunk.text, content_hash=chunk.content_hash)
    @contextmanager
    def connect(**kwargs):
        yield SimpleNamespace(execute=lambda statement, values: SimpleNamespace(fetchall=lambda: [row]))
    probe.sources.db = SimpleNamespace(connect=connect, workspace_id="personal:local_operator")
    probe.sources.artifacts = SimpleNamespace(raw_bytes=lambda *a, **kw: raw.encode(),
        objects=SimpleNamespace(manifest=lambda **kw: {"logical_key": "video:7:subtitle-raw.json"}))
    def search(request, **kwargs):
        return SimpleNamespace(executed_mode="lexical"), SimpleNamespace(results=[SimpleNamespace(
            video_id=7, match_excerpt=content, windows=({"best_chunk_id": unit_id},),
            best_unit_id=unit_id, best_unit_type="transcript_chunk")])
    probe.sources.product_search = SimpleNamespace(search_with_raw=search)
    probe.raw, probe.row = raw, row
    # Positions computed from the construction, independently of the decoder under test.
    probe.element_start = len(" \n[ \n") + sum(len(e) for e in elements[:2]) + 2 * len(", \n \t")
    return probe


def test_exact_hint_after_projection_reads_later_original_ordinal(mapped_probe):
    p = mapped_probe
    raw = asyncio.run(p.registry.search_knowledge(UnifiedSearchArgs(query="alpha", sources=["collection"]),
        call_id="search", run_context=CONTEXT))
    projected = project_tool_result("search_knowledge", raw, result_ref="run-result:r:search", sources=p.sources)
    card = projected["items"][0]["candidates"][0]
    assert "windows" not in card and len(card["read_hints"]) == 1
    read_args = card["read_hints"][0]["read_args"]
    result = p.sources.read(call_id="hint", scope=SourceScope(all_active=True), **read_args)
    start = max(0, p.element_start - 500)
    assert result.coverage["read_position"]["start"] == start > 0
    assert result.items[0]["content"] == p.raw[start:]
    assert result.coverage["model_delivery"] == "pending_context_projection"
    assert read_evidence("search_knowledge", projected, result_ref="run-result:r:search")[0] == []
    # Source/ref, view, video and narrowed access retain the existing Read vetoes.
    for changes, code in [({"source_ref": "video:8:" + REVISION}, "cursor_scope_mismatch"),
                          ({"view": "summary"}, "cursor_scope_mismatch"),
                          ({"revision": "b" * 64}, "revision_conflict"),
                          ({"query": "alpha"}, "query_cursor_conflict")]:
        denied = p.sources.read(call_id="conflict", scope=SourceScope(all_active=True), **(read_args | changes))
        assert denied.error_code == code
    print({"encoding": "escaped" if "\\u" in p.raw else "unicode", "original_ordinal": 2,
           "target_element_start": p.element_start, "read_start": start})


def test_hint_mismatch_retains_candidate_without_fallback(mapped_probe, monkeypatch):
    p = mapped_probe
    p.captured.snapshot["material_hashes"]["raw_subtitle"] = "b" * 64
    raw = asyncio.run(p.registry.search_knowledge(UnifiedSearchArgs(query="alpha", sources=["collection"]),
        call_id="stale", run_context=CONTEXT))
    card = raw["items"][0]["candidates"][0]
    assert raw["status"] == "ok" and card["read_hints"] == []
    assert card["read_hint_unavailable_reasons"] == ["source_version_mismatch"]
    p.captured.snapshot["material_hashes"]["raw_subtitle"] = sha256(p.raw.encode()).hexdigest()
    p.row["content_hash"] = "b" * 64
    unmapped = asyncio.run(p.registry.search_knowledge(UnifiedSearchArgs(query="alpha", sources=["collection"]),
        call_id="unmapped", run_context=CONTEXT))
    card = unmapped["items"][0]["candidates"][0]
    assert unmapped["status"] == "ok" and card["read_hints"] == []
    assert card["read_hint_unavailable_reasons"] == ["chunk_segment_mapping_failed"]
    monkeypatch.setattr(p.sources, "_video_is_available", lambda *a, **kw: False)
    assert p.sources.read(call_id="denied", scope=SourceScope(video_ids=frozenset({8})),
        source_ref=REF, view="transcript").error_code == "source_out_of_scope"
