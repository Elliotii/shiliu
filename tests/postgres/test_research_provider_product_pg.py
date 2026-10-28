"""Receipt-bound Research product with real PG and no-network Deep providers."""
import pytest
from types import SimpleNamespace
from test_research_knowledge_pg import knowledge_core
from test_research_outer_pg import outer_core
import test_v5_a_stage5_gate_b_provider_product as original
from test_v5_a_stage5_gate_b_provider_product import (
    DurableDeepResearchOutput,AgentDecision,AnswerBlock,GroundedAnswerDraft,
    AskResponse,TraceSummary,_ProductMockProvider,
)

class PgBoundedMockDeepExecutor(original._BoundedMockDeepExecutor):
    def execute(self, *, objective: str, provider_factory) -> DurableDeepResearchOutput:
        provider_factory("agent_action").generate_structured(
            role="agent_action",
            messages=[{"role": "user", "content": objective}],
            response_schema=AgentDecision,
            max_tokens=1200,
        )
        task_id = provider_factory.context.task_id
        attempt_id = provider_factory.context.attempt_id
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei
                  ON (ei.workspace_id,ei.evidence_id)=(eu.workspace_id,eu.evidence_id)
                WHERE eu.workspace_id=%s AND eu.task_id=%s AND eu.attempt_id=%s
                ORDER BY eu.created_at, eu.evidence_use_id LIMIT 1
                """,
                (self.db.workspace_id,task_id, attempt_id),
            ).fetchone()
        insufficient = objective in self.insufficient_objectives or row is None
        span = None if row is None else self.authority.observe(row).span
        if insufficient:
            final_blocks: list[AnswerBlock] = []
            draft = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["当前固定证据不足以回答该目标"],
            )
            citations = []
            termination = "evidence_unavailable"
        else:
            assert span is not None
            status = (
                "complete" if objective in self.complete_objectives else "partial"
            )
            final_blocks = [
                AnswerBlock(
                    text=span.quote_text,
                    citation_ids=[span.citation_id],
                )
            ]
            draft = GroundedAnswerDraft(
                status=status,
                answer_blocks=final_blocks,
                limitations=[f"Deep {status} limitation preserved"],
            )
            citations = [span.as_citation()]
            termination = "answer_ready"
        transport = provider_factory("grounded_answer")
        receipt_transport = getattr(transport, "provider", transport)
        provider = receipt_transport.factory.provider_factory("grounded_answer")
        if isinstance(provider, _ProductMockProvider):
            provider.next_grounded_draft = draft
        grounded = transport.generate_structured(
            role="grounded_answer",
            messages=[{"role": "user", "content": objective}],
            response_schema=GroundedAnswerDraft,
            max_tokens=4096,
        )
        # The mock transport proves receipt mechanics; this executor supplies the
        # typed grounded result that the unchanged Deep path would validate.
        assert isinstance(grounded.output, GroundedAnswerDraft)
        response = AskResponse(
            run_id=f"mock-deep-{task_id}-{attempt_id}",
            mode="deep",
            status=draft.status,
            answer_blocks=final_blocks,
            citations=citations,
            limitations=draft.limitations,
            termination_reason=termination,
            trace_summary=TraceSummary(
                query_count=1,
                retrieval_count=1,
                valid_evidence_count=len(citations),
                stale_evidence_count=0,
                context_span_count=len(citations),
                context_truncated=False,
                repair_used=False,
                latency_ms=3,
                termination_reason=termination,
                decision_rounds=1,
                tool_calls=1,
                visited_video_count=1 if citations else 0,
                visited_segment_count=1 if citations else 0,
                navigation_result_count=1,
            ),
        )
        return DurableDeepResearchOutput(
            response=response,
            trace={
                "run_id": response.run_id,
                "query": objective,
                "events": [{"event_type": "bounded_mock_deep"}],
                "status": response.status,
            },
        )


@pytest.fixture
def provider_product_pg(knowledge_core,monkeypatch):
    from shiliu.research.product_service import ResearchProductService
    core=knowledge_core
    inner=core.research_inner
    inner.provider_runs_authorized=True
    product=ResearchProductService(db=core.db,kernel=core.research,inner=inner,outer=core.research_outer,control=core.research_control,runner_id="gate-b-product-worker")
    materializer=inner.materializer
    def fixture(paths,*,inner_fault_injector=None):
        inner.fault_injector=inner_fault_injector or (lambda point:None)
        return core,inner,product,materializer
    core.product_search=inner.tools.navigation.product_search
    core.runtime_config=SimpleNamespace(corpus_identity=None)
    monkeypatch.setattr(original,"_fixture",fixture)
    monkeypatch.setattr(original,"_BoundedMockDeepExecutor",PgBoundedMockDeepExecutor)
    monkeypatch.setattr(original,"PersistentEvidenceAuthority",lambda db:inner.authority)
    monkeypatch.setattr(original,"TranscriptEvidenceMaterializer",lambda db:materializer)
    monkeypatch.setattr(original,"Application",lambda paths:core)
    return core,inner,product,materializer


@pytest.mark.parametrize("objective,answer_status",[
    (original.GROUNDED_OBJECTIVE,"complete"),
    (original.GROUNDED_OBJECTIVE,"partial"),
    ("无法由当前字幕证明的目标","insufficient"),
])
def test_original_provider_product_completion_on_pg(provider_product_pg,app_paths,objective,answer_status):
    core, inner, product, materializer = original._fixture(app_paths)
    provider = _ProductMockProvider()
    orchestrator, receipt = original._orchestrator(
        core,
        inner,
        product,
        materializer,
        provider,
        insufficient_objectives=(
            {objective} if answer_status == "insufficient" else set()
        ),
        complete_objectives={objective} if answer_status == "complete" else set(),
    )
    task_id = original._create(product, answer_status, objective)
    inner.grounded_validator = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Research must not revalidate Deep AskResponse")
    )
    product.outer.advance = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Provider completion must not enter Outer")
    )

    result = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert result["task_status"] == "terminal"
    raw = core.research.get_task(task_id)
    assert raw["task"]["status"] == "terminal"
    assert raw["checkpoints"]
    assert raw["outer_audits"] == []
    assert raw["traces"]
    artifact = raw["provisional_artifacts"][-1]
    assert artifact["provider_side_effect_id"]
    expected_result_status = {
        "complete": "valid_success",
        "partial": "valid_partial",
        "insufficient": "valid_insufficient",
    }[answer_status]
    assert artifact["answer_status"] == expected_result_status
    assert raw["traces"][-1]["ended_at"] is not None
    assert raw["results"][-1]["is_task_terminal"] == 1
    assert raw["results"][-1]["answer_status"] == expected_result_status
    assert raw["results"][-1]["attempt_id"] == raw["attempts"][-1]["attempt_id"]
    assert raw["results"][-1]["checkpoint_id"] == artifact["checkpoint_id"]
    with core.db.connect(read_only=True) as conn:
        assert conn.execute("SELECT count(*) AS n FROM research_outer_result_links WHERE workspace_id=%s AND task_id=%s",(core.db.workspace_id,task_id)).fetchone()["n"]==0

    restarted = original.Application(app_paths)
    projection = restarted.research_product.get_task(task_id)
    assert projection["state"]["answer_status"] == expected_result_status
    assert projection["answer_blocks"] == artifact["answer_blocks"]
    assert projection["limitations"] == artifact["limitations"]
    assert [value["citation_id"] for value in projection["citations"]] == artifact[
        "evidence_ids"
    ]
    assert projection["user_completion"]["objective_verified"] is False
    assert projection["provider_status"] == "boundary_recorded_not_call_verified"
    before_calls = list(provider.calls)
    before_budget = receipt.budget_snapshot(task_id)
    replay = orchestrator.run_to_boundary(
        task_id, command_id=f"gate-b-product:run:{objective}"
    )
    assert replay["deduplicated"] is True
    assert provider.calls == before_calls
    assert receipt.budget_snapshot(task_id) == before_budget


@pytest.mark.parametrize("contract",[
    "test_provider_product_unknown_dispatch_blocks_and_never_replays_transport",
    "test_unchanged_deep_executor_reaches_durable_waiting_boundary_no_network",
    "test_generation_failed_ask_response_preserves_provider_failure_mapping",
])
def test_original_provider_product_boundary_on_pg(provider_product_pg,app_paths,contract):
    getattr(original,contract)(app_paths)
