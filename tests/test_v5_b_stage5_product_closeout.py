from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import SCHEMA_VERSION
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.knowledge_contracts import (
    AssessArtifactRouteRequest,
    BuildKnowledgeArtifactRequest,
    BuildTopicPageRequest,
    ProceedArtifactRouteRequest,
    ProposeFactUpdateRequest,
    ReviewFactUpdateRequest,
    ReviewTopicPageRequest,
    SubmitKnowledgeFeedbackRequest,
)
from shiliu.web import create_web_app
from test_v5_b_stage2_knowledge_lifecycle import _insert_second_fact
from test_v5_b_stage3_artifact_reuse import (
    GAP,
    _accept_child_fact,
    _add_gap_source,
    _assess,
    _core,
    _vertical,
)
from test_v5_b_stage4_personal_workspace import (
    _create,
    _stable_ask,
    _stable_research,
    _stable_route,
    _stable_search,
)
from shiliu.ask import AskRequest
from shiliu.retrieval import ProductSearchRequest


def _feedback(
    core: Application,
    task_id: str,
    *,
    command_id: str,
    target_kind: str,
    target_id: str,
    expected_hash: str,
    decision: str = "helpful",
) -> dict:
    return core.research_knowledge.submit_feedback(
        task_id,
        SubmitKnowledgeFeedbackRequest(
            command_id=command_id,
            target_kind=target_kind,
            target_id=target_id,
            decision=decision,
            reason_code="route" if target_kind == "artifact_route" else "answer_quality",
            note="bounded Stage 5 feedback",
            expected_hash=expected_hash,
        ),
        principal_id="local_operator",
    )


def test_reuse_first_closeout_feedback_restart_api_and_ui(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, artifact, page = _vertical(core, "stage5-direct")
    assessed = _assess(
        core,
        task_id,
        suffix="stage5-direct",
        query=fact["claim"],
        aspects=[fact["claim"]],
    )
    assert assessed["recommended_route"] == "direct_reuse"
    proceeded = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b5:direct:proceed",
            expected_version=1,
            route="direct_reuse",
        ),
        principal_id="local_operator",
    )
    assert proceeded["outcome_artifact_revision_id"] == artifact["artifact_revision_id"]
    workspace = core.research_knowledge.get_workspace(task_id)
    path = workspace["closeout"]["product_paths"]["reuse_first"]
    assert path["route"] == "direct_reuse"
    assert path["outcome_artifact_revision_id"] == artifact["artifact_revision_id"]

    recorded = _feedback(
        core,
        task_id,
        command_id="v5b5:feedback:page",
        target_kind="topic_page_revision",
        target_id=page["page_revision_id"],
        expected_hash=page["content_hash"],
    )
    assert recorded["advisory_only"] is True
    assert recorded["automatic_action"] is False
    assert _feedback(
        core,
        task_id,
        command_id="v5b5:feedback:page",
        target_kind="topic_page_revision",
        target_id=page["page_revision_id"],
        expected_hash=page["content_hash"],
    )["deduplicated"] is True
    restarted = Application(core.paths)
    projected = restarted.research_knowledge.get_workspace(task_id)
    assert projected["closeout"]["observability"]["counts"]["feedback"] == 1
    assert projected["closeout"]["observability"]["feedback"][0]["target_id"] == page["page_revision_id"]
    assert projected["closeout"]["observability"]["derived_only"] is True
    assert projected["closeout"]["observability"]["latest"]["artifact_route"]["final_route"] == "direct_reuse"
    assert projected["closeout"]["observability"]["latest"]["page_review"]["decision_kind"] == "publish"
    assert projected["pages"][0]["published_version"] == 1

    client = TestClient(create_web_app(restarted))
    route = restarted.research_knowledge.get_artifact_route(
        task_id, assessed["route_id"]
    )["latest"]
    response = client.post(
        f"/api/research/product/tasks/{task_id}/knowledge/feedback",
        json={
            "command_id": "v5b5:feedback:api",
            "target_kind": "artifact_route",
            "target_id": route["record_id"],
            "decision": "needs_fix",
            "reason_code": "route",
            "note": "route explanation could be clearer",
            "expected_hash": route["expected_authority_hash"],
        },
    )
    assert response.status_code == 201
    assert response.json()["outcome"]["advisory_only"] is True
    html = client.get(f"/research/{task_id}").text
    script = client.get("/static/research.js").text
    assert "data-knowledge-closeout" in html
    assert "Stage 5 product completion" in script
    assert "shared_current_fact" in html
    assert "/feedback" in script


def test_research_change_incremental_preserves_lineage_and_publish_boundary(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, artifact, page = _vertical(core, "stage5-incremental")
    _add_gap_source(core, "stage5-incremental")
    assessed = _assess(
        core,
        task_id,
        suffix="stage5-incremental",
        query=f"{fact['claim']}；{GAP}",
        aspects=[fact["claim"], GAP],
    )
    assert assessed["recommended_route"] == "incremental_refresh"
    confirmed = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b5:incremental:proceed",
            expected_version=1,
            route="incremental_refresh",
        ),
        principal_id="local_operator",
    )
    new_fact = _accept_child_fact(
        core, confirmed["continuation_task_id"], "stage5-incremental"
    )
    finalized = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b5:incremental:finalize",
            action="finalize",
            expected_version=2,
            new_fact_aspect_map={GAP: new_fact["fact_revision_id"]},
        ),
        principal_id="local_operator",
    )
    assert finalized["contribution"]["reused"][0]["fact_revision_id"] == fact["fact_revision_id"]
    assert finalized["contribution"]["newly_researched"][0]["fact_revision_id"] == new_fact["fact_revision_id"]
    workspace = core.research_knowledge.get_workspace(task_id)
    changed = workspace["closeout"]["product_paths"]["research_change"]
    assert changed["route"] == "incremental_refresh"
    assert changed["outcome_artifact_revision_id"] != artifact["artifact_revision_id"]
    assert workspace["pages"][0]["page_revision_id"] == page["page_revision_id"]
    assert workspace["pages"][0]["published_version"] == 1


def test_research_seed_fails_closed_without_automatic_knowledge_mutation(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, artifact, page = _vertical(core, "stage5-seed")
    assessed = _assess(
        core,
        task_id,
        suffix="stage5-seed",
        query="完全不存在的量子园艺主题",
        aspects=["量子园艺"],
    )
    assert assessed["recommended_route"] == "research_seed"
    with pytest.raises(ResearchValidationError, match="unsafe route override"):
        core.research_knowledge.proceed_artifact_route(
            task_id,
            assessed["route_id"],
            ProceedArtifactRouteRequest(
                command_id="v5b5:seed:unsafe-direct",
                expected_version=1,
                route="direct_reuse",
            ),
            principal_id="local_operator",
        )
    proceeded = core.research_knowledge.proceed_artifact_route(
        task_id,
        assessed["route_id"],
        ProceedArtifactRouteRequest(
            command_id="v5b5:seed:proceed",
            expected_version=1,
            route="research_seed",
        ),
        principal_id="local_operator",
    )
    assert proceeded["status"] == "running"
    with core.db.connect() as connection:
        goal = connection.execute(
            "SELECT evidence_policy_json FROM research_goals WHERE task_id=?",
            (proceeded["continuation_task_id"],),
        ).fetchone()
        policy = json.loads(str(goal["evidence_policy_json"]))
        assert policy["artifact_context_authority"] == "candidate_only_not_verifier"
        assert policy["open_retrieval_required"] is True
        assert connection.execute(
            "SELECT COUNT(*) FROM research_knowledge_artifact_revisions WHERE task_id=?",
            (task_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT current_version, published_version FROM research_topic_pages WHERE page_id=?",
            (page["page_id"],),
        ).fetchone()[:] == (1, 1)
    assert artifact["artifact_revision_id"] not in proceeded["contribution"]["reused"]


def test_bounded_relations_are_derived_current_explainable_and_l1_drillable(app_paths) -> None:
    core = _core(app_paths)
    task_id, first_fact, _, first_page = _vertical(core, "stage5-relations")
    second_fact_id, second_revision_id = _insert_second_fact(
        core, task_id, first_fact
    )
    second_artifact = core.research_knowledge.build_artifact(
        task_id,
        BuildKnowledgeArtifactRequest(
            command_id="v5b5:relations:artifact",
            fact_revision_ids=[first_fact["fact_revision_id"], second_revision_id],
        ),
    )
    second_page = core.research_knowledge.build_topic_page(
        task_id,
        BuildTopicPageRequest(
            command_id="v5b5:relations:page",
            artifact_revision_id=second_artifact["artifact_revision_id"],
        ),
    )
    core.research_knowledge.review_page(
        task_id,
        second_page["page_id"],
        ReviewTopicPageRequest(
            command_id="v5b5:relations:publish",
            decision="publish",
            expected_version=1,
        ),
        principal_id="local_operator",
    )
    workspace = core.research_knowledge.get_workspace(task_id)
    first_projection = next(
        page for page in workspace["pages"] if page["page_id"] == first_page["page_id"]
    )
    shared = first_projection["relations"]["items"][0]
    assert shared["kind"] == "shared_current_fact"
    assert shared["target"]["page_id"] == second_page["page_id"]
    assert shared["supporting_facts"][0]["citations"][0]["current_outcome"] == "current"
    assert shared["navigation_only"] is True
    assert shared["citation_authority"] is False
    assert shared["verifier"] is False
    assert shared["hard_filter"] is False

    source = next(
        fact for fact in workspace["facts"] if fact["fact_id"] == first_fact["fact_id"]
    )
    proposed = core.research_knowledge.propose_fact_update(
        task_id,
        source["fact_id"],
        ProposeFactUpdateRequest(
            command_id="v5b5:relations:conflict",
            kind="potential_conflict",
            expected_fact_state_version=source["fact_state_version"],
            related_fact_revision_id=second_revision_id,
        ),
        principal_id="local_operator",
    )
    state = next(
        item for item in core.research_knowledge.get_workspace(task_id)["fact_states"]
        if item["fact_id"] == first_fact["fact_id"]
    )
    core.research_knowledge.review_fact_update(
        task_id,
        proposed["update_candidate_id"],
        ReviewFactUpdateRequest(
            command_id="v5b5:relations:confirm",
            decision="accept",
            expected_candidate_version=0,
            expected_fact_state_version=state["state_version"],
            reason="same scope conflict confirmed by user",
        ),
        principal_id="local_operator",
    )
    conflicted = core.research_knowledge.get_workspace(task_id)
    relations = conflicted["closeout"]["relations"]
    assert relations["max_per_page"] == 8
    assert any(
        item["kind"] == "confirmed_conflict"
        for page in relations["by_page"].values()
        for item in page["items"]
    )
    assert not any(
        item["kind"] == "shared_current_fact"
        for page in relations["by_page"].values()
        for item in page["items"]
    )
    assert second_fact_id in {item["fact_id"] for item in conflicted["fact_states"]}


def test_feedback_expected_hash_cross_task_payload_and_fault_fail_closed(app_paths) -> None:
    core = _core(app_paths)
    task_id, _, _, page = _vertical(core, "stage5-feedback-fence")
    other_task, _, _, other_page = _vertical(core, "stage5-feedback-other")
    with pytest.raises(ResearchValidationError, match="expected_hash"):
        _feedback(
            core,
            task_id,
            command_id="v5b5:feedback:bad-hash",
            target_kind="topic_page_revision",
            target_id=page["page_revision_id"],
            expected_hash="0" * 64,
        )
    with pytest.raises(ResearchNotFound, match="does not exist in Task"):
        _feedback(
            core,
            task_id,
            command_id="v5b5:feedback:cross-task",
            target_kind="topic_page_revision",
            target_id=other_page["page_revision_id"],
            expected_hash=other_page["content_hash"],
        )
    assert other_task != task_id

    core.research_knowledge.fault_injector = lambda point: (
        (_ for _ in ()).throw(SimulatedCrash(point))
        if point == "after_stage5_feedback_event"
        else None
    )
    with pytest.raises(SimulatedCrash, match="after_stage5_feedback_event"):
        _feedback(
            core,
            task_id,
            command_id="v5b5:feedback:fault",
            target_kind="topic_page_revision",
            target_id=page["page_revision_id"],
            expected_hash=page["content_hash"],
        )
    core.research_knowledge.fault_injector = lambda _point: None
    with core.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_events WHERE task_id=? "
            "AND command_id='v5b5:feedback:fault'",
            (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts WHERE task_id=? "
            "AND command_id='v5b5:feedback:fault'",
            (task_id,),
        ).fetchone()[0] == 0

    accepted = _feedback(
        core,
        task_id,
        command_id="v5b5:feedback:mismatch",
        target_kind="topic_page_revision",
        target_id=page["page_revision_id"],
        expected_hash=page["content_hash"],
    )
    assert accepted["decision"] == "helpful"
    with pytest.raises(ResearchConflict, match="payload hash"):
        _feedback(
            core,
            task_id,
            command_id="v5b5:feedback:mismatch",
            target_kind="topic_page_revision",
            target_id=page["page_revision_id"],
            expected_hash=page["content_hash"],
            decision="needs_fix",
        )


def test_zero_table_composition_and_workspace_feedback_do_not_change_products(app_paths) -> None:
    core = _core(app_paths)
    task_id, fact, _, page = _vertical(core, "stage5-noninterference")
    assert SCHEMA_VERSION == 14
    with core.db.connect() as connection:
        stage5_tables = connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND "
            "(name LIKE '%relation%' OR name LIKE '%feedback%' OR name LIKE '%closeout%')"
        ).fetchall()
        assert stage5_tables == []

    search_before = _stable_search(
        core.product_search.search(ProductSearchRequest(query=fact["claim"])).as_dict()
    )
    ask_before = _stable_ask(
        core.ask_service.ask(AskRequest(query="ZZZZZ-NO-SUCH-EVIDENCE")).model_dump(
            mode="json"
        )
    )
    research_before = _stable_research(core.research_knowledge.get_workspace(task_id))
    route_before = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5b5:noninterference:before",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    _create(
        core,
        task_id,
        command_id="v5b5:workspace:seed",
        record_kind="explicit_memory",
        semantic_key="stage5-navigation-preference",
        payload={"key": "stage5-navigation-preference", "value": "relations"},
    )
    _feedback(
        core,
        task_id,
        command_id="v5b5:noninterference:feedback",
        target_kind="topic_page_revision",
        target_id=page["page_revision_id"],
        expected_hash=page["content_hash"],
    )
    search_after = _stable_search(
        core.product_search.search(ProductSearchRequest(query=fact["claim"])).as_dict()
    )
    ask_after = _stable_ask(
        core.ask_service.ask(AskRequest(query="ZZZZZ-NO-SUCH-EVIDENCE")).model_dump(
            mode="json"
        )
    )
    research_after = _stable_research(core.research_knowledge.get_workspace(task_id))
    route_after = _stable_route(
        core.research_knowledge.assess_artifact_route(
            task_id,
            AssessArtifactRouteRequest(
                command_id="v5b5:noninterference:after",
                query=fact["claim"],
                required_aspects=[fact["claim"]],
            ),
        )
    )
    assert search_after == search_before
    assert ask_after == ask_before
    assert research_after == research_before
    assert route_after == route_before
    assert route_after["open_corpus"]["independent_lane"] is True
    assert route_after["open_corpus"]["hard_filter"] is False
