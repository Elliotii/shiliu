from __future__ import annotations

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.web import create_web_app
from test_v5_5_goal2_knowledge_product import _publish
from test_v5_b_stage1_knowledge_workspace import _fixture_core, _intake, _terminal_task


def test_goal3_primary_navigation_and_contextual_handoffs(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))

    home = client.get("/")
    assert home.status_code == 200
    assert '<a href="/knowledge">知识</a>' in home.text
    assert "稍后回看" in home.text
    assert "语料实验" in home.text
    assert "分类实验</a>" not in home.text

    search = client.get("/search?q=MCP")
    assert search.status_code == 200
    assert "基于这些结果提问" in search.text
    assert "继续做长程研究" in search.text
    assert "Advanced：查看排序说明" in search.text

    ask = client.get("/ask?q=MCP")
    assert ask.status_code == 200
    assert "这还需要多步骤、可持续的研究吗" in ask.text
    assert "只有你点击后才会进入" in ask.text

    research = client.get("/research?objective=MCP&route_query=Skill")
    assert research.status_code == 200
    assert '>MCP</textarea>' in research.text
    assert 'value="Skill"' in research.text


def test_goal3_research_primary_hierarchy_and_cold_start_copy(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    page = client.get("/research")

    assert page.status_code == 200
    assert "研究结果" in page.text
    assert "当前字幕证据" in page.text
    assert "保存这次研究，在以后继续使用" in page.text
    assert "下一步可以做什么" in page.text
    assert "Advanced / Diagnostics / 维护信息" in page.text
    assert "还没有设置当前关注" in client.get("/static/research.js").text
    assert "不会自动推断或后台修改" in page.text


def test_goal3_global_knowledge_rediscovery_uses_existing_assets(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "v55-goal3-knowledge")
    _intake(core, task_id, "v55-goal3-knowledge")
    _publish(core, task_id, command_id="v55:g3:publish")
    client = TestClient(create_web_app(core))

    page = client.get("/knowledge")

    assert page.status_code == 200
    assert "已保存的知识" in page.text
    assert "核心结论" in page.text
    assert "来源仍有效" in page.text
    assert "查看原始字幕" in page.text
    assert "基于这个主题提出新问题" in page.text
    assert f"/research/{task_id}?route_query=" in page.text
    assert "task_id" not in page.text


def test_goal3_current_focus_thin_ui_reuses_explicit_focus_contract(app_paths) -> None:
    core = _fixture_core(app_paths)
    task_id = _terminal_task(core, "v55-goal3-focus")
    client = TestClient(create_web_app(core))

    response = client.post(
        f"/api/research/product/tasks/{task_id}/workspace/records",
        json={
            "command_id": "v55:g3:focus",
            "record_kind": "focus_state",
            "semantic_key": "current focus",
            "payload": {"topic": "Agent Skill", "state": "focused"},
            "source_refs": [],
            "reason": "user explicitly set current focus in thin product UI",
        },
    )

    assert response.status_code == 201
    outcome = response.json()["outcome"]
    assert outcome["authority_class"] == "user_authored"
    assert outcome["effective_status"] == "confirmed"
    assert outcome["user_state_authority"] is True
