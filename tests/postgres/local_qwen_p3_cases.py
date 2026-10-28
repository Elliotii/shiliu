# ruff: noqa: F811
"""Explicit opt-in P3 semantic checks; installed pinned Qwen, strictly offline."""

import json
import os
from pathlib import Path
import time

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.memory_jobs import MemoryJobWorker
from shiliu.assistant.wiki_retrieval import WikiHybridIndex
from shiliu.assistant.wiki_jobs import WikiProjectionWorker
from shiliu.retrieval.qwen import QwenEmbeddingProvider
from test_wiki import wiki_parts  # noqa: F401


def test_offline_memory_and_wiki_chinese_cases(wiki_parts):
    assert (
        os.environ.get("HF_HUB_OFFLINE") == "1"
        and os.environ.get("TRANSFORMERS_OFFLINE") == "1"
    )
    db, _, wiki, space, msg, _, _ = wiki_parts
    started = time.monotonic()
    provider = QwenEmbeddingProvider()
    memories = MemoryService(db, provider=provider)
    memory_corpus = [
        "晚上需要照顾家人，只能白天安排学习",
        "久坐腰部不适，倾向每半小时起身活动",
        "习惯用PostgreSQL验证事务与并发控制",
        "最近准备Agent应用开发方向的实习面试",
        "下个月参加日语考试，正在准备语言复习",
        "写代码时偏好小步提交并先跑定向测试",
    ]
    rows = [
        memories.save_explicit(
            text=text,
            subject_key=f"offline{i}",
            kind="context",
            scope_kind="user",
            scope_id=None,
            operation_key=f"offline{i}",
            stated_text=text,
            stated_at="2026-10-17T13:45:38+00:00",
        )
        for i, text in enumerate(memory_corpus)
    ]
    worker = MemoryJobWorker(memories, owner="offline-memory")
    for _ in rows:
        assert worker.run_once()["status"] == "ready"
    memory_cases = []
    for query, target in [
        ("怎样安排复习才不会影响家庭照护？", 0),
        ("阅读时怎样安排活动休息？", 1),
        ("我的数据库练习该选哪个系统？", 2),
        ("最近的求职方向是什么？", 3),
        ("我有什么语言考试安排？", 4),
        ("怎样组织代码变更的验证和版本记录？", 5),
    ]:
        result = memories.recall_with_status(query, space_id=space, limit=3)
        ids = [r["id"] for r in result["items"]]
        memory_cases.append(dict(query=query, target=rows[target]["id"], top3=ids))
        assert rows[target]["id"] in ids, (query, ids)
        assert result["semantic_index"] == "ready"
    memories.correct(
        rows[2]["id"],
        text="数据库练习现改为SQLite兼容性研究",
        expected_version=1,
        operation_key="offline-correct",
    )
    assert all(
        "semantic" not in r["recall_reasons"]
        for r in memories.recall_with_status("PostgreSQL", space_id=space)["items"]
        if r["id"] == rows[2]["id"]
    )
    memories.forget(rows[0]["id"], expected_version=1, operation_key="offline-forget")
    assert all(
        r["id"] != rows[0]["id"] for r in memories.recall("家庭照护", space_id=space)
    )
    memory_cases.append(
        dict(case="correct_and_forget_immediately_fence_dense", passed=True)
    )
    wiki_corpus = [
        (
            "事务与锁",
            "PG行锁保护短事务，先取得Job和业务行锁，再用数据库时钟校验租约，拒绝旧epoch的迟到写入。",
        ),
        ("语音字幕", "ASR将音频中的语音转成带时间戳的字幕，保存原始字幕用于重建引用。"),
        ("密码找回", "忘记登录密码后，通过验证邮箱身份重置密码，然后重新登录账户。"),
        (
            "向量检索",
            "pgvector在PostgreSQL中存储512维向量，用cosine距离精确排序，先过滤范围和版本再取TopK。",
        ),
        (
            "MCP文件工具",
            "MCP协议连接智能体与文件工具，模型通过工具调用读取文件并取得原始证据。",
        ),
        (
            "知识页范围",
            "Wiki只检索当前Space和任务范围中的有效块，Memory遗忘或来源失效后发送前重新核验。",
        ),
    ]
    pages = [
        wiki.save_discussion(
            space_id=space,
            title=title,
            purpose="离线合成检索验证",
            source_message_id=msg,
            operation_key=f"wiki-offline{i}",
            blocks=[dict(role="analysis", heading=title, markdown=body)],
        )
        for i, (title, body) in enumerate(wiki_corpus)
    ]
    index = WikiHybridIndex(provider, wiki=wiki)
    wiki_worker = WikiProjectionWorker(index, owner="offline-wiki")
    index.search("离线检索", space_id=space)
    for _ in pages:
        assert wiki_worker.run_once()["status"] == "ready"
    wiki_cases = []
    for query, target in [
        ("如何阻止旧worker提交过期计算结果？", 0),
        ("把音频转成带时间的文字", 1),
        ("怎样找回忘记的登录口令？", 2),
        ("pgvector cosine 的范围过滤在哪里做？", 3),
        ("怎样让Agent通过MCP读取本地文档？", 4),
        ("个人记忆删除后如何避免知识页继续使用？", 5),
    ]:
        result = index.search(query, space_id=space)
        ids = [r["page_id"] for r in result["candidates"]]
        wiki_cases.append(dict(query=query, target=pages[target]["id"], top3=ids))
        assert pages[target]["id"] in ids, (query, ids)
        assert result["coverage"]["dense_candidates"] > 0
    wiki.manage_page(
        pages[2]["id"],
        space_id=space,
        action="archive",
        expected_version=1,
        operation_key="offline-archive",
    )
    assert all(
        r["page_id"] != pages[2]["id"]
        for r in index.search("密码", space_id=space)["candidates"]
    )
    wiki_cases.append(
        dict(case="archive_immediately_invalidates_current_set", passed=True)
    )
    assert provider.load_count == 1
    output = dict(
        source_kind="synthetic author verification",
        memory_cases=memory_cases,
        wiki_cases=wiki_cases,
        model=provider.model_identity().__dict__,
        memory_profile=memories.profile.profile_id,
        wiki_profile=index.profile.profile_id,
        device=provider.active_device,
        loads=provider.load_count,
        offline=True,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )
    Path("/tmp/shiliu-w01-20261023/p3-qwen-author-final-cases.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
