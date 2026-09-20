from pathlib import Path

import pytest

from shiliu.research.product_service import ResearchProductService


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/shiliu/templates/research.html"
SCRIPT = ROOT / "src/shiliu/static/research.js"
BASE = ROOT / "src/shiliu/templates/base.html"


def _completion(
    *,
    task_status: str,
    answer_status: str = "not_produced",
    termination_reason: str | None = None,
    failure_class: str = "none",
    unresolved: bool = False,
) -> dict[str, object]:
    return ResearchProductService._user_completion_projection(
        task={"status": task_status},
        active_goal={"evidence_policy": {"product_execution": "receipt_bound_provider"}},
        answer_status=answer_status,
        termination_reason=termination_reason,
        failure_class=failure_class,
        artifact={} if answer_status != "not_produced" else None,
        constraint_policy={"semantic_constraints": []},
        objective_evaluator_registered=False,
        events=[],
        unresolved_side_effects=[{"status": "unknown"}] if unresolved else [],
    )


@pytest.mark.parametrize(
    ("task_status", "answer_status", "category", "label"),
    [
        ("ready", "not_produced", "waiting", "等待开始"),
        ("running", "not_produced", "running", "正在研究"),
        ("terminal", "valid_success", "success", "已完成"),
        ("terminal", "valid_partial", "partial", "部分完成"),
        ("terminal", "valid_insufficient", "insufficient", "未找到足够证据"),
        ("waiting_user", "not_produced", "waiting_user", "等待你的输入"),
        ("blocked", "not_produced", "blocked", "已暂停"),
    ],
)
def test_stage1_user_completion_categories(
    task_status: str,
    answer_status: str,
    category: str,
    label: str,
) -> None:
    completion = _completion(task_status=task_status, answer_status=answer_status)

    assert completion["category"] == category
    assert completion["label"] == label


def test_stage1_failure_unknown_and_partial_priorities_are_distinct() -> None:
    failed = _completion(
        task_status="terminal",
        answer_status="valid_insufficient",
        termination_reason="provider_error",
        failure_class="provider_failure",
    )
    unknown = _completion(
        task_status="blocked",
        termination_reason="provider_error",
        failure_class="provider_failure",
        unresolved=True,
    )
    partial = _completion(task_status="terminal", answer_status="valid_partial")

    assert failed["category"] == "failed"
    assert failed["label"] == "执行失败"
    assert unknown["category"] == "unknown"
    assert unknown["label"] == "调用状态待确认"
    assert "不会自动重试" in str(unknown["detail"])
    assert partial["category"] == "partial"


def test_stage1_list_projection_uses_the_same_product_labels() -> None:
    partial = ResearchProductService._list_completion_projection(
        {"status": "terminal", "answer_status": "valid_partial"}
    )
    unknown = ResearchProductService._list_completion_projection(
        {"status": "blocked", "provider_outcome_unknown": 1}
    )

    assert partial == {
        "status": "limited_output",
        "category": "partial",
        "label": "部分完成",
    }
    assert unknown == {
        "status": "blocked",
        "category": "unknown",
        "label": "调用状态待确认",
    }


def test_stage1_template_has_distinct_create_and_task_modes() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")

    assert "研究任务" in base
    assert "在收藏字幕中进行多轮查找，并生成带引用的回答。" in html
    assert "任务会保存，可以稍后回来查看。" in html
    assert "data-create-only" in html
    assert "data-primary-status" in html
    assert "data-recent-tasks" in html
    assert "<summary>高级信息</summary>" in html
    assert "<h3>回答</h3>" in html
    assert "<strong>尚未覆盖</strong>" in html
    assert "<h3>依据</h3>" in html
    assert "research-status-grid" not in html


def test_stage1_frontend_freezes_primary_order_and_safe_operations() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    main_order = (
        "'.research-task-nav', '.research-task-header', '[data-primary-status]',\n"
        "      '[data-answer-section]', '[data-evidence-section]', '.research-controls',\n"
        "      '[data-input-panel]', '[data-advanced-disclosure]'"
    )

    assert main_order in script
    assert "'[data-effect-panel]'" in script.split("const setPageMode", 1)[0]
    assert "operation === 'retry' && category === 'failed'" in script
    assert "if (category === 'unknown')" in script
    assert "loadTask({refreshAuxiliary: false})" in script
    assert "answerSection.append(limitations)" in script


def test_stage1_polling_refreshes_only_the_current_projection() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    polling = script.split("if (['ready', 'running'].includes(product.task.status))", 1)[1]
    polling = polling.split("async function loadTask", 1)[0]
    load_task = script.split("async function loadTask", 1)[1]
    load_task = load_task.split("createForm.addEventListener", 1)[0]

    assert "refreshAuxiliary: false" in polling
    assert "showLoading: false" in polling
    assert "loadKnowledge()" not in polling
    assert "loadPersonalWorkspace()" not in polling
    assert "method: 'POST'" not in load_task
    assert "renderTask(data.product, {refreshAuxiliary})" in load_task


def test_stage1_creation_request_contract_is_unchanged() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "if (submit.disabled) return" in script
    assert "if (!objective)" in script
    assert "success_constraints: lines(createForm.elements.constraints.value)" in script
    assert "constraint_profile: createForm.elements.constraint_profile.value" in script
    assert "run_immediately: true" in script
    assert "history.pushState({}, '', `/research/${encodeURIComponent(taskId)}`)" in script
