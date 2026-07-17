from __future__ import annotations

import json
import re
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from shiliu.llm import CompletionResponse, OpenAICompatibleProvider
from shiliu.taxonomy.discovery import (
    BatchedDiscoverySpikeService,
    LocalDiscoveryOutput,
    build_compact_corpus,
)
from shiliu.taxonomy.model_calls import AuditedJsonCaller


def make_card(index: int, evidence: str) -> dict:
    content_id = f"bilibili:BV{index:010d}:p1"
    return {
        "content_key": content_id,
        "evidence_level": evidence,
        "discovery_eligible": evidence != "D",
        "discovery_view": {
            "content_id": content_id,
            "title": f"标题 {index}",
            "uploader": f"绝不发送的UP {index}",
            "description": f"仅C发送的简介 {index} " + "长" * 400,
            "one_line_summary": f"结论 {index}",
            "key_points": ["重复观点", " 重复观点 ", "观点二", "观点三", "观点四"],
            "projects_tools_models": ["Tool", "Tool", "Model", "Project", "Paper", "Extra"],
            "evidence_level": evidence,
        },
    }


class FakeRepository:
    def __init__(self, cards: list[dict]) -> None:
        self.cards = cards

    def get_snapshot(self, snapshot_id: int):
        return {"id": snapshot_id, "snapshot_hash": "2" * 64, "cards": self.cards}


class FakeRawProvider:
    model = "fake-model"
    thinking_enabled = True
    reasoning_effort = None

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        if "局部候选发现器" in prompt:
            ids = _ids_after(prompt, "本批卡片：")
            output = {
                "content_types": [_content_type_candidate("教程", ids[:2])],
                "domains": [
                    {
                        **_candidate("软件工程", ids[:3]),
                        "provisional_id": "ld_software",
                        "includes": ["软件工程实践"],
                        "excludes": ["纯工具新闻"],
                        "suggested_level": "primary",
                        "parent_hint": None,
                        "stability_reason": "可长期复用",
                    }
                ],
                "topics": [_candidate("近期专题", ids[:1])],
                "entities": [
                    {**_candidate("Tool", ids[:1]), "entity_type": "tool"}
                ],
                "ambiguous_ids": [],
            }
        elif "全局候选归并器" in prompt:
            output = {
                "content_types": [
                    {
                        "id": "ct_01",
                        **_candidate("教程", ["C001"]),
                        "includes": ["教学"],
                        "excludes": ["新闻"],
                        "representative_ids": ["C001"],
                        "parent_id": None,
                        "node_type": "content_type",
                    }
                ],
                "domains": [
                    {
                        "id": "d_01",
                        **_candidate("软件工程", ["C001", "C002"]),
                        "includes": ["工程实践"],
                        "excludes": ["纯观点"],
                        "representative_ids": ["C001"],
                        "parent_id": None,
                        "node_type": "domain",
                        "children": [
                            {
                                "id": "d_01_01",
                                **_candidate("开发工具", ["C001"]),
                                "includes": ["开发工具工程"],
                                "excludes": ["通用教程"],
                                "representative_ids": ["C001"],
                                "parent_id": "d_01",
                                "node_type": "domain",
                            }
                        ],
                    }
                ],
                "topics": [_candidate("近期专题", ["C001"])],
                "entities": [
                    {**_candidate("Tool", ["C001"]), "entity_type": "tool"}
                ],
                "consolidation_notes": ["合并同义候选"],
            }
        elif "试分类器" in prompt:
            ids = _ids_after(prompt, "卡片行：")
            output = {
                "assignments": [
                    {
                        "content_id": content_id,
                        "content_type_ids": [] if content_id == "C021" else ["ct_01"],
                        "primary_domain_path": [] if content_id == "C021" else ["d_01"],
                        "secondary_domain_ids": [],
                        "dynamic_topics": [],
                        "entities": [],
                        "certainty": "low" if content_id == "C021" else "high",
                        "rejection_reason": (
                            "insufficient_evidence" if content_id == "C021" else None
                        ),
                    }
                    for content_id in ids
                ]
            }
        else:
            raise AssertionError(prompt[:100])
        content = json.dumps(output, ensure_ascii=False)
        return CompletionResponse(
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": len(prompt) // 2, "completion_tokens": 10},
            response_id="fake-response",
        )


def _candidate(name: str, ids: list[str]) -> dict:
    return {"name": name, "definition": f"{name}定义", "supporting_ids": ids}


def test_local_topic_ids_are_accepted_but_not_persisted() -> None:
    value = LocalDiscoveryOutput.model_validate(
        {
            "content_types": [],
            "domains": [],
            "topics": [
                {
                    "provisional_id": "lt_recent_topic",
                    "name": "近期专题",
                    "definition": "阶段性关注主题",
                    "supporting_ids": ["C001"],
                }
            ],
            "entities": [],
            "ambiguous_ids": [],
        }
    )

    assert value.topics[0].provisional_id == "lt_recent_topic"
    assert "provisional_id" not in value.model_dump(mode="json")["topics"][0]


def _content_type_candidate(name: str, ids: list[str]) -> dict:
    return {
        **_candidate(name, ids),
        "provisional_id": "lct_tutorial",
        "includes": ["教学"],
        "excludes": ["新闻"],
    }


def _ids_after(prompt: str, marker: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'"(C\d{3})"', prompt.split(marker, 1)[1])))


def test_compact_view_is_evidence_aware_and_deduplicated() -> None:
    corpus = build_compact_corpus(
        [make_card(1, "A"), make_card(2, "B"), make_card(3, "C"), make_card(4, "D")]
    )
    a, b, c, d = corpus["rows"]
    assert a[:4] == ["C001", "A", "标题 1", "结论 1"]
    assert a[4] == ["重复观点", "观点二", "观点三"]
    assert a[5] == ["Tool", "Model", "Project", "Paper", "Extra"]
    assert "仅C发送的简介" not in json.dumps(a, ensure_ascii=False)
    assert "绝不发送的UP" not in json.dumps(corpus, ensure_ascii=False)
    assert b[1] == "B"
    assert c[:3] == ["C003", "C", "标题 3"]
    assert len(c[3]) == 300
    assert d == ["C004", "D", "标题 4"]


def test_batched_spike_keeps_calls_small_and_assigns_d_level(tmp_path) -> None:
    cards = [
        make_card(index, "A" if index <= 7 else "B" if index <= 14 else "C")
        for index in range(1, 21)
    ] + [make_card(21, "D")]
    provider = FakeRawProvider()
    service = BatchedDiscoverySpikeService(
        repository=FakeRepository(cards),  # type: ignore[arg-type]
        provider_factory=lambda role: provider,
        output_dir=tmp_path,
    )
    result = service.run_spike(2, batch_size=20, seed=1)
    assert result["eligible_count"] == 20
    assert result["trial_only_count"] == 1
    assert len(result["local_calls"]) == 1
    assert len(result["assignment_calls"]) == 2
    assert result["assignment_count"] == 21
    assert result["novelty_pool_count"] == 1
    assert result["totals"]["usage"]["prompt_tokens"] > 0
    run_dir = tmp_path / result["run_id"]
    assert (run_dir / "local-01" / "raw-response.txt").is_file()
    assert (run_dir / "taxonomy-draft.json").is_file()
    assert json.loads((run_dir / "novelty-pool.json").read_text())[0][
        "content_id"
    ] == "C021"
    assert json.loads((run_dir / "novelty-pool.json").read_text())[0][
        "content_key"
    ] == cards[-1]["content_key"]


class TinyOutput(BaseModel):
    value: str


class InvalidProvider:
    model = "invalid"
    thinking_enabled = True
    reasoning_effort = None

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        return CompletionResponse("{\"wrong\":1}", "stop", None, "raw-1")


class RepairProvider(InvalidProvider):
    model = "repair"

    def complete_raw(self, prompt: str, *, max_tokens: int | None = None):
        assert "SECRET_ORIGINAL_CORPUS" not in prompt
        assert "校验错误" in prompt
        return CompletionResponse('{"value":"fixed"}', "stop", None, "repair-1")


def test_validation_failure_repairs_raw_response_without_replaying_prompt(tmp_path) -> None:
    caller = AuditedJsonCaller(
        provider=InvalidProvider(),  # type: ignore[arg-type]
        repair_provider=RepairProvider(),  # type: ignore[arg-type]
    )
    result, audit = caller.call(
        call_dir=tmp_path / "call",
        prompt="SECRET_ORIGINAL_CORPUS",
        prompt_version="test-v1",
        schema=TinyOutput,
        schema_hint='{"value":"string"}',
        max_tokens=100,
        input_ids=["C001"],
    )
    assert result.value == "fixed"
    assert (tmp_path / "call" / "raw-response.txt").read_text() == '{"wrong":1}'
    assert audit["repair"]["original_prompt_replayed"] is False
    assert "SECRET_ORIGINAL_CORPUS" not in (
        tmp_path / "call" / "repair-prompt.txt"
    ).read_text()


def test_raw_provider_preserves_usage_when_thinking_exhausts_final_content() -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "id": "response-1",
                    "choices": [
                        {
                            "message": {"content": "", "reasoning_content": "内部推理"},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 8192},
                },
            )

    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="model",
        thinking_enabled=True,
    )
    with patch("shiliu.llm.httpx.Client", FakeClient):
        response = provider.complete_raw("prompt", max_tokens=8192)
    assert response.content == ""
    assert response.reasoning_content == "内部推理"
    assert response.usage == {"prompt_tokens": 100, "completion_tokens": 8192}
