"""Explicit opt-in offline P2 acceptance; not part of model-free test discovery.

Run this file by name with the existing locked qwen extra and both offline flags.
Only synthetic source bytes and the already installed pinned model are used.
"""

import json
import time
from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.ask.deep.f1_tools import F1TranscriptTool
from shiliu.retrieval.dense import PgExactDenseIndex
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.product_search import ProductSearchFilterRequest
from shiliu.retrieval.qwen import QwenEmbeddingProvider
from shiliu.retrieval.service import RetrievalService
from shiliu.retrieval.coordinator import ProjectionWorker
from test_collection_retrieval import add_video, product_composition


def test_offline_qwen_chinese_acceptance(collection_db, tmp_path):
    started = time.monotonic()
    db = collection_db
    artifacts = ArtifactStore(tmp_path / "qwen-artifacts", db)
    lexical = RetrievalService(db=db, artifacts=artifacts)
    provider = QwenEmbeddingProvider()
    dense = PgExactDenseIndex(db=db, provider=provider, lexical=lexical)
    resources = db, artifacts, lexical, dense
    corpus = [
        "智能体使用工具读取文件并检索原始证据。MCP 协议连接模型与文件工具。",
        "忘记账户密码后，可以通过验证邮箱身份来重置密码，重新登录账户。",
        "PostgreSQL 的 pgvector 扩展存储向量，通过余弦距离进行精确检索。",
        "数据库租约使用 owner 和 epoch 拒绝过期工作者，迟到结果不能覆盖新版本。",
        "ASR 将音频语音识别为带时间戳的字幕，原始字幕用于重建引用。",
        "收藏管理支持多个收藏夹，已读标记和个人笔记帮助整理视频。",
    ]
    videos = [add_video(resources, i + 1, text) for i, text in enumerate(corpus)]
    db.update_video(videos[5][1], title="收藏管理界面与个人笔记")
    dense.rebuild()
    report = []
    for query, expected in [
        ("怎样让智能体通过 MCP 调用文件工具", 0),
        ("如何找回忘记的登录密码", 1),
        ("pgvector cosine 向量检索", 2),
        ("如何阻止旧 worker 的迟到结果覆盖更新", 3),
        ("把音频转成带时间的字幕", 4),
    ]:
        hits = dense.search(query, level="transcript_chunk", top_k=3)
        ranks = [h.video_id for h in hits]
        report.append(dict(query=query, expected_video=videos[expected][1], top3=ranks))
        assert videos[expected][1] in ranks
    # Short navigation, title, constrained F1, and immediate invalidation use the
    # same real database/profile and exact raw evidence as the semantic cases.
    assert lexical.search("工具", level="transcript_chunk")[0].video_id == videos[0][1]
    report.append(dict(case="short_navigation", passed=True))
    assert lexical.search("收藏管理", level="video")[0].video_id == videos[5][1]
    report.append(dict(case="title_condition", passed=True))
    _, _, evidence = product_composition(resources)
    f1 = F1TranscriptTool(evidence, provider, lexical)
    sid, vid = videos[0]
    result = f1.search(
        "MCP 文件工具", filters=ProductSearchFilterRequest(source_db_id=sid)
    )
    assert result["spans"] and {s.video_id for s in result["spans"]} == {vid}
    span = result["spans"][0]
    f1.materializer.validate_current(span)
    replay = f1.materializer.reconstruct_citation(
        span.as_citation(),
        execution_id="offline-qwen",
        search_trace_id=result["trace_id"],
        query="MCP",
    )
    assert (
        replay.segment_ids == span.segment_ids and replay.quote_text == span.quote_text
    )
    assert dense.search("MCP", filters=RetrievalFilters(video_ids=())) == []
    db.set_ignored(vid, True)
    assert dense.search("MCP", filters=RetrievalFilters(video_ids=(vid,))) == []
    db.set_ignored(vid, False)
    ProjectionWorker(lexical, dense).run_one(video_id=vid)
    assert dense.search("MCP", filters=RetrievalFilters(video_ids=(vid,)))
    report.append(dict(case="scope_citation_invalidation_restore", passed=True))
    assert provider.load_count == 1
    output = dict(
        cases=report,
        model=provider.model_identity().__dict__,
        profile=dense.profile_id,
        device=provider.active_device,
        loads=provider.load_count,
        elapsed_seconds=round(time.monotonic() - started, 3),
        offline=True,
    )
    Path("/tmp/shiliu-w01-20261023/w07-qwen-cases.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
