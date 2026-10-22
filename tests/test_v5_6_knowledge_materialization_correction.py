from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest

from shiliu.ask import AskService
from shiliu.ask.contracts import AskRequest
from shiliu.knowledge_draft import (
    ConfirmDraftPromotionRequest,
    DraftCommandRequest,
    KnowledgeDraftError,
    SaveKnowledgeDraftRequest,
)
from shiliu.research.errors import ResearchConflict, SimulatedCrash
from shiliu.research.product_contracts import CreateProductResearchRequest
from research.v5_6.goal3b.tooling.collection_experience_fixture import (
    CASE_ID,
    FOLDER_ID,
    FOLDER_TITLE,
    GOLD_END,
    GOLD_START,
    GOLD_TEXT,
    LIMITATION,
    MATERIAL_CLAIM,
    QUESTION,
    SOURCE_ID,
    SOURCE_VERSION,
    FrozenAskProvider,
)
from research.v5_6.goal3b.tooling.common import load_cases, load_gold
from research.v5_6.goal3b.tooling.fixture import build_fixture
from test_v5_b_stage1_knowledge_workspace import _fixture_core, _terminal_task


def _collection_saved(tmp_path, suffix: str):
    cases, gold = load_cases(), load_gold()
    case, case_gold = cases[CASE_ID], gold[CASE_ID]
    span = case_gold["evidence_spans"][0]
    assert (
        case["question"],
        case["source_ids"],
        span["source_id"],
        span["source_version"],
        span["start_time"],
        span["end_time"],
        span["quote_text"],
        case_gold["limitation"],
    ) == (
        QUESTION,
        [SOURCE_ID],
        SOURCE_ID,
        SOURCE_VERSION,
        GOLD_START,
        GOLD_END,
        GOLD_TEXT,
        "Claims are bounded to selected local transcripts at recorded check time.",
    )
    fixture = build_fixture(
        case=case,
        gold=case_gold,
        arm="baseline",
        root=tmp_path / suffix,
    )
    core = fixture.core
    provider = FrozenAskProvider()
    core._ask_service = AskService(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        claim_verifier=None,
    )
    answer = core.ask_service.ask(AskRequest(query=QUESTION, mode="fast"))
    assert answer.status == "partial"
    assert provider.calls == ["query_analysis", "grounded_answer"]
    assert len(answer.citations) == 1
    trace = core.ask_service.get_trace(answer.run_id)
    assert trace is not None
    assert trace["trust_summary"]["overall_outcome"] == "partial"
    saved = core.knowledge_drafts.save(
        SaveKnowledgeDraftRequest(
            source_kind="ask_run",
            source_id=answer.run_id,
            command_id=f"correction:{suffix}:save",
        )
    )
    assert saved["scope"]["query"] == QUESTION.replace("？", "?")
    assert saved["limitations"] == [LIMITATION]
    assert saved["authority"] == "draft_only_not_fact_or_citation"
    return core, provider, answer, saved


def _authority_counts(core, task_id: str) -> dict[str, int]:
    tables = {
        "candidates": "research_knowledge_candidates",
        "facts": "research_fact_revisions",
        "artifacts": "research_knowledge_artifact_revisions",
        "pages": "research_topic_pages",
        "confirmations": "research_knowledge_review_decisions",
    }
    with core.db.connect() as connection:
        result = {
            key: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)
                ).fetchone()[0]
            )
            for key, table in tables.items()
        }
        result["publications"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_command_receipts WHERE task_id=? "
                "AND command_type='review_topic_page'",
                (task_id,),
            ).fetchone()[0]
        )
        return result


def test_exact_collection_draft_materializes_real_lineage_then_explicitly_publishes(
    tmp_path,
) -> None:
    core, provider, answer, saved = _collection_saved(tmp_path, "exact-collection")
    citation = answer.citations[0]
    assert citation.source_version == SOURCE_VERSION
    assert citation.start_time <= GOLD_START < GOLD_END <= citation.end_time
    assert "".join(GOLD_TEXT.split()) in "".join(citation.quote_text.split())
    assert "".join(MATERIAL_CLAIM.split()) not in "".join(QUESTION.split())
    binding = saved["evidence_refs"][0]
    assert binding["citation_id"] == citation.citation_id
    assert binding["source_version"] == SOURCE_VERSION
    assert binding["collection_bindings"] == [
        {
            "source_db_id": 1,
            "platform": "bilibili",
            "folder_id": FOLDER_ID,
            "folder_title": FOLDER_TITLE,
            "source_status": "active",
            "favorite_time": 1,
            "removed_at": None,
        }
    ]

    prepared_request = DraftCommandRequest(
        command_id="correction:collection:prepare",
        expected_version=int(saved["version"]),
    )
    prepared = core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]), prepared_request
    )
    assert prepared["status"] == "promotion_ready"
    assert prepared["candidate_ids"]
    assert core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]), prepared_request
    )["draft_revision_id"] == prepared["draft_revision_id"]
    task_id = str(prepared["materialization_task_id"])
    raw = core.research.get_task(task_id)
    assert len(raw["attempts"]) == 1
    attempt = raw["attempts"][0]
    assert attempt["cause"] == "initial"
    assert raw["provisional_artifacts"]
    assert any(value["event_type"] == "draft_evidence_materialized" for value in raw["events"])
    assert any(value["event_type"] == "candidate_deltas_materialized" for value in raw["events"])
    receipt = next(
        value
        for value in raw["command_receipts"]
        if value["command_type"] == "intake_draft_materialization_evidence"
    )
    assert receipt["owner_epoch"] == attempt["owner_epoch"]
    intake_checkpoint = next(
        value
        for value in raw["checkpoints"]
        if value["checkpoint_id"] == receipt["outcome_reference"]
    )
    assert intake_checkpoint["is_complete"] is True
    assert intake_checkpoint["state_payload"]["phase"] == "provisional_synthesis"
    assert raw["evidence_uses"]
    evidence_use = raw["evidence_uses"][0]
    assert evidence_use["task_id"] == task_id
    assert evidence_use["attempt_id"] == attempt["attempt_id"]
    assert evidence_use["evidence_id"] == binding["citation_id"]
    assert evidence_use["evidence_use_id"] != binding.get("evidence_use_id")
    assert all(value["outcome"] == "current" for value in raw["evidence_validations"])
    with core.db.connect() as connection:
        provenance = connection.execute(
            "SELECT * FROM research_evidence_provenance WHERE evidence_use_id=?",
            (evidence_use["evidence_use_id"],),
        ).fetchall()
    assert provenance
    assert {str(value["retrieval_method"]) for value in provenance} == {
        "draft_materialization_carry_in"
    }

    workspace = core.research_knowledge.get_workspace(task_id)
    pending = [value for value in workspace["candidates"] if value["status"] == "pending_review"]
    assert [value["candidate_id"] for value in pending] == prepared["candidate_ids"]
    assert provider.calls == ["query_analysis", "grounded_answer"]
    before = _authority_counts(core, task_id)
    assert before["candidates"] == len(prepared["candidate_ids"])
    assert all(before[key] == 0 for key in ("facts", "artifacts", "pages", "confirmations", "publications"))

    confirm_request = ConfirmDraftPromotionRequest(
        command_id="correction:collection:confirm",
        expected_version=int(prepared["version"]),
        candidate_ids=list(prepared["candidate_ids"]),
    )
    confirmed = core.knowledge_drafts.confirm_promotion(
        str(saved["draft_id"]), confirm_request, principal_id="local_operator"
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["promotion_output"]["review_status"] == "published"
    assert core.knowledge_drafts.confirm_promotion(
        str(saved["draft_id"]), confirm_request, principal_id="local_operator"
    )["draft_revision_id"] == confirmed["draft_revision_id"]
    after = _authority_counts(core, task_id)
    assert all(after[key] >= 1 for key in ("facts", "artifacts", "pages", "confirmations", "publications"))


def test_research_draft_creates_new_attempt_scoped_uses_for_same_evidence(app_paths) -> None:
    core = _fixture_core(app_paths)
    source_task_id = _terminal_task(core, "correction-source")
    source_raw = core.research.get_task(source_task_id)
    saved = core.knowledge_drafts.save(
        SaveKnowledgeDraftRequest(
            source_kind="research_task",
            source_id=source_task_id,
            command_id="correction:research:save",
        )
    )
    prepared = core.knowledge_drafts.prepare_promotion(
        str(saved["draft_id"]),
        DraftCommandRequest(
            command_id="correction:research:prepare",
            expected_version=int(saved["version"]),
        ),
    )
    materialized = core.research.get_task(str(prepared["materialization_task_id"]))
    old_uses = {value["evidence_use_id"] for value in source_raw["evidence_uses"]}
    new_uses = {value["evidence_use_id"] for value in materialized["evidence_uses"]}
    assert old_uses.isdisjoint(new_uses)
    assert {value["evidence_id"] for value in source_raw["evidence_uses"]} == {
        value["evidence_id"] for value in materialized["evidence_uses"]
    }
    assert {value["attempt_id"] for value in materialized["evidence_uses"]} == {
        materialized["attempts"][0]["attempt_id"]
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "question_scope",
        "limitation",
        "folder_identity",
        "source_identity",
        "source_version",
        "source_text",
        "segment_time",
        "segment_set",
    ],
)
def test_server_source_scope_segment_text_time_and_folder_mutations_fail_closed(
    tmp_path, mutation: str
) -> None:
    core, _provider, answer, saved = _collection_saved(tmp_path, mutation)
    bvid = SOURCE_ID.split(":", 1)[1]
    path = core.paths.videos_dir / bvid / "subtitle-raw.json"
    if mutation == "question_scope":
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE ask_runs SET query=? WHERE run_id=?",
                (QUESTION + " changed", answer.run_id),
            )
    elif mutation == "limitation":
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE ask_runs SET limitations_json=? WHERE run_id=?",
                (json.dumps([LIMITATION + " changed"]), answer.run_id),
            )
    elif mutation == "folder_identity":
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE favorite_sources SET folder_title=? WHERE folder_id=?",
                (FOLDER_TITLE + " changed", FOLDER_ID),
            )
    elif mutation == "source_identity":
        with core.db.connect() as connection:
            connection.execute(
                "UPDATE videos SET source_id=? WHERE source_id=?",
                ("BV0000000000", bvid),
            )
    elif mutation == "source_version":
        path.write_bytes(path.read_bytes() + b" \n")
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "source_text":
            payload[0]["content"] += " changed"
        elif mutation == "segment_time":
            payload[0]["from"] = float(payload[0]["from"]) + 0.001
        else:
            payload.pop(0)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KnowledgeDraftError) as raised:
        core.knowledge_drafts.prepare_promotion(
            str(saved["draft_id"]),
            DraftCommandRequest(
                command_id=f"correction:{mutation}:prepare",
                expected_version=int(saved["version"]),
            ),
        )
    assert raised.value.code in {
        "draft_source_changed",
        "draft_source_binding_changed",
        "draft_scope_changed",
        "draft_limitations_changed",
        "draft_source_evidence_changed",
        "draft_source_evidence_unavailable",
    }
    history = core.knowledge_drafts.get(str(saved["draft_id"]))["history"]
    assert history[-1]["status"] == "needs_revalidation"
    with core.db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM research_fact_revisions").fetchone()[0] == 0


def test_candidate_command_and_immutable_draft_overwrite_mutations_fail_closed(
    tmp_path,
) -> None:
    core, _provider, _answer, saved = _collection_saved(tmp_path, "command-candidate")
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE knowledge_draft_revisions SET scope_json='{}' WHERE draft_id=?",
                (saved["draft_id"],),
            )
    request = DraftCommandRequest(
        command_id="correction:mutation:prepare",
        expected_version=int(saved["version"]),
    )
    prepared = core.knowledge_drafts.prepare_promotion(str(saved["draft_id"]), request)
    with pytest.raises(KnowledgeDraftError) as command_error:
        core.knowledge_drafts.prepare_promotion(
            str(saved["draft_id"]),
            request.model_copy(update={"expected_version": int(saved["version"]) + 1}),
        )
    assert command_error.value.code == "draft_command_payload_mismatch"
    with pytest.raises(KnowledgeDraftError) as candidate_error:
        core.knowledge_drafts.confirm_promotion(
            str(saved["draft_id"]),
            ConfirmDraftPromotionRequest(
                command_id="correction:mutation:confirm",
                expected_version=int(prepared["version"]),
                candidate_ids=["kcandidate_mutated"],
            ),
            principal_id="local_operator",
        )
    assert candidate_error.value.code == "draft_candidate_set_mismatch"
    counts = _authority_counts(core, str(prepared["materialization_task_id"]))
    assert all(counts[key] == 0 for key in ("facts", "artifacts", "pages", "confirmations", "publications"))


def test_draft_intake_fault_rolls_back_then_replays_exactly_once(tmp_path) -> None:
    core, _provider, _answer, saved = _collection_saved(tmp_path, "atomic-intake")
    core.knowledge_drafts._assert_source_current(saved)
    spans = core.knowledge_drafts._reconstruct_materialization_evidence(saved)
    binding = core.knowledge_drafts._draft_materialization_binding(saved)
    created = core.research_product.create_task(
        CreateProductResearchRequest(
            command_id="correction:atomic:create",
            objective=str(saved["scope"]["query"]),
            success_constraints=[],
            run_immediately=False,
        )
    )
    task_id = str(created["task_id"])

    def crash(point: str) -> None:
        if point == "after_draft_materialization_checkpoint_insert":
            raise SimulatedCrash(point)

    core.research_inner.fault_injector = crash
    with pytest.raises(SimulatedCrash):
        core.research_product.intake_draft_materialization_evidence(
            task_id,
            command_id="correction:atomic:evidence",
            draft_binding=binding,
            spans=spans,
        )
    with core.db.connect() as connection:
        for table in (
            "research_inner_actions",
            "research_evidence_uses",
            "research_evidence_provenance",
            "research_evidence_validations",
            "research_checkpoints",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE task_id=?" if table != "research_evidence_provenance" else
                "SELECT COUNT(*) FROM research_evidence_provenance p JOIN research_evidence_uses u ON u.evidence_use_id=p.evidence_use_id WHERE u.task_id=?",
                (task_id,),
            ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM research_command_receipts WHERE task_id=? "
            "AND command_type='intake_draft_materialization_evidence'",
            (task_id,),
        ).fetchone()[0] == 0

    core.research_inner.fault_injector = lambda _point: None
    committed = core.research_product.intake_draft_materialization_evidence(
        task_id,
        command_id="correction:atomic:evidence",
        draft_binding=binding,
        spans=spans,
    )
    replay = core.research_product.intake_draft_materialization_evidence(
        task_id,
        command_id="correction:atomic:evidence",
        draft_binding=binding,
        spans=spans,
    )
    assert replay["deduplicated"] is True
    assert replay["checkpoint_id"] == committed["checkpoint_id"]
    with pytest.raises(ResearchConflict):
        core.research_product.intake_draft_materialization_evidence(
            task_id,
            command_id="correction:atomic:evidence",
            draft_binding={**binding, "scope_hash": "sha256:mutated"},
            spans=spans,
        )
    raw = core.research.get_task(task_id)
    assert len(raw["attempts"]) == 1
    assert len(raw["evidence_uses"]) == len(spans)
    assert len(
        [
            value
            for value in raw["command_receipts"]
            if value["command_type"] == "intake_draft_materialization_evidence"
        ]
    ) == 1
